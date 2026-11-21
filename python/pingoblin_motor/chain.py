"""[`MotorChain`][pingoblin_motor.chain.MotorChain]: several daisy-chained boards managed as one system."""
from __future__ import annotations

import logging
from typing import Callable, Dict, Iterator, List, Optional

from .board import MotorBoard
from .faults import ConfigError, Fault
from .monitor import FaultMonitor
from .motor import Motor

_log = logging.getLogger("pingoblin_motor")


class MotorChain:
    """Several [`MotorBoard`][pingoblin_motor.board.MotorBoard]s powered through one daisy chain, with one fault monitor.

    Motors are addressed as `"board.motor"` (for example `"front.a"`) or by an alias.
    The chain also checks `CHAIN_OVERLOAD`: the total supply current through the VIN
    terminals.

    Example:
        ```python
        chain = MotorChain([front, rear])
        chain.alias("left", "front.a")
        chain["left"].forward(60, duration=2)
        chain.add_fault_handler(print)
        chain.emergency_stop()
        ```
    """

    def __init__(self, boards=(), chain_current_limit: float = 6.0, monitor: bool = True,
                 monitor_interval: float = 0.05):
        """
        Args:
            boards: Boards to add. Names must be unique.
            chain_current_limit: Total supply current allowed through the chain (A). Checked
                only when every motor has a sensor.
            monitor: Start the fault monitor immediately.
            monitor_interval: Seconds between fault checks.

        Raises:
            ConfigError: Duplicate board names.
        """
        self.boards: Dict[str, MotorBoard] = {}
        self._aliases: Dict[str, Motor] = {}
        self.chain_current_limit = chain_current_limit
        self._monitor = FaultMonitor([], interval=monitor_interval, chain_current_limit=chain_current_limit)
        for b in boards:
            self.add_board(b)
        if monitor:
            self.start_monitor()

    # ------------------------------------------------------------ setup
    def add_board(self, board: MotorBoard) -> MotorBoard:
        """Add a board. Its own monitor stops; the chain's monitor takes over.

        Args:
            board: The [`MotorBoard`][pingoblin_motor.board.MotorBoard].

        Returns:
            The board.

        Raises:
            ConfigError: A board with that name already exists.
        """
        if board.name in self.boards:
            raise ConfigError(f"duplicate board name '{board.name}'")
        board.stop_monitor()   # the chain's monitor takes over
        self.boards[board.name] = board
        self._monitor.add_board(board)
        return board

    def alias(self, alias: str, target: str) -> Motor:
        """Give a motor a friendly name.

        Args:
            alias: The new name. Must not contain `.`.
            target: `"board.motor"` or an existing alias.

        Returns:
            The [`Motor`][pingoblin_motor.motor.Motor].

        Raises:
            ConfigError: The alias contains `.`.
            KeyError: No such motor.
        """
        if "." in alias:
            raise ConfigError("aliases must not contain '.'")
        motor = self.motor(target)
        self._aliases[alias] = motor
        return motor

    def add_fault_handler(self, handler: Callable[[Fault], None]) -> None:
        """Call `handler(fault)` for every fault on any board.

        Args:
            handler: A callable taking one [`Fault`][pingoblin_motor.faults.Fault].
        """
        self._monitor.add_fault_handler(handler)

    # ------------------------------------------------------------ access
    def motor(self, name: str) -> Motor:
        """Look up a motor. `chain[name]` does the same.

        Args:
            name: An alias, or `"board.motor"`.

        Returns:
            The [`Motor`][pingoblin_motor.motor.Motor].

        Raises:
            KeyError: No such motor.
        """
        if name in self._aliases:
            return self._aliases[name]
        board_name, _, motor_name = name.partition(".")
        try:
            return self.boards[board_name].motors[motor_name]
        except KeyError:
            raise KeyError(f"no motor '{name}' (use 'board.motor' or an alias)") from None

    __getitem__ = motor
    """`chain[name]` is the same as `chain.motor(name)`."""

    @property
    def motors(self) -> List[Motor]:
        """Every motor on every board, in board order."""
        return [m for b in self.boards.values() for m in b.motors.values()]

    def __iter__(self) -> Iterator[Motor]:
        return iter(self.motors)

    @property
    def faults(self) -> List[Fault]:
        """History of detected faults, oldest first (up to 1000)."""
        return list(self._monitor.faults)

    @property
    def active_faults(self) -> List[Fault]:
        """Latched faults currently blocking motors."""
        return [m.fault for m in self.motors if m.fault is not None]

    @property
    def total_current(self) -> Optional[float]:
        """Total supply-side current of the chain (A) from the last readings, or `None`."""
        vals = [b.total_current for b in self.boards.values()]
        if not vals or any(v is None for v in vals):
            return None
        return sum(vals)

    # ------------------------------------------------------------ commands
    def stop_all(self) -> None:
        """Brake every motor."""
        for m in self.motors:
            m.stop()

    def coast_all(self) -> None:
        """Coast every motor (see [`MotorBoard.coast_all()`][pingoblin_motor.board.MotorBoard.coast_all])."""
        for b in self.boards.values():
            b.coast_all()

    def emergency_stop(self) -> None:
        """Brake every motor, then put every board that has a sleep pin to sleep."""
        self.stop_all()
        for b in self.boards.values():
            if b._sleep is not None:
                b.sleep()

    def clear_faults(self) -> None:
        """Clear the latched fault on every motor."""
        for m in self.motors:
            m.clear_fault()

    def start_monitor(self) -> None:
        """Start the background fault monitor."""
        self._monitor.start()

    def stop_monitor(self) -> None:
        """Stop the background fault monitor."""
        self._monitor.stop()

    def check_faults(self) -> List[Fault]:
        """Run one fault check now. Useful when the monitor thread is off.

        Returns:
            The faults found in this check.
        """
        return self._monitor.check_once()

    def close(self) -> None:
        """Stop the monitor and close every board."""
        self.stop_monitor()
        for b in self.boards.values():
            b.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self) -> str:
        return f"<MotorChain boards={list(self.boards)}>"
