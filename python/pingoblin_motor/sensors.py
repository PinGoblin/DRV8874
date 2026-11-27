"""Current sensing: current-sensor classes and the adapter for an ADS1115 board.

The PinGoblin DRV8874 outputs 0.45 V per amp on A_ISENSE and B_ISENSE (J3 pins 7 and 8). The Raspberry
Pi has no ADC, so read ISENSE with a PinGoblin ADS1115 board and its library,
[`pingoblin_ads1115`](https://pingoblin.github.io/ADS1115/). One ADS1115 has four inputs,
so it reads two boards (four motors). Up to four ADS1115 boards share one I²C bus
(addresses 0x48 to 0x4B).

ISENSE is zero during the PWM off-time. The ADS1115 is a delta-sigma converter that
averages each reading over about 1.2 ms, so with PWM at 1 kHz or faster one reading is
roughly *duty × motor current*. [`Motor.read_current()`][pingoblin_motor.motor.Motor.read_current]
divides by the duty to estimate the motor current.
"""
from __future__ import annotations

import abc
import warnings
from typing import Optional

from .faults import ConfigError, SensorError

ISENSE_V_PER_A = 0.45    # 1.0 kOhm x 450 uA/A (DRV8874 IPROPI gain)
"""PinGoblin DRV8874 ISENSE gain: 0.45 V per amp (1.0 kΩ × 450 µA/A, the DRV8874 IPROPI gain)."""

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
    """One ADS1115 input wired to an ISENSE pin.

    Works with an [`pingoblin_ads1115.ADS1115`](https://pingoblin.github.io/ADS1115/), or any
    ADC object with a `read_voltage(channel)` method that is safe to call from the monitor
    thread.
    """

    MIN_RATE = 475
    """Slowest ADS1115 data rate (samples/s) that keeps stall and overload detection prompt."""

    def __init__(self, adc: object, channel: int):
        """
        Args:
            adc: The ADS1115, for example `pingoblin_ads1115.ADS1115(address=0x48, rate=860)`.
            channel: Input 0–3.

        Raises:
            ConfigError: Channel out of range, or `adc` has no `read_voltage()` method.
        """
        if channel not in (0, 1, 2, 3):
            raise ConfigError("ADS1115 channel must be 0-3")
        if not callable(getattr(adc, "read_voltage", None)):
            raise ConfigError("adc must have a read_voltage(channel) method")
        rate = getattr(adc, "rate", None)
        if isinstance(rate, int) and rate < self.MIN_RATE:
            warnings.warn(f"ADS1115 rate is {rate} samples/s: create it with rate=860 so that "
                          "stall and overload detection respond promptly", stacklevel=3)
        self.adc, self.channel = adc, channel

    def read_voltage(self) -> float:
        """Read this channel.

        Returns:
            The ISENSE voltage (V).

        Raises:
            SensorError: The I²C transfer failed.
        """
        try:
            return self.adc.read_voltage(self.channel)
        except OSError as exc:
            raise SensorError(f"ADS1115 read failed: {exc}") from exc


class MotorCurrentSensor:
    """Converts ISENSE voltage readings into amps, averaging several readings."""

    def __init__(self, source: CurrentSensor, samples: int = 4, v_per_a: float = ISENSE_V_PER_A):
        """
        Args:
            source: A [`CurrentSensor`][pingoblin_motor.sensors.CurrentSensor].
            samples: Readings averaged per measurement (smooths PWM and brush noise).
            v_per_a: ISENSE gain (V/A): 0.45 on the PinGoblin DRV8874.
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


def make_sensor(adc: Optional[object], channel: Optional[int], samples: int = 4) -> Optional[MotorCurrentSensor]:
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
