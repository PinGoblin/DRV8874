"""[`MotorBoard`][pingoblin_motor.board.MotorBoard]: one Board A (two DRV8874 drivers) and its shared lines."""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Iterator, Optional

from .backends import Backend, default_backend
from .faults import ConfigError, Fault, FaultType
from .motor import ControlMode, HalfBridgeMotor, Motor, MotorState
from .sensors import ADS1115, CurrentSensor, MotorCurrentSensor, make_sensor

_log = logging.getLogger("pingoblin_motor")

ISENSE_V_PER_A = 0.675
"""Board A ISENSE gain: 0.675 V per amp."""
WAKE_TIME_S = 0.0015           # DRV8874 wake-up time from sleep is about 1 ms
"""Seconds to wait after waking the drivers (the DRV8874 needs about 1 ms)."""


class MotorBoard:
    """One Board A dual DC motor driver.

    Pins are BCM GPIO numbers. Motor B is optional. Boards work as context managers and
    close on exit.

    The board pulls nSLEEP low, so its drivers sleep (motors off) until `sleep_pin` is
    driven high. The library drives it high at start-up and wakes the board before every
    run command. Several boards can share one `sleep_pin` (one e-stop line). Each board
    needs its **own** `fault_pin`: a shared fault line overloads the nFAULT outputs and
    hides which board faulted, so a `fault_pin` already used by another open board is
    rejected.

    The `mode` must match the PMODE jumper JP1:

    | `mode` | JP1 | Motors | Names (default) |
    |---|---|---|---|
    | `"ph_en"` | Pads 1–2 (default) | 2 × [`Motor`][pingoblin_motor.motor.Motor] | `a`, `b` |
    | `"pwm"` | Pads 2–3 | 2 × [`Motor`][pingoblin_motor.motor.Motor] | `a`, `b` |
    | `"independent"` | All pads open | 4 × [`HalfBridgeMotor`][pingoblin_motor.motor.HalfBridgeMotor] | `a1`, `a2`, `b1`, `b2` |

    Example:
        ```python
        from pingoblin_motor import MotorBoard

        with MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6,
                        sleep_pin=26, fault_pin=19) as board:
            board.start_monitor(on_fault=print)
            board.motor_a.forward(60, duration=2, wait=True)
        ```

    Four-motor mode:
        ```python
        with MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                        mode="independent") as board:
            board["a1"].forward(50)
            board["b2"].forward(80, duration=2, wait=True)
        ```

        In this mode an input that isn't driven turns its motor **on**. `sleep_pin` is
        required: the board's pull-down on nSLEEP then keeps the drivers asleep whenever
        your program isn't holding it high. The library keeps the drivers asleep until the
        first run command, and puts them to sleep in
        [`close()`][pingoblin_motor.board.MotorBoard.close].
    """

    _sleep_groups: Dict[tuple, list] = {}
    _fault_users: Dict[tuple, "MotorBoard"] = {}
    _group_lock = threading.Lock()

    def __init__(self, name: str = "board", *, a_en: int, a_ph: int,
                 b_en: Optional[int] = None, b_ph: Optional[int] = None,
                 sleep_pin: Optional[int] = None, fault_pin: Optional[int] = None,
                 mode: str = "ph_en", logic_voltage: float = 3.3,
                 adc: Optional[ADS1115] = None, a_sense_channel: Optional[int] = None,
                 b_sense_channel: Optional[int] = None, sense_samples: int = 4,
                 a_sensor: Optional[CurrentSensor] = None, b_sensor: Optional[CurrentSensor] = None,
                 backend: Optional[Backend] = None, pwm_frequency: float = 1000.0,
                 motor_names=None, motor_options: Optional[dict] = None,
                 a_options: Optional[dict] = None, b_options: Optional[dict] = None,
                 fuse_rating: float = 3.0):
        """
        Args:
            name: Board name, used in `"board.motor"` addresses. Must not contain `.`.
            a_en: GPIO for A_EN (J3 pin 3).
            a_ph: GPIO for A_PH (J3 pin 4).
            b_en: GPIO for B_EN (J3 pin 5), or `None` for a single motor.
            b_ph: GPIO for B_PH (J3 pin 6), or `None`.
            sleep_pin: GPIO for nSLEEP (J3 pin 9). The board pulls nSLEEP low, so the motors
                only run while this pin is driven high. Pass `None` only if J3 pin 9 is linked
                to VLOGIC (pin 2); the board then can't coast in PH/EN mode or
                [`sleep()`][pingoblin_motor.board.MotorBoard.sleep]. Required in four-motor
                mode. Several boards may share it.
            fault_pin: GPIO for nFAULT (J3 pin 10), or `None`. Needed for stall detection
                without a current sensor. Must be a different GPIO for each board.
            mode: `"ph_en"` (JP1 pads 1–2, default), `"pwm"` (JP1 pads 2–3) or
                `"independent"` (JP1 all pads open: four-motor mode).
            logic_voltage: VLOGIC (V). Sets the current limit: about 2.0 A at 3.3 V and
                3.0 A at 5 V.
            adc: An [`ADS1115`][pingoblin_motor.sensors.ADS1115] for current sensing.
            a_sense_channel: ADS1115 input wired to A_ISENSE. In four-motor mode this reads
                motors `a1` and `a2` together.
            b_sense_channel: ADS1115 input wired to B_ISENSE.
            sense_samples: Readings averaged per current measurement.
            a_sensor: Any [`CurrentSensor`][pingoblin_motor.sensors.CurrentSensor] for motor A,
                instead of an ADS1115 channel.
            b_sensor: The same for motor B.
            backend: Pin [`Backend`][pingoblin_motor.backends.Backend]. Default:
                [`GpiozeroBackend`][pingoblin_motor.backends.GpiozeroBackend].
            pwm_frequency: PWM frequency (Hz).
            motor_names: Names for motors A and B, for example `("left", "right")`. In
                four-motor mode, four names for A1, A2, B1 and B2. Default: `("a", "b")`, or
                `("a1", "a2", "b1", "b2")` in four-motor mode.
            motor_options: Keyword arguments for every motor.
            a_options: Keyword arguments for motor A only (override `motor_options`). In
                four-motor mode they apply to A1 and A2.
            b_options: Keyword arguments for motor B only (B1 and B2 in four-motor mode).
            fuse_rating: Board fuse hold current (A), for `BOARD_OVERLOAD`.

        Raises:
            ConfigError: Invalid mode, voltage, names or pins, four-motor mode without
                `sleep_pin`, or a `fault_pin` already used by another open board.
        """
        try:
            self.mode = ControlMode(mode)
        except ValueError:
            raise ConfigError("mode must be 'ph_en', 'pwm' or 'independent'") from None
        four = self.mode is ControlMode.INDEPENDENT
        if four and sleep_pin is None:
            raise ConfigError("four-motor mode needs sleep_pin: an undriven input turns its motor on, "
                              "so the drivers must sleep whenever the program isn't running")
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
        backend = backend or default_backend()
        if fault_pin is not None:
            with MotorBoard._group_lock:
                other = MotorBoard._fault_users.get((id(backend), fault_pin))
            if other is not None:
                raise ConfigError(f"fault_pin {fault_pin} is already used by board '{other.name}': "
                                  "give each board its own nFAULT line")
        self.name = name
        self.logic_voltage = logic_voltage
        self.fuse_rating = fuse_rating
        self.backend = backend
        self._sleep_pin, self._fault_pin = sleep_pin, fault_pin
        # The board pulls nSLEEP low. Drive it high (awake) at start, except in four-motor
        # mode: stay asleep until the first run, so the inputs are set first.
        self._sleep = self.backend.output(sleep_pin, not four) if sleep_pin is not None else None
        self._fault = self.backend.input(fault_pin) if fault_pin is not None else None
        with MotorBoard._group_lock:
            if sleep_pin is not None:
                MotorBoard._sleep_groups.setdefault((id(self.backend), sleep_pin), []).append(self)
            if fault_pin is not None:
                MotorBoard._fault_users[(id(self.backend), fault_pin)] = self

        common = dict(motor_options or {})
        self.motors: Dict[str, Motor] = {}
        self._driver_sensors: Dict[str, Optional[MotorCurrentSensor]] = {}
        self._driver_amps: Dict[str, Optional[float]] = {}
        n = 4 if four else 2
        if motor_names is None:
            motor_names = ("a1", "a2", "b1", "b2") if four else ("a", "b")
        motor_names = tuple(motor_names)
        if len(motor_names) != n or len(set(motor_names)) != n or any("." in m for m in motor_names):
            raise ConfigError(f"motor_names must be {n} different names without '.'")
        if four:
            drivers = [("a", a_en, a_ph, a_sense_channel, a_sensor, a_options)]
            if b_en is not None:
                drivers.append(("b", b_en, b_ph, b_sense_channel, b_sensor, b_options))
            for i, (drv, p1, p2, ch, src, opts) in enumerate(drivers):
                self._driver_sensors[drv] = (MotorCurrentSensor(src, samples=sense_samples) if src is not None
                                             else make_sensor(adc, ch, sense_samples))
                self._driver_amps[drv] = None
                kw = {**common, **(opts or {})}
                for out, pin in ((1, p1), (2, p2)):
                    mname = motor_names[2 * i + out - 1]
                    self.motors[mname] = HalfBridgeMotor(
                        mname, self, pin, driver=drv, output=out, backend=self.backend,
                        pwm_frequency=pwm_frequency, **kw)
            self._monitor = None
            return
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
        """Driver current limit per motor (A), set on the board from VLOGIC.

        VREF = 0.4 × VLOGIC and ITRIP = VREF / 0.675 V/A.
        """
        vref = self.logic_voltage * 10.0 / 25.0          # 15k / 10k divider
        return vref / ISENSE_V_PER_A

    @property
    def motor_a(self) -> Motor:
        """The first [`Motor`][pingoblin_motor.motor.Motor] (J4).

        Raises:
            ConfigError: In four-motor mode. Use `board["a1"]`, `board["a2"]` and so on.
        """
        self._two_motor_only()
        return list(self.motors.values())[0]

    @property
    def motor_b(self) -> Optional[Motor]:
        """The second [`Motor`][pingoblin_motor.motor.Motor] (J5), or `None` on a single-motor setup.

        Raises:
            ConfigError: In four-motor mode. Use `board["b1"]`, `board["b2"]` and so on.
        """
        self._two_motor_only()
        vals = list(self.motors.values())
        return vals[1] if len(vals) > 1 else None

    @property
    def is_four_motor(self) -> bool:
        """`True` in four-motor mode (`mode="independent"`)."""
        return self.mode is ControlMode.INDEPENDENT

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

        `None` unless every motor (every driver, in four-motor mode) has a sensor and has
        been read at least once.
        """
        if self.is_four_motor:
            vals = list(self._driver_amps.values())
            if not vals or any(v is None for v in vals) or any(s is None for s in self._driver_sensors.values()):
                return None
            return sum(vals)
        vals = [m.last_isense_amps for m in self.motors.values() if m.has_sensor]
        if not vals or any(v is None for v in vals):
            return None
        return sum(vals)

    def __getitem__(self, name: str) -> Motor:
        return self.motors[name]

    def __iter__(self) -> Iterator[Motor]:
        return iter(self.motors.values())

    # ------------------------------------------------------------ commands
    def driver_current(self, driver: str) -> float:
        """Read one driver's ISENSE now (four-motor mode).

        In four-motor mode ISENSE carries the combined current of both motors on that
        driver (A1 + A2, or B1 + B2), averaged over the PWM cycle: the current the pair draws
        from the supply.

        Args:
            driver: `"a"` (U1, J4) or `"b"` (U2, J5).

        Returns:
            Current (A).

        Raises:
            ConfigError: Not in four-motor mode, unknown driver, or no sensor for it.
            SensorError: The reading failed.
        """
        if not self.is_four_motor:
            raise ConfigError("driver_current() is for four-motor mode; use motor.current")
        if driver not in self._driver_sensors:
            raise ConfigError(f"unknown driver '{driver}'")
        sensor = self._driver_sensors[driver]
        if sensor is None:
            raise ConfigError(f"{self.name}: no current sensor for driver {driver}")
        amps = sensor.read_isense_amps()
        self._driver_amps[driver] = amps
        return amps

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

        In PH/EN and four-motor modes this sleeps the board, so it needs `sleep_pin`. Without
        one the motors brake.
        """
        for m in self.motors.values():
            m.stop()
        if self.mode is ControlMode.PWM:
            for m in self.motors.values():
                m.coast()
            return
        if self._sleep is not None:
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
        """Stop the monitor, brake every motor and release every pin.

        In four-motor mode the drivers are put to sleep first, so the motors don't start when
        the inputs are released.
        """
        self.stop_monitor()
        if self.is_four_motor and self._sleep is not None:
            for m in self.motors.values():
                m.stop()
            self._sleep.set(False)
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
    def _two_motor_only(self) -> None:
        if self.is_four_motor:
            raise ConfigError("four-motor mode: use board['a1'], board['a2'], board['b1'], board['b2']")

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
