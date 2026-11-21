"""Fault types, fault records, fault policies and exceptions."""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Optional


class FaultType(enum.Enum):
    """Every fault the library can detect.

    ``needs_sensor`` faults are only detected when an ADS1115 current sensor
    is attached to the motor. The others work from the board's nFAULT line.
    """

    #: Motor is driven but not turning: current at or near the limit for
    #: longer than ``stall_time``. Detected from current, or from nFAULT if no sensor.
    STALL = "stall"
    #: Driver is chopping at its current limit (short events). A warning only.
    CURRENT_LIMIT = "current_limit"
    #: nFAULT stays low while no motor on the board is driven: overcurrent
    #: shutdown (shorted output) or over-temperature shutdown.
    DRIVER_FAULT = "driver_fault"
    #: Motor commanded to run but draws (almost) no current: motor disconnected,
    #: broken wire, motor supply off or board fuse tripped. Needs a sensor.
    OPEN_LOAD = "open_load"
    #: Motor current above its continuous rating for longer than
    #: ``overload_time``. Risk of overheating. Needs a sensor.
    OVERLOAD = "overload"
    #: Total current on one board is above the board fuse rating (3 A).
    #: The fuse is likely to trip. Needs sensors.
    BOARD_OVERLOAD = "board_overload"
    #: Total current through a daisy chain is above the chain limit (6 A).
    #: Needs sensors.
    CHAIN_OVERLOAD = "chain_overload"
    #: The current sensor (ADS1115) could not be read.
    SENSOR_ERROR = "sensor_error"


class FaultAction(enum.Enum):
    """What the library does to a motor when a fault is detected."""

    NONE = "none"        #: Record and report only.
    BRAKE = "brake"      #: Stop the motor with the brake (EN low).
    COAST = "coast"      #: Let the motor coast (if possible, otherwise brake).
    SLEEP = "sleep"      #: Put the whole board to sleep (all motors coast).


#: Default response to each fault. Override per motor with ``FaultPolicy``.
DEFAULT_ACTIONS = {
    FaultType.STALL: FaultAction.BRAKE,
    FaultType.CURRENT_LIMIT: FaultAction.NONE,
    FaultType.DRIVER_FAULT: FaultAction.SLEEP,
    FaultType.OPEN_LOAD: FaultAction.BRAKE,
    FaultType.OVERLOAD: FaultAction.BRAKE,
    FaultType.BOARD_OVERLOAD: FaultAction.BRAKE,
    FaultType.CHAIN_OVERLOAD: FaultAction.BRAKE,
    FaultType.SENSOR_ERROR: FaultAction.NONE,
}

#: Faults that latch: the motor refuses to run until ``clear_fault()``.
LATCHING = {FaultType.STALL, FaultType.DRIVER_FAULT, FaultType.OPEN_LOAD, FaultType.OVERLOAD}


@dataclass
class FaultPolicy:
    """Per-motor fault response.

    Example::

        policy = FaultPolicy(actions={FaultType.STALL: FaultAction.COAST}, latch=False)
    """

    actions: dict = field(default_factory=dict)
    latch: bool = True

    def action_for(self, fault_type: FaultType) -> FaultAction:
        return self.actions.get(fault_type, DEFAULT_ACTIONS[fault_type])

    def latches(self, fault_type: FaultType) -> bool:
        return self.latch and fault_type in LATCHING


@dataclass(frozen=True)
class Fault:
    """A record of one detected fault."""

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
    """Base class for all library errors."""


class ConfigError(MotorError):
    """Invalid configuration (pins, modes, limits)."""


class MotorFaultError(MotorError):
    """Raised when commanding a motor that has a latched fault."""

    def __init__(self, fault: Fault):
        super().__init__(f"motor has a latched fault: {fault}. Call clear_fault() first.")
        self.fault = fault


class SensorError(MotorError):
    """The current sensor could not be read."""
