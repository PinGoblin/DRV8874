"""Hardware pin backends.

A backend creates three kinds of pin: digital outputs, PWM outputs and
digital inputs. Pins are cached by number, so several boards in a daisy
chain can share one nSLEEP or nFAULT GPIO: ask for the same pin twice and
you get the same object back.

Backends:

* :class:`GpiozeroBackend` – the default on a Raspberry Pi (works on Pi 5).
  Uses software PWM unless ``hardware_pwm=True``.
* :class:`MockBackend` – no hardware; for tests and dry runs.
"""
from __future__ import annotations

import abc
import threading
from typing import Dict, Optional

from .faults import ConfigError

# Raspberry Pi GPIOs that have a hardware PWM channel (Pi 4 and Pi 5 header).
HW_PWM_CHANNELS = {12: 0, 13: 1, 18: 0, 19: 1}


class OutputPin(abc.ABC):
    @abc.abstractmethod
    def set(self, value: bool) -> None: ...

    @abc.abstractmethod
    def get(self) -> bool: ...

    def close(self) -> None:
        pass


class PwmPin(abc.ABC):
    """PWM output. ``duty`` is 0.0-1.0."""

    @abc.abstractmethod
    def set_duty(self, duty: float) -> None: ...

    @abc.abstractmethod
    def get_duty(self) -> float: ...

    def close(self) -> None:
        pass


class InputPin(abc.ABC):
    @abc.abstractmethod
    def read(self) -> bool:
        """Return the electrical level (True = high)."""

    def close(self) -> None:
        pass


class Backend(abc.ABC):
    """Creates and caches pins. Shared pins are reference-counted."""

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
        return self._get(pin, "output", lambda: self._make_output(pin, initial))

    def pwm(self, pin: int, frequency: float) -> PwmPin:
        return self._get(pin, "pwm", lambda: self._make_pwm(pin, frequency))

    def input(self, pin: int) -> InputPin:
        return self._get(pin, "input", lambda: self._make_input(pin))

    def release(self, pin: Optional[int]) -> None:
        """Drop one reference to a pin; close it when nobody uses it."""
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
    """Raspberry Pi backend using gpiozero (BCM pin numbers).

    :param hardware_pwm: use hardware PWM on GPIO12/13/18/19 (needs the
        ``rpi-hardware-pwm`` package and the PWM overlay enabled). Other EN
        pins fall back to software PWM.
    :param pwm_chip: PWM chip number: 0 on Pi 4, 2 on Pi 5 (kernel dependent).
    """

    def __init__(self, hardware_pwm: bool = False, pwm_chip: int = 0, pin_factory=None):
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
    def __init__(self, pin, initial):
        self.pin, self.value = pin, bool(initial)

    def set(self, value):
        self.value = bool(value)

    def get(self):
        return self.value


class MockPwm(PwmPin):
    def __init__(self, pin, frequency):
        self.pin, self.frequency, self.duty = pin, frequency, 0.0

    def set_duty(self, duty):
        self.duty = max(0.0, min(1.0, duty))

    def get_duty(self):
        return self.duty


class MockInput(InputPin):
    def __init__(self, pin):
        self.pin, self.level = pin, True  # nFAULT idles high (pulled up)

    def read(self):
        return self.level


class MockBackend(Backend):
    """Hardware-free backend. Inspect ``backend.pins[gpio]`` in tests."""

    @property
    def pins(self):
        return self._pins

    def _make_output(self, pin, initial):
        return MockOutput(pin, initial)

    def _make_pwm(self, pin, frequency):
        return MockPwm(pin, frequency)

    def _make_input(self, pin):
        return MockInput(pin)


def default_backend() -> Backend:
    """Return a GpiozeroBackend (on a Pi)."""
    return GpiozeroBackend()
