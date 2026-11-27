"""[`MotorBoard`][pingoblin_motor.board.MotorBoard]: one PinGoblin DRV8874 board (two motor channels) and its shared lines."""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Iterator, Optional

from .backends import Backend, default_backend
from .faults import ConfigError, Fault, FaultType
from .motor import ControlMode, Motor, MotorState
from .sensors import CurrentSensor, MotorCurrentSensor, make_sensor

_log = logging.getLogger("pingoblin_motor")

ISENSE_V_PER_A = 0.675
"""PinGoblin DRV8874 ISENSE gain: 0.675 V per amp."""
VREF_V = 1.24 * (1 + 10.0 / 15.0)
"""PinGoblin DRV8874 current-limit reference: a TLV431 set to about 2.07 V, independent of VLOGIC."""
WAKE_TIME_S = 0.0015           # DRV8874 wake-up time from sleep is about 1 ms
RELATCH_TIME_S = 0.0015        # nSLEEP low time at start-up; DRV8874 tSLEEP is 1 ms max
"""Seconds to wait after waking the drivers (the DRV8874 needs about 1 ms)."""


class MotorBoard:
    """One PinGoblin DRV8874 dual DC motor driver board.

    Pins are BCM GPIO numbers. Motor B is optional. Boards work as context managers and
    close on exit.

    Several boards can share one `sleep_pin` (one e-stop line). Each board needs its
    **own** `fault_pin`: a shared fault line overloads the nFAULT outputs and hides which
    board faulted, so a `fault_pin` already used by another open board is rejected.

    Example:
        ```python
        from pingoblin_motor import MotorBoard

        with MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6,
                        sleep_pin=26, fault_pin=19) as board:
            board.start_monitor(on_fault=print)
            board.motor_a.forward(60, duration=2, wait=True)
        ```
    """

    _sleep_groups: Dict[tuple, list] = {}
    _fault_users: Dict[tuple, "MotorBoard"] = {}
    _group_lock = threading.Lock()

    def __init__(self, name: str = "board", *, a_en: int, a_ph: int,
                 b_en: Optional[int] = None, b_ph: Optional[int] = None,
                 sleep_pin: Optional[int] = None, fault_pin: Optional[int] = None,
                 mode: str = "ph_en", logic_voltage: float = 3.3,
                 adc: Optional[object] = None, a_sense_channel: Optional[int] = None,
                 b_sense_channel: Optional[int] = None, sense_samples: int = 4,
                 a_sensor: Optional[CurrentSensor] = None, b_sensor: Optional[CurrentSensor] = None,
                 backend: Optional[Backend] = None, pwm_frequency: float = 1000.0,
                 motor_names=("a", "b"), motor_options: Optional[dict] = None,
                 a_options: Optional[dict] = None, b_options: Optional[dict] = None,
                 fuse_rating: float = 3.0, supply_voltage: Optional[float] = None):
        """
        Args:
            name: Board name, used in `"board.motor"` addresses. Must not contain `.`.
            a_en: GPIO for A_EN (J3 pin 3).
            a_ph: GPIO for A_PH (J3 pin 4).
            b_en: GPIO for B_EN (J3 pin 5), or `None` for a single motor.
            b_ph: GPIO for B_PH (J3 pin 6), or `None`.
            sleep_pin: GPIO for nSLEEP (J3 pin 9), or `None`. The board pulls nSLEEP high, so
                the drivers are awake without it. Needed to coast in PH/EN mode and for
                [`sleep()`][pingoblin_motor.board.MotorBoard.sleep]. Several boards may share it.
            fault_pin: GPIO for nFAULT (J3 pin 10), or `None`. Needed for stall detection
                without a current sensor. Must be a different GPIO for each board.
            mode: `"ph_en"` (JP1 open, default) or `"pwm"` (JP1 bridged).
            logic_voltage: VLOGIC (V), 3.0–5.5. Checked for range only: the current limit is
                fixed at about 3 A whatever the logic voltage.
            adc: A `pingoblin_ads1115.ADS1115` for current sensing, created with `rate=860`.
                See [`ADS1115Channel`][pingoblin_motor.sensors.ADS1115Channel].
            a_sense_channel: ADS1115 input wired to A_ISENSE.
            b_sense_channel: ADS1115 input wired to B_ISENSE.
            sense_samples: Readings averaged per current measurement.
            a_sensor: Any [`CurrentSensor`][pingoblin_motor.sensors.CurrentSensor] for motor A,
                instead of an ADS1115 channel.
            b_sensor: The same for motor B.
            backend: Pin [`Backend`][pingoblin_motor.backends.Backend]. Default:
                [`GpiozeroBackend`][pingoblin_motor.backends.GpiozeroBackend].
            pwm_frequency: PWM frequency (Hz).
            motor_names: Names for motors A and B, for example `("left", "right")`.
            motor_options: Keyword arguments for both [`Motor`][pingoblin_motor.motor.Motor]s.
            a_options: Keyword arguments for motor A only (override `motor_options`).
            b_options: Keyword arguments for motor B only.
            fuse_rating: The board's continuous current rating (A), for `BOARD_OVERLOAD`.
                The on-board 4 A fast-acting (high I2t) fuse allows 3 A continuously.
            supply_voltage: Motor supply voltage (V), 6–30, or `None`. Required when a motor
                is given `motor_voltage`: the library then limits that motor's PWM duty so the
                average voltage across it does not exceed its rating.

        Raises:
            ConfigError: Invalid mode, voltage, names or pins, or a `fault_pin` already used
                by another open board.
        """
        try:
            self.mode = ControlMode(mode)
        except ValueError:
            raise ConfigError("mode must be 'ph_en' or 'pwm'") from None
        if not 3.0 <= logic_voltage <= 5.5:
            raise ConfigError("logic_voltage must be 3.0-5.5 V")
        if supply_voltage is not None and not 6.0 <= supply_voltage <= 30.0:
            raise ConfigError("supply_voltage must be 6-30 V")
        if supply_voltage is None and any("motor_voltage" in (o or {})
                                          for o in (motor_options, a_options, b_options)):
            raise ConfigError("motor_voltage needs supply_voltage on the board")
        if (b_en is None) != (b_ph is None):
            raise ConfigError("give both b_en and b_ph, or neither")
        pins = [p for p in (a_en, a_ph, b_en, b_ph) if p is not None]
        if len(set(pins)) != len(pins):
            raise ConfigError("motor control pins must all be different")
        if sleep_pin in pins or fault_pin in pins:
            raise ConfigError("sleep/fault pins must not reuse a motor pin")

        if "." in name:
            raise ConfigError("board name must not contain '.'")
        backend = backend or default_backend()
        if fault_pin is not None:
            with MotorBoard._group_lock:
                other = MotorBoard._fault_users.get((id(backend), fault_pin))
            if other is not None:
                raise ConfigError(f"fault_pin {fault_pin} is already used by board '{other.name}': "
                                  "give each board its own nFAULT line")
        self.name = name
        self.logic_voltage = logic_voltage
        self.supply_voltage = supply_voltage
        self.fuse_rating = fuse_rating
        self.backend = backend
        self._sleep_pin, self._fault_pin = sleep_pin, fault_pin
        # Start-up re-latch: the DRV8874 samples PMODE when it wakes. If VLOGIC rose slowly,
        # it may have sampled PMODE mid-ramp. Holding nSLEEP low for longer than tSLEEP and
        # then releasing it makes the drivers sample PMODE again with VLOGIC settled. Skip the
        # pulse when another board already drives this nSLEEP line, so its motors keep running.
        self._sleep = None
        if sleep_pin is not None:
            with MotorBoard._group_lock:
                first = not MotorBoard._sleep_groups.get((id(self.backend), sleep_pin))
            self._sleep = self.backend.output(sleep_pin, not first)
            if first:
                time.sleep(RELATCH_TIME_S)
                self._sleep.set(True)
                time.sleep(WAKE_TIME_S)
        self._fault = self.backend.input(fault_pin) if fault_pin is not None else None
        with MotorBoard._group_lock:
            if sleep_pin is not None:
                MotorBoard._sleep_groups.setdefault((id(self.backend), sleep_pin), []).append(self)
            if fault_pin is not None:
                MotorBoard._fault_users[(id(self.backend), fault_pin)] = self

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
        """Driver current limit per motor (A): about 3 A, fixed on the board.

        ITRIP = VREF / 0.675 V/A, with VREF ≈ 2.07 V from an on-board reference.
        """
        return VREF_V / ISENSE_V_PER_A

    @property
    def motor_a(self) -> Motor:
        """The first [`Motor`][pingoblin_motor.motor.Motor] (J4)."""
        return list(self.motors.values())[0]

    @property
    def motor_b(self) -> Optional[Motor]:
        """The second [`Motor`][pingoblin_motor.motor.Motor] (J5), or `None` on a single-motor setup."""
        vals = list(self.motors.values())
        return vals[1] if len(vals) > 1 else None

    @property
    def is_asleep(self) -> bool:
        """`True` while nSLEEP is driven low."""
        return self._sleep is not None and not self._sleep.get()

    @property
    def fault_active(self) -> Optional[bool]:
        """`True` while nFAULT is low (a fault, or a driver current-limiting).
        `None` if `fault_pin` isn't wired.
        """
        if self._fault is None:
            return None
        return not self._fault.read()

    @property
    def total_current(self) -> Optional[float]:
        """Sum of the motors' last supply-side current readings (A).

        `None` unless every motor has a sensor and has been read at least once.
        """
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
        """Pull nSLEEP low: every motor on this nSLEEP line coasts and the drivers draw almost no current.

        All motors on the line are stopped first, so they stay stopped when the board wakes.

        Raises:
            ConfigError: No `sleep_pin` configured.
        """
        if self._sleep is None:
            raise ConfigError(f"{self.name}: no sleep_pin configured")
        for b in self._sleep_group():
            for m in b.motors.values():
                m.stop()          # EN low, so motors stay stopped after wake
        self._sleep.set(False)

    def wake(self) -> None:
        """Drive nSLEEP high and wait for the drivers to wake (about 1.5 ms). Run commands wake the board automatically."""
        if self._sleep is not None and not self._sleep.get():
            self._sleep.set(True)
            time.sleep(WAKE_TIME_S)

    def stop_all(self) -> None:
        """Brake every motor on this board."""
        for m in self.motors.values():
            m.stop()

    def coast_all(self) -> None:
        """Coast every motor on this board.

        In PH/EN mode this sleeps the board, so it needs `sleep_pin`. Without one the motors brake.
        """
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
            _log.warning("%s: coast needs sleep_pin in PH/EN mode; motors braked", self.name)

    def start_monitor(self, interval: float = 0.05, on_fault=None):
        """Start a background fault monitor for this board alone.

        When the board joins a [`MotorChain`][pingoblin_motor.chain.MotorChain], the chain's
        monitor takes over.

        Args:
            interval: Seconds between checks.
            on_fault: Optional `handler(fault)` called for every fault.

        Returns:
            The running [`FaultMonitor`][pingoblin_motor.monitor.FaultMonitor].
        """
        from .monitor import FaultMonitor
        if self._monitor is None:
            self._monitor = FaultMonitor([self], interval=interval)
            if on_fault:
                self._monitor.add_fault_handler(on_fault)
            self._monitor.start()
        return self._monitor

    def stop_monitor(self) -> None:
        """Stop the board's fault monitor, if running."""
        if self._monitor is not None:
            self._monitor.stop()
            self._monitor = None

    def close(self) -> None:
        """Stop the monitor, brake every motor and release every pin."""
        self.stop_monitor()
        for m in self.motors.values():
            m.close()
        with MotorBoard._group_lock:
            if self._sleep_pin is not None:
                grp = MotorBoard._sleep_groups.get((id(self.backend), self._sleep_pin), [])
                if self in grp:
                    grp.remove(self)
            key = (id(self.backend), self._fault_pin)
            if MotorBoard._fault_users.get(key) is self:
                del MotorBoard._fault_users[key]
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
