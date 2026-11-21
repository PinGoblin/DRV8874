"""MotorBoard: one Board A (two DRV8874 channels) and its shared lines."""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Iterator, Optional

from .backends import Backend, default_backend
from .faults import ConfigError, Fault, FaultType
from .motor import ControlMode, Motor, MotorState
from .sensors import ADS1115, CurrentSensor, MotorCurrentSensor, make_sensor

log = logging.getLogger("pingoblin_motor")

ISENSE_V_PER_A = 0.675
WAKE_TIME_S = 0.0015           # DRV8874 wake-up time from sleep is about 1 ms


class MotorBoard:
    """One Board A (dual DC motor driver).

    Pins are BCM GPIO numbers. Motor B pins are optional (single-motor use).
    Several boards can share ``sleep_pin`` (one e-stop line) and
    ``fault_pin`` (wired-OR fault line): pass the same GPIO to each board.

    :param mode: ``"ph_en"`` (default, JP1 pads 1-2) or ``"pwm"`` (JP1 2-3).
    :param logic_voltage: VLOGIC (3.3 or 5.0). Sets the board current limit:
        about 2.0 A at 3.3 V and 3.0 A at 5 V.
    :param adc: an :class:`ADS1115` for current sensing (optional).
    :param a_sense_channel, b_sense_channel: ADS1115 inputs wired to
        A_ISENSE / B_ISENSE.
    :param a_sensor, b_sensor: any :class:`CurrentSensor` instead of an
        ADS1115 channel (e.g. a different ADC, or a mock for testing).
    :param motor_names: names for motors A and B, e.g. ``("left", "right")``.
    :param a_options, b_options: extra keyword arguments for each
        :class:`Motor` (``invert``, ``min_speed_pc``, ``ramp_time``,
        ``stall_current``, ``policy`` ...). ``motor_options`` applies to both.
    :param fuse_rating: board fuse hold current in amps (3 A).
    """

    _sleep_groups: Dict[tuple, list] = {}
    _group_lock = threading.Lock()

    def __init__(self, name: str = "board", *, a_en: int, a_ph: int,
                 b_en: Optional[int] = None, b_ph: Optional[int] = None,
                 sleep_pin: Optional[int] = None, fault_pin: Optional[int] = None,
                 mode: str = "ph_en", logic_voltage: float = 3.3,
                 adc: Optional[ADS1115] = None, a_sense_channel: Optional[int] = None,
                 b_sense_channel: Optional[int] = None, sense_samples: int = 4,
                 a_sensor: Optional[CurrentSensor] = None, b_sensor: Optional[CurrentSensor] = None,
                 backend: Optional[Backend] = None, pwm_frequency: float = 1000.0,
                 motor_names=("a", "b"), motor_options: Optional[dict] = None,
                 a_options: Optional[dict] = None, b_options: Optional[dict] = None,
                 fuse_rating: float = 3.0):
        try:
            self.mode = ControlMode(mode)
        except ValueError:
            raise ConfigError("mode must be 'ph_en' or 'pwm'") from None
        if not 3.0 <= logic_voltage <= 5.5:
            raise ConfigError("logic_voltage must be 3.0-5.5 V")
        if (b_en is None) != (b_ph is None):
            raise ConfigError("give both b_en and b_ph, or neither")
        pins = [p for p in (a_en, a_ph, b_en, b_ph) if p is not None]
        if len(set(pins)) != len(pins):
            raise ConfigError("motor control pins must all be different")
        if sleep_pin in pins or fault_pin in pins:
            raise ConfigError("sleep/fault pins must not reuse a motor pin")

        if "." in name:
            raise ConfigError("board name must not contain '.'")
        self.name = name
        self.logic_voltage = logic_voltage
        self.fuse_rating = fuse_rating
        self.backend = backend or default_backend()
        self._sleep_pin, self._fault_pin = sleep_pin, fault_pin
        # Drive nSLEEP high (awake) at start; the board's pull-up also keeps it high.
        self._sleep = self.backend.output(sleep_pin, True) if sleep_pin is not None else None
        self._fault = self.backend.input(fault_pin) if fault_pin is not None else None
        if sleep_pin is not None:
            with MotorBoard._group_lock:
                MotorBoard._sleep_groups.setdefault((id(self.backend), sleep_pin), []).append(self)

        common = dict(motor_options or {})
        self.motors: Dict[str, Motor] = {}
        if len(motor_names) != 2 or motor_names[0] == motor_names[1] or any("." in n for n in motor_names):
            raise ConfigError("motor_names must be two different names without '.'")
        specs = [(motor_names[0], a_en, a_ph, a_sense_channel, a_sensor, a_options)]
        if b_en is not None:
            specs.append((motor_names[1], b_en, b_ph, b_sense_channel, b_sensor, b_options))
        for mname, en, ph, ch, src, opts in specs:
            kw = {**common, **(opts or {})}
            sensor = (MotorCurrentSensor(src, samples=sense_samples) if src is not None
                      else make_sensor(adc, ch, sense_samples))
            self.motors[mname] = Motor(
                mname, self, en, ph, mode=self.mode, backend=self.backend,
                sensor=sensor, pwm_frequency=pwm_frequency, **kw)
        self._monitor = None

    # ------------------------------------------------------------ properties
    @property
    def current_limit(self) -> float:
        """Driver current limit per motor (amps), set by VLOGIC on the board."""
        vref = self.logic_voltage * 10.0 / 25.0          # 15k / 10k divider
        return vref / ISENSE_V_PER_A

    @property
    def motor_a(self) -> Motor:
        return list(self.motors.values())[0]

    @property
    def motor_b(self) -> Optional[Motor]:
        vals = list(self.motors.values())
        return vals[1] if len(vals) > 1 else None

    @property
    def is_asleep(self) -> bool:
        return self._sleep is not None and not self._sleep.get()

    @property
    def fault_active(self) -> Optional[bool]:
        """True while nFAULT is low (fault or current limiting). None if not wired."""
        if self._fault is None:
            return None
        return not self._fault.read()

    @property
    def total_current(self) -> Optional[float]:
        """Sum of last measured supply-side currents, or None without sensors."""
        vals = [m.last_isense_amps for m in self.motors.values() if m.has_sensor]
        if not vals or any(v is None for v in vals):
            return None
        return sum(vals)

    def __getitem__(self, name: str) -> Motor:
        return self.motors[name]

    def __iter__(self) -> Iterator[Motor]:
        return iter(self.motors.values())

    # ------------------------------------------------------------ commands
    def sleep(self) -> None:
        """Pull nSLEEP low: all motors on this nSLEEP line coast, near-zero current."""
        if self._sleep is None:
            raise ConfigError(f"{self.name}: no sleep_pin configured")
        for b in self._sleep_group():
            for m in b.motors.values():
                m.stop()          # EN low, so motors stay stopped after wake
        self._sleep.set(False)

    def wake(self) -> None:
        if self._sleep is not None and not self._sleep.get():
            self._sleep.set(True)
            time.sleep(WAKE_TIME_S)

    def stop_all(self) -> None:
        """Brake every motor on this board."""
        for m in self.motors.values():
            m.stop()

    def coast_all(self) -> None:
        """Coast every motor on this board."""
        for m in self.motors.values():
            m.stop()
        if self.mode is ControlMode.PWM:
            for m in self.motors.values():
                m.coast()
        elif self._sleep is not None:
            self.sleep()
            for m in self.motors.values():
                if m.fault is None:
                    m._state = MotorState.COASTING
        else:
            log.warning("%s: coast needs sleep_pin in PH/EN mode; motors braked", self.name)

    def start_monitor(self, interval: float = 0.05, on_fault=None):
        """Start a background fault monitor for this board alone."""
        from .monitor import FaultMonitor
        if self._monitor is None:
            self._monitor = FaultMonitor([self], interval=interval)
            if on_fault:
                self._monitor.add_fault_handler(on_fault)
            self._monitor.start()
        return self._monitor

    def stop_monitor(self) -> None:
        if self._monitor is not None:
            self._monitor.stop()
            self._monitor = None

    def close(self) -> None:
        """Stop the monitor, brake all motors and release every pin."""
        self.stop_monitor()
        for m in self.motors.values():
            m.close()
        if self._sleep_pin is not None:
            with MotorBoard._group_lock:
                grp = MotorBoard._sleep_groups.get((id(self.backend), self._sleep_pin), [])
                if self in grp:
                    grp.remove(self)
        self.backend.release(self._sleep_pin)
        self.backend.release(self._fault_pin)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self) -> str:
        return f"<MotorBoard {self.name} {self.mode.value} motors={list(self.motors)}>"

    # ------------------------------------------------------------ internals
    def _sleep_group(self):
        if self._sleep_pin is None:
            return [self]
        with MotorBoard._group_lock:
            return list(MotorBoard._sleep_groups.get((id(self.backend), self._sleep_pin), [self]))

    def _ensure_awake(self) -> None:
        self.wake()

    def _coast_request(self, motor: Motor) -> bool:
        """PH/EN-mode coast: sleep the line only if every other motor on it is idle."""
        if self._sleep is None:
            return False
        for b in self._sleep_group():
            for m in b.motors.values():
                if m is not motor and m.is_running:
                    return False
        self._sleep.set(False)
        return True

    def _report_board_fault(self, fault: Fault) -> None:
        """Deliver a board-level fault to every motor on the board."""
        for m in self.motors.values():
            m._report_fault(Fault(fault.type, fault.message, self.name, m.name, fault.value, fault.timestamp))
