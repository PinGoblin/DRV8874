"""Current sensing: ADS1115 driver and current-sensor classes.

Board A outputs 0.675 V per amp on A_ISENSE / B_ISENSE. One ADS1115 has four
inputs, so it can read the current of two Board A boards (four motors). Up to
four ADS1115 boards fit on one I2C bus (addresses 0x48-0x4B).

The ADS1115 is a delta-sigma converter: each conversion averages the input
over about 1.2 ms (at 860 samples/s). ISENSE is zero during the PWM off-time,
so with PWM at 1 kHz or faster one reading is roughly ``duty x motor current``.
:class:`MotorCurrentSensor` divides by the duty to estimate the motor current.
"""
from __future__ import annotations

import abc
import threading
import time
from typing import Optional

from .faults import ConfigError, SensorError

ISENSE_V_PER_A = 0.675   # 1.5 kOhm x 450 uA/A (DRV8874 IPROPI gain)

# ADS1115 registers and config fields
_REG_CONVERSION = 0x00
_REG_CONFIG = 0x01
_PGA = {6.144: 0b000, 4.096: 0b001, 2.048: 0b010, 1.024: 0b011, 0.512: 0b100, 0.256: 0b101}
_DATA_RATE = {8: 0b000, 16: 0b001, 32: 0b010, 64: 0b011, 128: 0b100, 250: 0b101, 475: 0b110, 860: 0b111}


class ADS1115:
    """Minimal ADS1115 driver (single-shot, single-ended), thread-safe.

    Works with a PinGoblin ADS1115 board or any ADS1115 breakout.

    :param bus: I2C bus number (1 on a Raspberry Pi) or an object with
        ``write_i2c_block_data`` / ``read_i2c_block_data`` (e.g. ``smbus2.SMBus``).
    :param address: 0x48 (ADDR to GND), 0x49 (VDD), 0x4A (SDA) or 0x4B (SCL).
    :param full_scale: input range in volts. 4.096 covers ISENSE at 5 V logic.
    :param data_rate: samples per second.
    """

    def __init__(self, bus=1, address: int = 0x48, full_scale: float = 4.096, data_rate: int = 860):
        if address not in (0x48, 0x49, 0x4A, 0x4B):
            raise ConfigError(f"invalid ADS1115 address 0x{address:02X}")
        if full_scale not in _PGA:
            raise ConfigError(f"full_scale must be one of {sorted(_PGA)}")
        if data_rate not in _DATA_RATE:
            raise ConfigError(f"data_rate must be one of {sorted(_DATA_RATE)}")
        if isinstance(bus, int):
            try:
                from smbus2 import SMBus
            except ImportError as exc:  # pragma: no cover - needs a Pi
                raise ConfigError("ADS1115 needs smbus2: pip install smbus2") from exc
            bus = SMBus(bus)
            self._owns_bus = True
        else:
            self._owns_bus = False
        self._bus = bus
        self.address = address
        self.full_scale = full_scale
        self.data_rate = data_rate
        self._lock = threading.Lock()
        self._conv_time = 1.0 / data_rate + 0.0004

    def config_word(self, channel: int) -> int:
        """16-bit config register value for a single-shot read of ``channel``."""
        if channel not in (0, 1, 2, 3):
            raise ConfigError("ADS1115 channel must be 0-3")
        return ((1 << 15)                      # OS: start a conversion
                | ((0b100 | channel) << 12)    # MUX: AINx vs GND
                | (_PGA[self.full_scale] << 9)
                | (1 << 8)                     # single-shot mode
                | (_DATA_RATE[self.data_rate] << 5)
                | 0b11)                        # comparator off

    def read_voltage(self, channel: int) -> float:
        """Return the voltage on AIN``channel`` in volts."""
        cfg = self.config_word(channel)
        try:
            with self._lock:
                self._bus.write_i2c_block_data(self.address, _REG_CONFIG, [cfg >> 8, cfg & 0xFF])
                deadline = time.monotonic() + 10 * self._conv_time
                time.sleep(self._conv_time)
                while True:  # wait for OS bit = 1 (conversion done)
                    hi, _ = self._bus.read_i2c_block_data(self.address, _REG_CONFIG, 2)
                    if hi & 0x80 or time.monotonic() > deadline:
                        break
                    time.sleep(0.0002)
                hi, lo = self._bus.read_i2c_block_data(self.address, _REG_CONVERSION, 2)
        except OSError as exc:
            raise SensorError(f"ADS1115 0x{self.address:02X} read failed: {exc}") from exc
        raw = (hi << 8) | lo
        if raw & 0x8000:
            raw -= 1 << 16
        return raw * self.full_scale / 32768.0

    def close(self) -> None:
        if self._owns_bus:
            self._bus.close()


class CurrentSensor(abc.ABC):
    """Anything that returns a voltage proportional to motor current."""

    @abc.abstractmethod
    def read_voltage(self) -> float: ...


class ADS1115Channel(CurrentSensor):
    """One ADS1115 input wired to an ISENSE pin."""

    def __init__(self, adc: ADS1115, channel: int):
        adc.config_word(channel)  # validates the channel number
        self.adc, self.channel = adc, channel

    def read_voltage(self) -> float:
        return self.adc.read_voltage(self.channel)


class MotorCurrentSensor:
    """Converts ISENSE readings into motor current.

    :param source: a :class:`CurrentSensor` (e.g. :class:`ADS1115Channel`).
    :param samples: readings averaged per measurement (smooths PWM and brush noise).
    :param v_per_a: ISENSE gain; 0.675 V/A on Board A.
    """

    def __init__(self, source: CurrentSensor, samples: int = 4, v_per_a: float = ISENSE_V_PER_A):
        self.source, self.samples, self.v_per_a = source, max(1, samples), v_per_a

    def read_isense_amps(self) -> float:
        """Average ISENSE current (what the pin shows, including PWM off-time)."""
        total = sum(self.source.read_voltage() for _ in range(self.samples))
        return max(0.0, total / self.samples / self.v_per_a)

    def read_motor_amps(self, duty: float) -> float:
        """Estimated motor current, correcting for PWM duty (0-1).

        Below 10 % duty the estimate becomes unreliable, so the raw reading
        is returned.
        """
        amps = self.read_isense_amps()
        return amps / duty if duty >= 0.1 else amps


class MockCurrentSensor(CurrentSensor):
    """Test sensor: set ``amps`` (motor current at the pin) or ``fail``."""

    def __init__(self, amps: float = 0.0, v_per_a: float = ISENSE_V_PER_A):
        self.amps, self.v_per_a, self.fail = amps, v_per_a, False

    def read_voltage(self) -> float:
        if self.fail:
            raise SensorError("mock sensor failure")
        return self.amps * self.v_per_a


def make_sensor(adc: Optional[ADS1115], channel: Optional[int], samples: int = 4) -> Optional[MotorCurrentSensor]:
    """Helper: build a MotorCurrentSensor from an ADS1115 and channel, or None."""
    if adc is None or channel is None:
        return None
    return MotorCurrentSensor(ADS1115Channel(adc, channel), samples=samples)
