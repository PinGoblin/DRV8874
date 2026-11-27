"""Hardware pin backends.

A backend creates three kinds of pin: digital outputs, PWM outputs and digital inputs.
Pins are cached by GPIO number, so several boards in a daisy chain can share one
nSLEEP line: ask for the same pin twice and you get the same object back. (nFAULT must
not be shared: each board needs its own.)
A shared pin is released when the last user closes it.

| Backend | Use |
|---|---|
| [`GpiozeroBackend`][pingoblin_motor.backends.GpiozeroBackend] | Default on a Raspberry Pi (Pi 5 supported). Software PWM, or hardware PWM on GPIO12/13/18/19 |
| [`MockBackend`][pingoblin_motor.backends.MockBackend] | No hardware: tests, dry runs and CI |
"""
from __future__ import annotations

import abc
import threading
from typing import Dict, Optional

from .faults import ConfigError

# Raspberry Pi GPIOs that have a hardware PWM channel (Pi 4 and Pi 5 header).
HW_PWM_CHANNELS = {12: 0, 13: 1, 18: 0, 19: 1}
"""Raspberry Pi GPIOs with a hardware PWM channel, mapped to the channel number."""


class OutputPin(abc.ABC):
    """Interface for a digital output pin."""

    @abc.abstractmethod
    def set(self, value: bool) -> None:
        """Drive the pin.

        Args:
            value: `True` for high, `False` for low.
        """

    @abc.abstractmethod
    def get(self) -> bool:
        """Return the level the pin is driven to.

        Returns:
            `True` if high.
        """

    def close(self) -> None:
        """Release the pin. The default does nothing."""
        pass


class PwmPin(abc.ABC):
    """Interface for a PWM output pin. Duty cycles are fractions from 0.0 to 1.0."""

    @abc.abstractmethod
    def set_duty(self, duty: float) -> None:
        """Set the duty cycle.

        Args:
            duty: 0.0 (always low) to 1.0 (always high). Out-of-range values are clamped.
        """

    @abc.abstractmethod
    def get_duty(self) -> float:
        """Return the current duty cycle.

        Returns:
            The duty cycle, 0.0 to 1.0.
        """

    def close(self) -> None:
        """Release the pin. The default does nothing."""
        pass


class InputPin(abc.ABC):
    """Interface for a digital input pin."""

    @abc.abstractmethod
    def read(self) -> bool:
        """Return the electrical level.

        Returns:
            `True` if the pin is high.
        """

    def close(self) -> None:
        """Release the pin. The default does nothing."""
        pass


class Backend(abc.ABC):
    """Base class for backends: creates, caches and reference-counts pins.

    Subclasses implement `_make_output()`, `_make_pwm()` and `_make_input()`.
    """

    #: Highest VLOGIC the host GPIOs tolerate (V). nFAULT is pulled up to VLOGIC.
    max_logic_voltage: float = 5.5

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._pins: Dict[int, object] = {}
        self._kinds: Dict[int, str] = {}
        self._refs: Dict[int, int] = {}

    def _get(self, pin: int, kind: str, factory):
        with self._lock:
            if pin in self._pins:
                if self._kinds[pin] != kind:
                    raise ConfigError(
                        f"GPIO{pin} already used as {self._kinds[pin]}, cannot reuse as {kind}")
                self._refs[pin] += 1
                return self._pins[pin]
            obj = factory()
            self._pins[pin], self._kinds[pin], self._refs[pin] = obj, kind, 1
            return obj

    def output(self, pin: int, initial: bool = False) -> OutputPin:
        """Get a digital output, creating it on first use.

        Args:
            pin: BCM GPIO number.
            initial: Level to drive when the pin is first created.

        Returns:
            An [`OutputPin`][pingoblin_motor.backends.OutputPin].

        Raises:
            ConfigError: The pin is already in use as a PWM output or input.
        """
        return self._get(pin, "output", lambda: self._make_output(pin, initial))

    def pwm(self, pin: int, frequency: float) -> PwmPin:
        """Get a PWM output, creating it on first use (duty 0).

        Args:
            pin: BCM GPIO number.
            frequency: PWM frequency (Hz). Ignored if the pin already exists.

        Returns:
            A [`PwmPin`][pingoblin_motor.backends.PwmPin].

        Raises:
            ConfigError: The pin is already in use as a digital output or input.
        """
        return self._get(pin, "pwm", lambda: self._make_pwm(pin, frequency))

    def input(self, pin: int) -> InputPin:
        """Get a digital input, creating it on first use (no internal pull resistor).

        Args:
            pin: BCM GPIO number.

        Returns:
            An [`InputPin`][pingoblin_motor.backends.InputPin].

        Raises:
            ConfigError: The pin is already in use as an output.
        """
        return self._get(pin, "input", lambda: self._make_input(pin))

    def release(self, pin: Optional[int]) -> None:
        """Drop one reference to a pin, and close it when no one uses it.

        Args:
            pin: BCM GPIO number, or `None` (ignored).
        """
        if pin is None:
            return
        with self._lock:
            if pin not in self._pins:
                return
            self._refs[pin] -= 1
            if self._refs[pin] <= 0:
                self._pins.pop(pin).close()
                del self._kinds[pin], self._refs[pin]

    @abc.abstractmethod
    def _make_output(self, pin: int, initial: bool) -> OutputPin: ...

    @abc.abstractmethod
    def _make_pwm(self, pin: int, frequency: float) -> PwmPin: ...

    @abc.abstractmethod
    def _make_input(self, pin: int) -> InputPin: ...


# ------------------------------------------------------------------ gpiozero
class _GzOutput(OutputPin):
    def __init__(self, dev):
        self._dev = dev

    def set(self, value):
        self._dev.value = 1 if value else 0

    def get(self):
        return bool(self._dev.value)

    def close(self):
        self._dev.close()


class _GzPwm(PwmPin):
    def __init__(self, dev):
        self._dev = dev

    def set_duty(self, duty):
        self._dev.value = max(0.0, min(1.0, duty))

    def get_duty(self):
        return float(self._dev.value)

    def close(self):
        self._dev.close()


class _GzInput(InputPin):
    def __init__(self, dev):
        self._dev = dev

    def read(self):
        # active_state=True so .value is the raw electrical level.
        return bool(self._dev.value)

    def close(self):
        self._dev.close()


class _HwPwm(PwmPin):
    """Hardware PWM through the ``rpi-hardware-pwm`` package (silent 20 kHz)."""

    def __init__(self, pin: int, frequency: float, chip: int):
        try:
            from rpi_hardware_pwm import HardwarePWM
        except ImportError as exc:  # pragma: no cover - needs a Pi
            raise ConfigError("hardware_pwm=True needs: pip install rpi-hardware-pwm") from exc
        if pin not in HW_PWM_CHANNELS:
            raise ConfigError(f"GPIO{pin} has no hardware PWM; use one of {sorted(HW_PWM_CHANNELS)}")
        self._pwm = HardwarePWM(pwm_channel=HW_PWM_CHANNELS[pin], hz=frequency, chip=chip)
        self._pwm.start(0)
        self._duty = 0.0

    def set_duty(self, duty):
        self._duty = max(0.0, min(1.0, duty))
        self._pwm.change_duty_cycle(self._duty * 100.0)

    def get_duty(self):
        return self._duty

    def close(self):
        self._pwm.stop()


class GpiozeroBackend(Backend):
    """Raspberry Pi backend using [gpiozero](https://gpiozero.readthedocs.io/) (BCM pin numbers).

    gpiozero's software PWM is reliable only up to about 1 kHz, which makes motors whine.
    For silent 20 kHz PWM, set `hardware_pwm=True` and use GPIO12, 13, 18 or 19 for the EN
    pins. This needs the `rpi-hardware-pwm` package and `dtoverlay=pwm-2chan` in
    `/boot/firmware/config.txt`. The Pi has two hardware PWM channels, so it covers one board.
    """

    #: Raspberry Pi GPIOs are 3.3 V only.
    max_logic_voltage = 3.6

    def __init__(self, hardware_pwm: bool = False, pwm_chip: int = 0, pin_factory=None):
        """
        Args:
            hardware_pwm: Use hardware PWM on GPIO12/13/18/19. Other EN pins fall back to
                software PWM.
            pwm_chip: PWM chip number for `rpi-hardware-pwm`: 0 on a Pi 4, 2 on some Pi 5 kernels.
            pin_factory: Optional gpiozero pin factory (for example a remote or mock factory).

        Raises:
            ConfigError: gpiozero is not installed.
        """
        super().__init__()
        try:
            import gpiozero  # noqa: F401
        except ImportError as exc:  # pragma: no cover - needs a Pi
            raise ConfigError("GpiozeroBackend needs gpiozero: pip install gpiozero") from exc
        self.hardware_pwm = hardware_pwm
        self.pwm_chip = pwm_chip
        self.pin_factory = pin_factory

    def _make_output(self, pin, initial):
        from gpiozero import DigitalOutputDevice
        return _GzOutput(DigitalOutputDevice(pin, initial_value=initial, pin_factory=self.pin_factory))

    def _make_pwm(self, pin, frequency):
        if self.hardware_pwm and pin in HW_PWM_CHANNELS:
            return _HwPwm(pin, frequency, self.pwm_chip)
        from gpiozero import PWMOutputDevice
        return _GzPwm(PWMOutputDevice(pin, frequency=frequency, initial_value=0, pin_factory=self.pin_factory))

    def _make_input(self, pin):
        from gpiozero import DigitalInputDevice
        # The board has its own pull-up on nFAULT, so no internal pull.
        return _GzInput(DigitalInputDevice(pin, pull_up=None, active_state=True, pin_factory=self.pin_factory))


# ---------------------------------------------------------------------- mock
class MockOutput(OutputPin):
    """Mock digital output for tests.

    Attributes:
        pin (int): GPIO number.
        value (bool): The driven level.
    """

    def __init__(self, pin, initial):
        """
        Args:
            pin: GPIO number.
            initial: Initial level.
        """
        self.pin, self.value = pin, bool(initial)

    def set(self, value):
        """Set `value`.

        Args:
            value: The new level.
        """
        self.value = bool(value)

    def get(self):
        """Return `value`.

        Returns:
            The driven level.
        """
        return self.value


class MockPwm(PwmPin):
    """Mock PWM output for tests.

    Attributes:
        pin (int): GPIO number.
        frequency (float): PWM frequency (Hz).
        duty (float): Duty cycle, 0.0 to 1.0.
    """

    def __init__(self, pin, frequency):
        """
        Args:
            pin: GPIO number.
            frequency: PWM frequency (Hz).
        """
        self.pin, self.frequency, self.duty = pin, frequency, 0.0

    def set_duty(self, duty):
        """Set `duty`, clamped to 0.0–1.0.

        Args:
            duty: The new duty cycle.
        """
        self.duty = max(0.0, min(1.0, duty))

    def get_duty(self):
        """Return `duty`.

        Returns:
            The duty cycle.
        """
        return self.duty


class MockInput(InputPin):
    """Mock digital input for tests. Set `level` to simulate the pin.

    Attributes:
        pin (int): GPIO number.
        level (bool): The simulated level. Starts high, like nFAULT's pull-up.
    """

    def __init__(self, pin):
        """
        Args:
            pin: GPIO number.
        """
        self.pin, self.level = pin, True  # nFAULT idles high (pulled up)

    def read(self):
        """Return `level`.

        Returns:
            The simulated level.
        """
        return self.level


class MockBackend(Backend):
    """Hardware-free backend for tests and dry runs.

    Example:
        ```python
        from pingoblin_motor import MockBackend, MotorBoard

        be = MockBackend()
        board = MotorBoard(a_en=12, a_ph=5, fault_pin=19, backend=be)
        board.motor_a.forward(50)
        assert be.pins[12].duty == 0.5
        be.pins[19].level = False        # simulate nFAULT going low
        ```
    """

    @property
    def pins(self):
        """The pins created so far, by GPIO number.

        Returns:
            A dict of [`MockOutput`][pingoblin_motor.backends.MockOutput],
            [`MockPwm`][pingoblin_motor.backends.MockPwm] and
            [`MockInput`][pingoblin_motor.backends.MockInput] objects.
        """
        return self._pins

    def _make_output(self, pin, initial):
        return MockOutput(pin, initial)

    def _make_pwm(self, pin, frequency):
        return MockPwm(pin, frequency)

    def _make_input(self, pin):
        return MockInput(pin)


def default_backend() -> Backend:
    """Return the default backend for this platform.

    Returns:
        A new [`GpiozeroBackend`][pingoblin_motor.backends.GpiozeroBackend].
    """
    return GpiozeroBackend()
