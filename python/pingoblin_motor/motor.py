"""The Motor class: one brushed DC motor on one DRV8874 channel."""
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

log = logging.getLogger("pingoblin_motor")


class Direction(enum.Enum):
    FORWARD = "forward"
    REVERSE = "reverse"


class MotorState(enum.Enum):
    STOPPED = "stopped"      #: braked (outputs shorted low): stops quickly, holds lightly
    COASTING = "coasting"    #: outputs open: spins down freely
    RUNNING = "running"
    FAULT = "fault"          #: latched fault; call clear_fault()


class ControlMode(enum.Enum):
    PH_EN = "ph_en"   #: default (JP1 pads 1-2): EN = speed PWM, PH = direction
    PWM = "pwm"       #: JP1 pads 2-3: IN1/IN2


class Motor:
    """One brushed DC motor.

    Create motors through :class:`~pingoblin_motor.MotorBoard`, not directly.

    Speeds are percentages, 0-100. ``run()`` takes a signed speed:
    positive = forward, negative = reverse.

    "Forward" follows the manual (PH low, OUT2 positive). If your motor turns
    the wrong way, pass ``invert=True`` rather than swapping wires.

    :param min_speed_pc: speeds between 0 and this value are raised to it
        (many motors don't turn below 15-25 %). 0 disables.
    :param ramp_time: seconds to ramp from 0 to 100 % (soft start/stop of
        speed changes). 0 = instant.
    :param reverse_delay: brake time before a direction change at speed.
    :param stall_current: motor amps treated as a stall. Default 80 % of the
        board current limit.
    :param stall_time: how long the stall condition must last.
    :param start_grace: ignore stall/open-load checks for this long after a
        start or speed change (start-up surge).
    :param open_load_current: amps below which a running motor counts as disconnected.
    :param open_load_time: how long the open-load condition must last.
    :param continuous_current: amps the motor/driver may carry continuously.
    :param overload_time: how long above ``continuous_current`` before OVERLOAD.
    :param policy: :class:`FaultPolicy`, how to react to each fault.
    """

    def __init__(self, name: str, board: "MotorBoard", en_pin: int, ph_pin: int, *,
                 mode: ControlMode, backend, sensor: Optional[MotorCurrentSensor] = None,
                 invert: bool = False, pwm_frequency: float = 1000.0,
                 min_speed_pc: float = 0.0, ramp_time: float = 0.0, reverse_delay: float = 0.1,
                 stall_current: Optional[float] = None, stall_time: float = 0.5,
                 start_grace: float = 0.3, open_load_current: float = 0.03,
                 open_load_time: float = 1.0, continuous_current: float = 1.5,
                 overload_time: float = 5.0, policy: Optional[FaultPolicy] = None):
        if not 0 <= min_speed_pc < 100:
            raise ConfigError("min_speed_pc must be 0-99")
        if ramp_time < 0 or reverse_delay < 0:
            raise ConfigError("ramp_time and reverse_delay must be >= 0")
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
        return f"{self.board.name}.{self.name}"

    @property
    def state(self) -> MotorState:
        return self._state

    @property
    def direction(self) -> Optional[Direction]:
        """Direction of the last run command (kept after stop for ``start()``)."""
        return self._direction

    @property
    def is_running(self) -> bool:
        return self._state is MotorState.RUNNING

    @property
    def duty(self) -> float:
        """PWM duty currently applied (0-1)."""
        return self._duty

    @property
    def running_since(self) -> float:
        return self._last_change

    @property
    def fault(self) -> Optional[Fault]:
        """The latched fault, or None."""
        return self._fault

    @property
    def has_sensor(self) -> bool:
        return self.sensor is not None

    @property
    def speed_pc(self) -> float:
        """Commanded speed, 0-100 %. Setting it while running changes speed."""
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
        """Motor current in amps (reads the sensor), or None without a sensor.

        While running, this is corrected for PWM duty. When stopped it is 0.
        """
        if self.sensor is None:
            return None
        return self.read_current()

    # ------------------------------------------------------------ commands
    def forward(self, speed_pc: float = 100.0, duration: Optional[float] = None, wait: bool = False) -> None:
        """Run forward at ``speed_pc`` %. With ``duration``, stop (brake) after that many seconds."""
        self._run(Direction.FORWARD, speed_pc, duration, wait)

    def reverse(self, speed_pc: float = 100.0, duration: Optional[float] = None, wait: bool = False) -> None:
        """Run in reverse at ``speed_pc`` %."""
        self._run(Direction.REVERSE, speed_pc, duration, wait)

    def run(self, speed_pc: float, duration: Optional[float] = None, wait: bool = False) -> None:
        """Signed speed: +50 = forward at 50 %, -50 = reverse at 50 %, 0 = stop."""
        if speed_pc == 0:
            self.stop()
            return
        self._run(Direction.FORWARD if speed_pc > 0 else Direction.REVERSE, abs(speed_pc), duration, wait)

    def start(self, duration: Optional[float] = None, wait: bool = False) -> None:
        """Resume the last direction and speed (forward 100 % if never run)."""
        direction = self._direction or Direction.FORWARD
        speed = self._speed_pc or 100.0
        self._run(direction, speed, duration, wait)

    def stop(self) -> None:
        """Brake: both outputs low. The motor stops quickly."""
        with self._lock:
            self._cancel_timer()
            self._cancel_ramp()
            self._apply_brake()
            if self._state is not MotorState.FAULT:
                self._state = MotorState.STOPPED
            self._done.set()

    brake = stop

    def coast(self) -> bool:
        """Let the motor spin down freely (outputs open).

        In PWM mode this is per motor. In PH/EN mode the DRV8874 can only
        coast by sleeping, which affects every motor sharing the nSLEEP line,
        so it only happens when all those motors are idle. Otherwise the
        motor brakes and this returns False.
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
                    log.warning("%s: coast not possible in PH/EN mode while other motors on the "
                                "same nSLEEP line run; braking instead", self.full_name)
            if self._state is not MotorState.FAULT:
                self._state = MotorState.COASTING if ok else MotorState.STOPPED
            self._done.set()
            return ok

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until a timed run (``duration=``) finishes. Returns False on timeout."""
        return self._done.wait(timeout)

    def read_current(self) -> float:
        """Read the sensor now: estimated motor amps. Raises SensorError / ConfigError."""
        if self.sensor is None:
            raise ConfigError(f"{self.full_name} has no current sensor")
        isense = self.sensor.read_isense_amps()
        duty = self._duty
        motor_amps = isense / duty if duty >= 0.1 else isense
        self.last_isense_amps, self.last_current = isense, motor_amps
        return motor_amps

    # ------------------------------------------------------------ faults
    def add_fault_handler(self, handler: Callable[[Fault], None]) -> None:
        """Call ``handler(fault)`` whenever a fault is reported for this motor."""
        self._handlers.append(handler)

    def clear_fault(self) -> None:
        """Clear a latched fault so the motor can run again."""
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
        log.warning("%s", fault)
        for h in list(self._handlers):
            try:
                h(fault)
            except Exception:  # never let a user callback kill the monitor
                log.exception("fault handler failed")

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
        return speed_pc / 100.0

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

    # Pin level control. PH/EN: forward = PH low. PWM mode uses slow decay
    # (off-time = brake) so speed response matches PH/EN mode.
    def _apply_drive(self, duty: float) -> None:
        duty = max(0.0, min(1.0, duty))
        self._duty = duty
        fwd = (self._direction is Direction.FORWARD) != self.invert
        if self.mode is ControlMode.PH_EN:
            self._ph.set(not fwd)
            self._en.set_duty(duty)
        else:  # IN1=en, IN2=ph. Forward: IN1 low, IN2 high.
            if fwd:
                self._ph.set_duty(1.0)
                self._en.set_duty(1.0 - duty)
            else:
                self._en.set_duty(1.0)
                self._ph.set_duty(1.0 - duty)

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
        """Brake and release the pins."""
        try:
            self.stop()
        finally:
            self._backend.release(self._en_pin)
            self._backend.release(self._ph_pin)

    def __repr__(self) -> str:
        d = self._direction.value if self._direction else "-"
        return f"<Motor {self.full_name} {self._state.value} {d} {self._speed_pc:.0f}%>"
