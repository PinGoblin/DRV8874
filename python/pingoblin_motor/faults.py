"""Fault types, fault records, fault policies and the library's exceptions.

A fault is detected by the [`FaultMonitor`][pingoblin_motor.monitor.FaultMonitor] and
delivered as a [`Fault`][pingoblin_motor.faults.Fault] record. Each motor then reacts
according to its [`FaultPolicy`][pingoblin_motor.faults.FaultPolicy]: brake, coast,
sleep the board, or report only. Serious faults *latch*: the next run command raises
[`MotorFaultError`][pingoblin_motor.faults.MotorFaultError] with the cause and what to do.
Once the cause has gone, the motor runs again on the following command.
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Optional


class FaultType(enum.Enum):
    """Every fault the library can detect.

    Faults marked *needs sensor* are only detected when the motor has a current sensor
    (for example a PinGoblin ADS1115 board). The others work from the board's nFAULT line.

    | Member | Detected when | Needs sensor |
    |---|---|---|
    | `STALL` | Motor current at or above `stall_current` for `stall_time` while driven | Yes |
    | `DRIVER_FAULT` | nFAULT low for 0.2 s: output short, driver overheated, or motor supply below about 4.5 V | No |
    | `OPEN_LOAD` | Under `open_load_current` for `open_load_time` while driven at 20 % duty or more: motor disconnected, broken wire, motor supply off or board fuse blown | Yes |
    | `OVERLOAD` | Above `continuous_current` for `overload_time` | Yes |
    | `BOARD_OVERLOAD` | Board supply current above the 5 A continuous board rating for 1 s | Yes |
    | `CHAIN_OVERLOAD` | Daisy-chain supply current above the chain limit (6 A) for 1 s | Yes |
    | `SENSOR_ERROR` | The current sensor could not be read (reported once until it recovers) | Yes |
    """

    #: Motor is driven but not turning: current at or near the limit for
    #: longer than ``stall_time``. Needs a sensor.
    STALL = "stall"
    #: nFAULT stays low for 0.2 s: overcurrent shutdown (shorted output),
    #: over-temperature shutdown, or a motor supply below the driver's
    #: undervoltage threshold (about 4.5 V).
    DRIVER_FAULT = "driver_fault"
    #: Motor commanded to run but draws (almost) no current: motor disconnected,
    #: broken wire, motor supply off or board fuse blown. Needs a sensor.
    OPEN_LOAD = "open_load"
    #: Motor current above its continuous rating for longer than
    #: ``overload_time``. Risk of overheating. Needs a sensor.
    OVERLOAD = "overload"
    #: Total current on one board is above its 5 A continuous rating.
    #: Sustained, this overheats the board. Needs sensors.
    BOARD_OVERLOAD = "board_overload"
    #: Total current through a daisy chain is above the chain limit (6 A).
    #: Needs sensors.
    CHAIN_OVERLOAD = "chain_overload"
    #: The current sensor (ADS1115) could not be read.
    SENSOR_ERROR = "sensor_error"


class FaultAction(enum.Enum):
    """What the library does to a motor when a fault is detected.

    | Member | Action |
    |---|---|
    | `NONE` | Record and report only |
    | `BRAKE` | Stop the motor with the brake (EN low) |
    | `COAST` | Let the motor coast if possible, otherwise brake |
    | `SLEEP` | Put the whole board to sleep (all motors coast). Brakes if the board has no sleep pin |
    """

    NONE = "none"        #: Record and report only.
    BRAKE = "brake"      #: Stop the motor with the brake (EN low).
    COAST = "coast"      #: Let the motor coast (if possible, otherwise brake).
    SLEEP = "sleep"      #: Put the whole board to sleep (all motors coast).


#: Default response to each fault. Override per motor with ``FaultPolicy``.
DEFAULT_ACTIONS = {
    FaultType.STALL: FaultAction.BRAKE,
    FaultType.DRIVER_FAULT: FaultAction.SLEEP,
    FaultType.OPEN_LOAD: FaultAction.BRAKE,
    FaultType.OVERLOAD: FaultAction.BRAKE,
    FaultType.BOARD_OVERLOAD: FaultAction.BRAKE,
    FaultType.CHAIN_OVERLOAD: FaultAction.BRAKE,
    FaultType.SENSOR_ERROR: FaultAction.NONE,
}
"""Default [`FaultAction`][pingoblin_motor.faults.FaultAction] for each [`FaultType`][pingoblin_motor.faults.FaultType]. Override per motor with a [`FaultPolicy`][pingoblin_motor.faults.FaultPolicy]."""

#: Faults that latch. The next run command raises ``MotorFaultError`` once; after
#: that the latch clears by itself as soon as the cause has gone.
LATCHING = {FaultType.STALL, FaultType.DRIVER_FAULT, FaultType.OPEN_LOAD, FaultType.OVERLOAD}
"""Fault types that latch. The next run command raises `MotorFaultError` once. After that,
the latch clears by itself when the cause has gone: for `DRIVER_FAULT` when nFAULT is high
again, for the others after the motor's `fault_retry_time`."""


@dataclass
class FaultPolicy:
    """Per-motor fault response: the action for each fault type, and whether faults latch.

    Fault types not listed in `actions` use the defaults in `DEFAULT_ACTIONS`. With
    `latch=True`, `STALL`, `DRIVER_FAULT`, `OPEN_LOAD` and `OVERLOAD` latch.

    Attributes:
        actions (dict): Maps a [`FaultType`][pingoblin_motor.faults.FaultType] to a
            [`FaultAction`][pingoblin_motor.faults.FaultAction].
        latch (bool): Whether latching fault types latch for this motor.

    Example:
        ```python
        from pingoblin_motor import FaultAction, FaultPolicy, FaultType

        # Coast on a stall, and don't latch (e.g. homing against an end stop)
        policy = FaultPolicy({FaultType.STALL: FaultAction.COAST}, latch=False)
        board = MotorBoard(a_en=12, a_ph=5, a_options=dict(policy=policy))
        ```
    """

    actions: dict = field(default_factory=dict)
    latch: bool = True

    def action_for(self, fault_type: FaultType) -> FaultAction:
        """Return the action for a fault type.

        Args:
            fault_type: The [`FaultType`][pingoblin_motor.faults.FaultType] detected.

        Returns:
            The [`FaultAction`][pingoblin_motor.faults.FaultAction] from `actions`, or the default.
        """
        return self.actions.get(fault_type, DEFAULT_ACTIONS[fault_type])

    def latches(self, fault_type: FaultType) -> bool:
        """Return whether a fault of this type latches the motor.

        Args:
            fault_type: The [`FaultType`][pingoblin_motor.faults.FaultType] detected.

        Returns:
            `True` if the fault latches (see `LATCHING`).
        """
        return self.latch and fault_type in LATCHING


@dataclass(frozen=True)
class Fault:
    """A record of one detected fault. Immutable.

    `str(fault)` gives a one-line summary such as
    `[stall] front.a: motor stalled: 2.61 A for 0.5 s`.

    Attributes:
        type (FaultType): What was detected.
        message (str): Human-readable description, including the likely cause.
        board (str | None): Board name, or `None` for a chain-wide fault.
        motor (str | None): Motor name, or `None` for a board-wide fault.
        value (float | None): The measured value that triggered it (amps), if any.
        timestamp (float): `time.monotonic()` when it was detected.
    """

    type: FaultType
    message: str
    board: Optional[str] = None
    motor: Optional[str] = None
    value: Optional[float] = None
    timestamp: float = field(default_factory=time.monotonic)

    def __str__(self) -> str:
        where = ".".join(p for p in (self.board, self.motor) if p) or "system"
        return f"[{self.type.value}] {where}: {self.message}"


# --------------------------------------------------------------------- errors
class MotorError(Exception):
    """Base class for every exception raised by the library."""


class ConfigError(MotorError):
    """Invalid configuration: pins, modes, names or limits."""


class MotorFaultError(MotorError):
    """Raised when you command a motor that has a latched fault.

    Raised once for each fault. Fix the cause and run the motor again: the latch clears by
    itself once the cause has gone (see `LATCHING`). A motor that is still faulty raises
    again. [`Motor.clear_fault()`][pingoblin_motor.motor.Motor.clear_fault] clears it at once.

    Attributes:
        fault (Fault): The latched fault.
    """

    def __init__(self, fault: Fault):
        """
        Args:
            fault: The latched [`Fault`][pingoblin_motor.faults.Fault].
        """
        super().__init__(f"{fault}")
        self.fault = fault


class SensorError(MotorError):
    """The current sensor (for example the ADS1115) could not be read."""
