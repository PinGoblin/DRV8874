"""Background fault monitor.

The [`FaultMonitor`][pingoblin_motor.monitor.FaultMonitor] polls each board's nFAULT
line and, where fitted, each motor's current sensor. It detects every
[`FaultType`][pingoblin_motor.faults.FaultType].

Without a current sensor, a stall is inferred from nFAULT staying low (the driver
current-limiting) for `stall_time`. If both motors on a board are running, the board
can't tell which one stalled, so both are stopped.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .faults import Fault, FaultType, SensorError

_log = logging.getLogger("pingoblin_motor")

DRIVER_FAULT_DEBOUNCE = 0.2
"""Seconds nFAULT must stay low before `DRIVER_FAULT`."""
OVERLOAD_DEBOUNCE = 1.0
"""Seconds a board or chain must stay over its limit before `BOARD_OVERLOAD` / `CHAIN_OVERLOAD`."""
OPEN_LOAD_MIN_DUTY = 0.2
"""Open-load checks run only at or above this PWM duty (0–1)."""


@dataclass
class _Track:
    stall_since: Optional[float] = None
    open_since: Optional[float] = None
    over_since: Optional[float] = None
    sensor_failed: bool = False


class FaultMonitor:
    """Watches boards for faults: polls nFAULT and the current sensors, and reports through handlers.

    Normally created for you by
    [`MotorBoard.start_monitor()`][pingoblin_motor.board.MotorBoard.start_monitor] or
    [`MotorChain`][pingoblin_motor.chain.MotorChain]. See
    [`FaultType`][pingoblin_motor.faults.FaultType] for what is detected.
    """

    def __init__(self, boards, interval: float = 0.05, chain_current_limit: Optional[float] = None,
                 clock: Callable[[], float] = time.monotonic):
        """
        Args:
            boards: Boards to watch.
            interval: Seconds between checks when running as a thread.
            chain_current_limit: Amps for `CHAIN_OVERLOAD`, or `None` to disable.
            clock: Time source in seconds (for tests). Default `time.monotonic`.

        Attributes:
            faults (list): History of detected faults, oldest first (up to 1000).
        """
        self.boards = list(boards)
        self.interval = interval
        self.chain_current_limit = chain_current_limit
        self.clock = clock
        self.faults: List[Fault] = []
        self._handlers: List[Callable[[Fault], None]] = []
        self._tracks: Dict[int, _Track] = {}
        self._board_since: Dict[int, Optional[float]] = {}
        self._board_reported: set = set()
        self._board_over_since: Dict[int, Optional[float]] = {}
        self._chain_since: Optional[float] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ control
    def add_fault_handler(self, handler: Callable[[Fault], None]) -> None:
        """Call `handler(fault)` for every fault detected.

        Args:
            handler: A callable taking one [`Fault`][pingoblin_motor.faults.Fault].
        """
        self._handlers.append(handler)

    def add_board(self, board) -> None:
        """Watch another board.

        Args:
            board: The [`MotorBoard`][pingoblin_motor.board.MotorBoard].
        """
        with self._lock:
            self.boards.append(board)

    def start(self) -> None:
        """Start checking in a background daemon thread."""
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="pingoblin-fault-monitor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the background thread and wait for it to finish."""
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None

    @property
    def running(self) -> bool:
        """`True` while the background thread runs."""
        return self._thread is not None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_once()
            except Exception:
                _log.exception("fault monitor check failed")
            self._stop.wait(self.interval)

    # ------------------------------------------------------------ checks
    def check_once(self) -> List[Fault]:
        """Check every board once.

        Returns:
            The faults found in this pass.
        """
        now = self.clock()
        found: List[Fault] = []
        chain_total, chain_known = 0.0, True
        with self._lock:
            boards = list(self.boards)
        for board in boards:
            total, known = self._check_board(board, now, found)
            if known:
                chain_total += total
            else:
                chain_known = False
        if self.chain_current_limit is not None and chain_known and boards:
            if chain_total > self.chain_current_limit:
                if self._chain_since is None:
                    self._chain_since = now
                elif now - self._chain_since >= OVERLOAD_DEBOUNCE:
                    msg = (f"daisy chain draws {chain_total:.2f} A, above the "
                           f"{self.chain_current_limit:.1f} A chain limit")
                    for board in boards:
                        for m in board.motors.values():
                            if m.is_running:
                                self._emit(Fault(FaultType.CHAIN_OVERLOAD, msg, board.name, m.name,
                                                 chain_total, now), m, found)
                    self._chain_since = None
            else:
                self._chain_since = None
        return found

    def _check_board(self, board, now: float, found: List[Fault]):
        key = id(board)
        if board.is_asleep:
            for m in board.motors.values():
                self._tracks[id(m)] = _Track()
            self._board_since[key] = None
            self._board_reported.discard(key)
            return 0.0, True

        nfault = board.fault_active                    # None if not wired

        # -- DRIVER_FAULT: nFAULT low (short, overheating or motor supply low)
        if nfault and key not in self._board_reported:
            since = self._board_since.get(key)
            if since is None:
                self._board_since[key] = now
            elif now - since >= DRIVER_FAULT_DEBOUNCE:
                f = Fault(FaultType.DRIVER_FAULT,
                          "driver shut down: motor output shorted, driver overheated, or motor "
                          "supply below 4.5 V. Check the motor wiring, let the board cool, or "
                          "charge the battery", board.name, None, None, now)
                self._record(f, found)
                board._report_board_fault(f)
                self._board_since[key] = None
                self._board_reported.add(key)       # once per event, until nFAULT goes high
        elif not nfault:
            self._board_since[key] = None
            self._board_reported.discard(key)

        total, known = 0.0, True
        for m in board.motors.values():
            tr = self._tracks.setdefault(id(m), _Track())
            amps = None
            if m.has_sensor:
                try:
                    amps = m.read_current()
                    tr.sensor_failed = False
                    total += m.last_isense_amps or 0.0
                except SensorError as exc:
                    known = False
                    if not tr.sensor_failed:
                        tr.sensor_failed = True
                        self._emit(Fault(FaultType.SENSOR_ERROR, str(exc), board.name, m.name, None, now), m, found)
            else:
                known = False

            if not (m.is_running and m.duty > 0):
                tr.stall_since = tr.open_since = tr.over_since = None
                continue
            in_grace = now - m.running_since < m.start_grace

            if amps is None:
                continue

            # -- STALL
            if amps >= m.stall_current and not in_grace:
                if tr.stall_since is None:
                    tr.stall_since = now
                elif now - tr.stall_since >= m.stall_time:
                    self._emit(Fault(FaultType.STALL,
                                     f"motor stalled ({amps:.2f} A for {m.stall_time:.1f} s): check "
                                     "for a jam or too much load", board.name, m.name, amps, now),
                               m, found)
                    tr.stall_since = None
                    continue
            else:
                tr.stall_since = None

            # -- OPEN_LOAD
            if not in_grace and m.duty >= OPEN_LOAD_MIN_DUTY and amps < m.open_load_current:
                if tr.open_since is None:
                    tr.open_since = now
                elif now - tr.open_since >= m.open_load_time:
                    self._emit(Fault(FaultType.OPEN_LOAD,
                                     f"no motor current ({amps * 1000:.0f} mA): check the motor wires "
                                     "and the motor supply",
                                     board.name, m.name, amps, now), m, found)
                    tr.open_since = None
                    continue
            else:
                tr.open_since = None

            # -- OVERLOAD
            if amps > m.continuous_current:
                if tr.over_since is None:
                    tr.over_since = now
                elif now - tr.over_since >= m.overload_time:
                    self._emit(Fault(FaultType.OVERLOAD,
                                     f"{amps:.2f} A above the {m.continuous_current:.1f} A continuous "
                                     f"rating for {m.overload_time:.0f} s: reduce the load", board.name, m.name, amps, now),
                               m, found)
                    tr.over_since = None
            else:
                tr.over_since = None

        # -- BOARD_OVERLOAD
        if known and total > board.fuse_rating:
            since = self._board_over_since.get(key)
            if since is None:
                self._board_over_since[key] = now
            elif now - since >= OVERLOAD_DEBOUNCE:
                msg = f"board draws {total:.2f} A, above the {board.fuse_rating:.1f} A board rating"
                for m in board.motors.values():
                    if m.is_running:
                        self._emit(Fault(FaultType.BOARD_OVERLOAD, msg, board.name, m.name, total, now), m, found)
                self._board_over_since[key] = None
        else:
            self._board_over_since[key] = None
        return total, known

    # ------------------------------------------------------------ reporting
    def _record(self, fault: Fault, found: List[Fault]) -> None:
        found.append(fault)
        self.faults.append(fault)
        if len(self.faults) > 1000:
            del self.faults[:-1000]
        for h in list(self._handlers):
            try:
                h(fault)
            except Exception:
                _log.exception("fault handler failed")

    def _emit(self, fault: Fault, motor, found: List[Fault]) -> None:
        self._record(fault, found)
        motor._report_fault(fault)
