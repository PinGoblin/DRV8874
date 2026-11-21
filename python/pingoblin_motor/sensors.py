"""Current sensing: the ADS1115 driver and current-sensor classes.

Board A outputs 0.675 V per amp on A_ISENSE and B_ISENSE (J3 pins 7 and 8). One
ADS1115 has four inputs, so it reads two boards (four motors). Up to four ADS1115
boards share one I²C bus (addresses 0x48 to 0x4B).

ISENSE is zero during the PWM off-time. The ADS1115 is a delta-sigma converter that
averages each reading over about 1.2 ms, so with PWM at 1 kHz or faster one reading is
roughly *duty × motor current*. [`Motor.read_current()`][pingoblin_motor.motor.Motor.read_current]
divides by the duty to estimate the motor current.
"""
from __future__ import annotations

import abc
import threading
import time
from typing import Optional

from .faults import ConfigError, SensorError

ISENSE_V_PER_A = 0.675   # 1.5 kOhm x 450 uA/A (DRV8874 IPROPI gain)
"""Board A ISENSE gain: 0.675 V per amp (1.5 kΩ × 450 µA/A, the DRV8874 IPROPI gain)."""

# ADS1115 registers and config fields
_REG_CONVERSION = 0x00
_REG_CONFIG = 0x01
_PGA = {6.144: 0b000, 4.096: 0b001, 2.048: 0b010, 1.024: 0b011, 0.512: 0b100, 0.256: 0b101}
_DATA_RATE = {8: 0b000, 16: 0b001, 32: 0b010, 64: 0b011, 128: 0b100, 250: 0b101, 475: 0b110, 860: 0b111}


class ADS1115:
    """Minimal, thread-safe ADS1115 driver (single-shot, single-ended inputs).

    Works with a PinGoblin ADS1115 board or any ADS1115 breakout.

    Example:
        ```python
        from pingoblin_motor import ADS1115, MotorBoard

        adc = ADS1115(bus=1, address=0x48)
        board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6,
                           adc=adc, a_sense_channel=0, b_sense_channel=1)
        ```
    """

    def __init__(self, bus=1, address: int = 0x48, full_scale: float = 4.096, data_rate: int = 860):
        """
        Args:
            bus: I²C bus number (1 on a Raspberry Pi), or an object with
                `write_i2c_block_data()` and `read_i2c_block_data()` such as `smbus2.SMBus`.
            address: 0x48 (ADDR to GND), 0x49 (VDD), 0x4A (SDA) or 0x4B (SCL).
            full_scale: Input range (V). 4.096 covers ISENSE at 5 V logic.
            data_rate: Samples per second.

        Raises:
            ConfigError: Invalid address, range or rate, or `smbus2` is not installed.
        """
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
        """Build the config-register value for a single-shot read.

        Args:
            channel: Input 0–3 (AIN0 to AIN3, measured against GND).

        Returns:
            The 16-bit config register value.

        Raises:
            ConfigError: Channel out of range.
        """
        if channel not in (0, 1, 2, 3):
            raise ConfigError("ADS1115 channel must be 0-3")
        return ((1 << 15)                      # OS: start a conversion
                | ((0b100 | channel) << 12)    # MUX: AINx vs GND
                | (_PGA[self.full_scale] << 9)
                | (1 << 8)                     # single-shot mode
                | (_DATA_RATE[self.data_rate] << 5)
                | 0b11)                        # comparator off

    def read_voltage(self, channel: int) -> float:
        """Start a conversion, wait for it and return the voltage.

        Args:
            channel: Input 0–3.

        Returns:
            The input voltage (V).

        Raises:
            SensorError: The I²C transfer failed.
        """
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
        """Close the I²C bus if this object opened it."""
        if self._owns_bus:
            self._bus.close()


class CurrentSensor(abc.ABC):
    """Interface for anything that returns a voltage proportional to motor current.

    Implement `read_voltage()` to use a different ADC.
    """

    @abc.abstractmethod
    def read_voltage(self) -> float:
        """Return the ISENSE voltage.

        Returns:
            Volts at the ISENSE pin.

        Raises:
            SensorError: The reading failed.
        """


class ADS1115Channel(CurrentSensor):
    """One ADS1115 input wired to an ISENSE pin."""

    def __init__(self, adc: ADS1115, channel: int):
        """
        Args:
            adc: The [`ADS1115`][pingoblin_motor.sensors.ADS1115].
            channel: Input 0–3.

        Raises:
            ConfigError: Channel out of range.
        """
        adc.config_word(channel)  # validates the channel number
        self.adc, self.channel = adc, channel

    def read_voltage(self) -> float:
        """Read this channel.

        Returns:
            The ISENSE voltage (V).

        Raises:
            SensorError: The I²C transfer failed.
        """
        return self.adc.read_voltage(self.channel)


class MotorCurrentSensor:
    """Converts ISENSE voltage readings into amps, averaging several readings."""

    def __init__(self, source: CurrentSensor, samples: int = 4, v_per_a: float = ISENSE_V_PER_A):
        """
        Args:
            source: A [`CurrentSensor`][pingoblin_motor.sensors.CurrentSensor].
            samples: Readings averaged per measurement (smooths PWM and brush noise).
            v_per_a: ISENSE gain (V/A): 0.675 on Board A.
        """
        self.source, self.samples, self.v_per_a = source, max(1, samples), v_per_a

    def read_isense_amps(self) -> float:
        """Return the average ISENSE current, including the PWM off-time.

        This is the supply-side current the board draws for this motor.

        Returns:
            Amps, never negative.

        Raises:
            SensorError: A reading failed.
        """
        total = sum(self.source.read_voltage() for _ in range(self.samples))
        return max(0.0, total / self.samples / self.v_per_a)

    def read_motor_amps(self, duty: float) -> float:
        """Estimate the motor current, correcting for PWM duty.

        Args:
            duty: The applied PWM duty, 0–1. Below 0.1 the raw reading is returned, because
                the correction becomes unreliable.

        Returns:
            Motor current (A).

        Raises:
            SensorError: A reading failed.
        """
        amps = self.read_isense_amps()
        return amps / duty if duty >= 0.1 else amps


class MockCurrentSensor(CurrentSensor):
    """Mock current sensor for tests.

    Attributes:
        amps (float): Current at the ISENSE pin (A), that is the duty-weighted average.
            For a motor drawing 1 A at 50 % duty, set 0.5.
        fail (bool): Set `True` to make reads raise
            [`SensorError`][pingoblin_motor.faults.SensorError].
    """

    def __init__(self, amps: float = 0.0, v_per_a: float = ISENSE_V_PER_A):
        """
        Args:
            amps: Initial ISENSE current (A).
            v_per_a: ISENSE gain (V/A).
        """
        self.amps, self.v_per_a, self.fail = amps, v_per_a, False

    def read_voltage(self) -> float:
        """Return `amps × v_per_a`.

        Returns:
            The simulated ISENSE voltage (V).

        Raises:
            SensorError: `fail` is set.
        """
        if self.fail:
            raise SensorError("mock sensor failure")
        return self.amps * self.v_per_a


def make_sensor(adc: Optional[ADS1115], channel: Optional[int], samples: int = 4) -> Optional[MotorCurrentSensor]:
    """Build a [`MotorCurrentSensor`][pingoblin_motor.sensors.MotorCurrentSensor] from an ADS1115 and a channel.

    Args:
        adc: The ADS1115, or `None`.
        channel: Input 0–3, or `None`.
        samples: Readings averaged per measurement.

    Returns:
        The sensor, or `None` if `adc` or `channel` is `None`.
    """
    if adc is None or channel is None:
        return None
    return MotorCurrentSensor(ADS1115Channel(adc, channel), samples=samples)
