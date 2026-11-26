"""The [`Motor`][pingoblin_motor.motor.Motor] class: one brushed DC motor on one DRV8874 channel."""
from __future__ import annotations

import enum
import logging
import threading
import time
from typing import Callable, List, Optional, TYPE_CHECKING

from .faults import (ConfigError, Fault, FaultAction, FaultPolicy, FaultType,
                     MotorFaultError, SensorError)
from .sensors import MotorCurrentSensor

if TYPE_CHECKING:  # pragma: no cover
    from .board import MotorBoard

_log = logging.getLogger("pingoblin_motor")


class Direction(enum.Enum):
    """Direction of rotation.

    "Forward" follows the board's (and TI's) convention: PH high, OUT1 positive. Which way the shaft
    turns depends on the wiring; use `invert=True` to swap.

    Attributes:
        FORWARD: PH high (OUT1 positive).
        REVERSE: PH low (OUT2 positive).
    """

    FORWARD = "forward"
    REVERSE = "reverse"


class MotorState(enum.Enum):
    """What a motor is doing.

    Attributes:
        STOPPED: Braked: both outputs low. Stops quickly and resists turning.
        COASTING: Outputs open. Spins down freely.
        RUNNING: Driven.
        FAULT: A latched fault. Call `clear_fault()`.
    """

    STOPPED = "stopped"      #: braked (outputs shorted low): stops quickly, holds lightly
    COASTING = "coasting"    #: outputs open: spins down freely
    RUNNING = "running"
    FAULT = "fault"          #: latched fault; call clear_fault()


class ControlMode(enum.Enum):
    """Control mode, set by the PMODE jumper JP1 on the board.

    Attributes:
        PH_EN: Default (JP1 open): EN = speed PWM, PH = direction.
        PWM: JP1 bridged: IN1 / IN2. Allows per-motor coast.
    """

    PH_EN = "ph_en"   #: default (JP1 open): EN = speed PWM, PH = direction
    PWM = "pwm"       #: JP1 bridged: IN1/IN2


class Motor:
    """One brushed DC motor.

    Create motors through [`MotorBoard`][pingoblin_motor.board.MotorBoard], not directly.
    Pass options to both motors with `motor_options=`, or to one with `a_options=` /
    `b_options=`.

    Speeds are percentages, 0–100. [`run()`][pingoblin_motor.motor.Motor.run] takes a signed
    speed: positive is forward, negative is reverse. Commands are thread-safe.

    Example:
        ```python
        m = board.motor_a
        m.forward(60, duration=2, wait=True)   # 60 % for 2 s, then brake
        m.reverse(40)
        m.speed_pc = 80                        # change speed while running
        print(m.current)                       # amps, if a sensor is fitted
        m.coast()
        ```
    """

    def __init__(self, name: str, board: "MotorBoard", en_pin: int, ph_pin: int, *,
                 mode: ControlMode, backend, sensor: Optional[MotorCurrentSensor] = None,
                 invert: bool = False, pwm_frequency: float = 1000.0,
                 min_speed_pc: float = 0.0, ramp_time: float = 0.0, reverse_delay: float = 0.1,
                 stall_current: Optional[float] = None, stall_time: float = 0.5,
                 start_grace: float = 0.3, open_load_current: float = 0.03,
                 open_load_time: float = 1.0, continuous_current: float = 1.5,
                 overload_time: float = 5.0, policy: Optional[FaultPolicy] = None,
                 motor_voltage: Optional[float] = None):
        """
        Args:
            name: Motor name within its board, for example `"a"` or `"left"`.
            board: The owning [`MotorBoard`][pingoblin_motor.board.MotorBoard].
            en_pin: GPIO for EN (PH/EN mode) or IN1 (PWM mode).
            ph_pin: GPIO for PH (PH/EN mode) or IN2 (PWM mode).
            mode: The board's [`ControlMode`][pingoblin_motor.motor.ControlMode].
            backend: The [`Backend`][pingoblin_motor.backends.Backend] that creates the pins.
            sensor: Optional [`MotorCurrentSensor`][pingoblin_motor.sensors.MotorCurrentSensor].
            invert: Swap forward and reverse (instead of swapping the motor wires).
            pwm_frequency: PWM frequency (Hz).
            min_speed_pc: Non-zero speeds below this are raised to it, to overcome the motor's
                deadband. 0 disables.
            ramp_time: Seconds to ramp from 0 to 100 %. Speed changes ramp proportionally.
                0 = instant.
            reverse_delay: Seconds of braking before a direction change while running.
            stall_current: Motor current (A) treated as a stall. Default: 80 % of the board's
                current limit.
            stall_time: Seconds the stall condition must last.
            start_grace: Seconds after a start or speed change during which stall and open-load
                checks are skipped (start-up surge).
            open_load_current: Current (A) below which a driven motor counts as disconnected.
            open_load_time: Seconds the open-load condition must last.
            continuous_current: Current (A) the motor may carry continuously.
            overload_time: Seconds above `continuous_current` before an overload fault.
            policy: [`FaultPolicy`][pingoblin_motor.faults.FaultPolicy] for this motor.
            motor_voltage: The motor's rated voltage (V), or `None`. When it is below the
                board's `supply_voltage`, 100 % speed is scaled to a PWM duty of
                `motor_voltage / supply_voltage`, so the motor never receives more than its
                rated average voltage. Requires `supply_voltage` on the board.

        Raises:
            ConfigError: An option is out of range.
        """
        if not 0 <= min_speed_pc < 100:
            raise ConfigError("min_speed_pc must be 0-99")
        if ramp_time < 0 or reverse_delay < 0:
            raise ConfigError("ramp_time and reverse_delay must be >= 0")
        supply = getattr(board, "supply_voltage", None)
        if motor_voltage is not None:
            if motor_voltage <= 0:
                raise ConfigError("motor_voltage must be > 0")
            if supply is None:
                raise ConfigError("motor_voltage needs supply_voltage on the board")
        self.motor_voltage = motor_voltage
        self.max_duty = 1.0 if motor_voltage is None else min(1.0, motor_voltage / supply)
        self.name = name
        self.board = board
        self.mode = mode
        self.invert = invert
        self.min_speed_pc = float(min_speed_pc)
        self.ramp_time = float(ramp_time)
        self.reverse_delay = float(reverse_delay)
        self.sensor = sensor
        self.stall_current = stall_current if stall_current is not None else 0.8 * board.current_limit
        self.stall_time = stall_time
        self.start_grace = start_grace
        self.open_load_current = open_load_current
        self.open_load_time = open_load_time
        self.continuous_current = continuous_current
        self.overload_time = overload_time
        self.policy = policy or FaultPolicy()

        self._backend = backend
        self._en_pin, self._ph_pin = en_pin, ph_pin
        if mode is ControlMode.PH_EN:
            self._en = backend.pwm(en_pin, pwm_frequency)
            self._ph = backend.output(ph_pin, False)
        else:
            self._en = backend.pwm(en_pin, pwm_frequency)   # IN1
            self._ph = backend.pwm(ph_pin, pwm_frequency)   # IN2

        self._lock = threading.RLock()
        self._state = MotorState.STOPPED
        self._direction: Optional[Direction] = None
        self._speed_pc = 0.0            # last commanded speed (kept after stop, for start())
        self._duty = 0.0                # duty currently applied to the bridge
        self._last_change = 0.0         # monotonic time of last start/speed change
        self._timer: Optional[threading.Timer] = None
        self._done = threading.Event()
        self._done.set()
        self._ramp_cancel = threading.Event()
        self._ramp_thread: Optional[threading.Thread] = None
        self._fault: Optional[Fault] = None
        self._handlers: List[Callable[[Fault], None]] = []
        self.last_current: Optional[float] = None       # estimated motor amps
        self.last_isense_amps: Optional[float] = None   # supply-side (duty-weighted) amps
        self._apply_brake()

    # ------------------------------------------------------------ properties
    @property
    def full_name(self) -> str:
        """The motor's name including its board, for example `"front.a"`."""
        return f"{self.board.name}.{self.name}"

    @property
    def state(self) -> MotorState:
        """The current [`MotorState`][pingoblin_motor.motor.MotorState]."""
        return self._state

    @property
    def direction(self) -> Optional[Direction]:
        """Direction of the last run command, kept after a stop for
        [`start()`][pingoblin_motor.motor.Motor.start]. `None` if never run.
        """
        return self._direction

    @property
    def is_running(self) -> bool:
        """`True` while the motor is driven."""
        return self._state is MotorState.RUNNING

    @property
    def duty(self) -> float:
        """PWM duty currently applied to the bridge, 0–1. 0 when stopped."""
        return self._duty

    @property
    def running_since(self) -> float:
        """`time.monotonic()` of the last start or speed change."""
        return self._last_change

    @property
    def fault(self) -> Optional[Fault]:
        """The latched [`Fault`][pingoblin_motor.faults.Fault], or `None`."""
        return self._fault

    @property
    def has_sensor(self) -> bool:
        """`True` if the motor has a current sensor."""
        return self.sensor is not None

    @property
    def speed_pc(self) -> float:
        """Commanded speed, 0–100 %.

        Setting it while the motor runs changes the speed (ramped if `ramp_time` is set).
        Setting 0 stops the motor. Setting it while stopped stores the speed for
        [`start()`][pingoblin_motor.motor.Motor.start].

        Raises:
            ValueError: Outside 0–100.
        """
        return self._speed_pc

    @speed_pc.setter
    def speed_pc(self, value: float) -> None:
        value = self._check_speed(value)
        with self._lock:
            self._speed_pc = value
            if self.is_running:
                if value == 0:
                    self.stop()
                else:
                    self._last_change = time.monotonic()
                    self._ramp_to(self._speed_to_duty(value))

    @property
    def current(self) -> Optional[float]:
        """Motor current (A), read from the sensor now, or `None` without a sensor.

        While running, the reading is corrected for PWM duty. See
        [`read_current()`][pingoblin_motor.motor.Motor.read_current].
        """
        if self.sensor is None:
            return None
        return self.read_current()

    # ------------------------------------------------------------ commands
    def forward(self, speed_pc: float = 100.0, duration: Optional[float] = None, wait: bool = False) -> None:
        """Run forward.

        Args:
            speed_pc: Speed, 0–100 %. 0 stops the motor.
            duration: Seconds to run before braking. `None` runs until told otherwise.
            wait: With `duration`, block until the run ends.

        Raises:
            ValueError: Speed outside 0–100, or `duration` not positive.
            MotorFaultError: The motor has a latched fault.
        """
        self._run(Direction.FORWARD, speed_pc, duration, wait)

    def reverse(self, speed_pc: float = 100.0, duration: Optional[float] = None, wait: bool = False) -> None:
        """Run in reverse.

        Args:
            speed_pc: Speed, 0–100 %. 0 stops the motor.
            duration: Seconds to run before braking. `None` runs until told otherwise.
            wait: With `duration`, block until the run ends.

        Raises:
            ValueError: Speed outside 0–100, or `duration` not positive.
            MotorFaultError: The motor has a latched fault.
        """
        self._run(Direction.REVERSE, speed_pc, duration, wait)

    def run(self, speed_pc: float, duration: Optional[float] = None, wait: bool = False) -> None:
        """Run with a signed speed.

        Args:
            speed_pc: -100 to 100. Positive is forward, negative is reverse, 0 stops.
            duration: Seconds to run before braking. `None` runs until told otherwise.
            wait: With `duration`, block until the run ends.

        Raises:
            ValueError: Speed outside -100 to 100, or `duration` not positive.
            MotorFaultError: The motor has a latched fault.
        """
        if speed_pc == 0:
            self.stop()
            return
        self._run(Direction.FORWARD if speed_pc > 0 else Direction.REVERSE, abs(speed_pc), duration, wait)

    def start(self, duration: Optional[float] = None, wait: bool = False) -> None:
        """Resume the last direction and speed (forward at 100 % if never run).

        Args:
            duration: Seconds to run before braking. `None` runs until told otherwise.
            wait: With `duration`, block until the run ends.

        Raises:
            MotorFaultError: The motor has a latched fault.
        """
        direction = self._direction or Direction.FORWARD
        speed = self._speed_pc or 100.0
        self._run(direction, speed, duration, wait)

    def stop(self) -> None:
        """Brake: both outputs low. The motor stops quickly.

        Cancels any timed run or ramp. `brake()` is an alias.
        """
        with self._lock:
            self._cancel_timer()
            self._cancel_ramp()
            self._apply_brake()
            if self._state is not MotorState.FAULT:
                self._state = MotorState.STOPPED
            self._done.set()

    brake = stop
    """Alias of [`stop()`][pingoblin_motor.motor.Motor.stop]."""

    def coast(self) -> bool:
        """Let the motor spin down freely (outputs open).

        In PWM mode this is per motor. In PH/EN mode the DRV8874 can only coast by sleeping,
        which affects every motor on the same nSLEEP line (both motors on the board, and any
        board sharing the GPIO). So it coasts only if all those motors are idle. Otherwise the
        motor brakes.

        Returns:
            `True` if the motor is coasting, `False` if it had to brake instead.
        """
        with self._lock:
            self._cancel_timer()
            self._cancel_ramp()
            if self.mode is ControlMode.PWM:
                self._apply_coast()
                ok = True
            else:
                self._apply_brake()   # EN low first, so waking later is safe
                ok = self.board._coast_request(self)
                if not ok:
                    _log.warning("%s: coast not possible in PH/EN mode while other motors on the "
                                "same nSLEEP line run; braking instead", self.full_name)
            if self._state is not MotorState.FAULT:
                self._state = MotorState.COASTING if ok else MotorState.STOPPED
            self._done.set()
            return ok

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until a timed run (`duration=`) finishes.

        Args:
            timeout: Maximum seconds to wait, or `None` to wait indefinitely.

        Returns:
            `False` if the timeout expired first.
        """
        return self._done.wait(timeout)

    def read_current(self) -> float:
        """Read the sensor now and return the estimated motor current.

        Also updates `last_current` (motor amps) and `last_isense_amps` (supply-side amps).
        Below 10 % duty the raw reading is returned.

        Returns:
            Motor current (A).

        Raises:
            ConfigError: The motor has no sensor.
            SensorError: The reading failed.
        """
        if self.sensor is None:
            raise ConfigError(f"{self.full_name} has no current sensor")
        isense = self.sensor.read_isense_amps()
        duty = self._duty
        motor_amps = isense / duty if duty >= 0.1 else isense
        self.last_isense_amps, self.last_current = isense, motor_amps
        return motor_amps

    # ------------------------------------------------------------ faults
    def add_fault_handler(self, handler: Callable[[Fault], None]) -> None:
        """Call `handler(fault)` whenever a fault is reported for this motor.

        Handlers run on the monitor thread, so keep them short. Exceptions in a handler are
        logged and ignored.

        Args:
            handler: A callable taking one [`Fault`][pingoblin_motor.faults.Fault].
        """
        self._handlers.append(handler)

    def clear_fault(self) -> None:
        """Clear a latched fault so the motor can run again. The motor stays stopped."""
        with self._lock:
            self._fault = None
            if self._state is MotorState.FAULT:
                self._state = MotorState.STOPPED

    def _report_fault(self, fault: Fault) -> None:
        """Called by the fault monitor. Applies the policy, latches, notifies."""
        action = self.policy.action_for(fault.type)
        with self._lock:
            if action is FaultAction.BRAKE:
                self.stop()
            elif action is FaultAction.COAST:
                self.coast()
            elif action is FaultAction.SLEEP:
                self.stop()
                if self.board._sleep is not None:   # no sleep pin: brake only
                    self.board.sleep()
            if self.policy.latches(fault.type):
                self._fault = fault
                self._state = MotorState.FAULT
        _log.warning("%s", fault)
        for h in list(self._handlers):
            try:
                h(fault)
            except Exception:  # never let a user callback kill the monitor
                _log.exception("fault handler failed")

    # ------------------------------------------------------------ internals
    def _check_speed(self, value: float) -> float:
        value = float(value)
        if not 0 <= value <= 100:
            raise ValueError(f"speed_pc must be 0-100, got {value}")
        return value

    def _speed_to_duty(self, speed_pc: float) -> float:
        if speed_pc <= 0:
            return 0.0
        speed_pc = max(speed_pc, self.min_speed_pc)
        return speed_pc / 100.0 * self.max_duty

    def _run(self, direction: Direction, speed_pc: float, duration, wait) -> None:
        speed_pc = self._check_speed(speed_pc)
        if duration is not None and duration <= 0:
            raise ValueError("duration must be > 0")
        with self._lock:
            if self._fault is not None:
                raise MotorFaultError(self._fault)
            self._cancel_timer()
            if speed_pc == 0:
                self._speed_pc = 0.0
                self.stop()
                return
            self.board._ensure_awake()
            reversing = self.is_running and self._direction is not direction and self._duty > 0
            if reversing:
                self._cancel_ramp()
                self._apply_brake()
                if self.reverse_delay:
                    time.sleep(self.reverse_delay)
            self._direction, self._speed_pc = direction, speed_pc
            self._state = MotorState.RUNNING
            self._last_change = time.monotonic()
            self._done.clear()
            target = self._speed_to_duty(speed_pc)
            if reversing or self._duty == 0:
                self._duty = 0.0
            self._ramp_to(target)
            if duration is not None:
                self._timer = threading.Timer(duration, self._timed_stop)
                self._timer.daemon = True
                self._timer.start()
            else:
                self._done.set()
        if wait and duration is not None:
            self._done.wait()

    def _timed_stop(self) -> None:
        with self._lock:
            self._timer = None
            if self.is_running:
                self._cancel_ramp()
                self._apply_brake()
                self._state = MotorState.STOPPED
            self._done.set()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _cancel_ramp(self) -> None:
        # The worker re-checks this event while holding the motor lock, so no
        # further duty change can land after this point. No join (avoids
        # deadlock with a worker waiting for the lock we hold).
        self._ramp_cancel.set()
        self._ramp_thread = None

    def _ramp_to(self, target: float) -> None:
        self._cancel_ramp()
        if self.ramp_time <= 0 or abs(target - self._duty) < 1e-6:
            self._apply_drive(target)
            return
        self._ramp_cancel = cancel = threading.Event()
        start, step_s = self._duty, 0.02
        steps = max(1, int(abs(target - start) * self.ramp_time / step_s))

        def worker():
            for i in range(1, steps + 1):
                if cancel.wait(step_s):
                    return
                with self._lock:
                    if cancel.is_set():
                        return
                    self._apply_drive(start + (target - start) * i / steps)

        self._ramp_thread = threading.Thread(target=worker, name=f"ramp-{self.full_name}", daemon=True)
        self._ramp_thread.start()

    # Pin level control. PH/EN: forward = PH high (OUT1 positive). PWM mode uses slow decay
    # (off-time = brake) so speed response matches PH/EN mode.
    def _apply_drive(self, duty: float) -> None:
        duty = max(0.0, min(1.0, duty))
        self._duty = duty
        fwd = (self._direction is Direction.FORWARD) != self.invert
        if self.mode is ControlMode.PH_EN:
            self._ph.set(fwd)
            self._en.set_duty(duty)
        else:  # IN1=en, IN2=ph. Forward: IN1 high, IN2 low (OUT1 positive).
            if fwd:
                self._en.set_duty(1.0)
                self._ph.set_duty(1.0 - duty)
            else:
                self._ph.set_duty(1.0)
                self._en.set_duty(1.0 - duty)

    def _apply_brake(self) -> None:
        self._duty = 0.0
        if self.mode is ControlMode.PH_EN:
            self._en.set_duty(0.0)
        else:
            self._en.set_duty(1.0)
            self._ph.set_duty(1.0)

    def _apply_coast(self) -> None:
        self._duty = 0.0
        self._en.set_duty(0.0)
        if self.mode is ControlMode.PWM:
            self._ph.set_duty(0.0)

    def close(self) -> None:
        """Brake and release the motor's pins."""
        try:
            self.stop()
        finally:
            self._backend.release(self._en_pin)
            self._backend.release(self._ph_pin)

    def __repr__(self) -> str:
        d = self._direction.value if self._direction else "-"
        return f"<Motor {self.full_name} {self._state.value} {d} {self._speed_pc:.0f}%>"
