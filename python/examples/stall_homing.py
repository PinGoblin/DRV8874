"""Home an actuator against its end stop using stall detection (no limit switch).

Drives slowly in reverse until the motor stalls, then treats that as position 0.
Works with or without an ADS1115: without it, the stall is detected from nFAULT
(the driver current-limiting).

Run with --mock to simulate a stall after 1 s.
"""
import sys
import threading
import time

from pingoblin_motor import FaultAction, FaultPolicy, FaultType, MockBackend, MotorBoard

mock = "--mock" in sys.argv
backend = MockBackend() if mock else None

# Brake on stall but don't latch: a stall at the end stop is expected here.
policy = FaultPolicy({FaultType.STALL: FaultAction.BRAKE}, latch=False)
board = MotorBoard(a_en=12, a_ph=5, fault_pin=19, backend=backend,
                   a_options=dict(policy=policy, stall_time=0.3))
stalled = threading.Event()
board.motor_a.add_fault_handler(lambda f: f.type is FaultType.STALL and stalled.set())
board.start_monitor(interval=0.02)

if mock:   # pretend the actuator hits the end stop after 1 s
    threading.Timer(1.0, lambda: setattr(backend.pins[19], "level", False)).start()

print("homing...")
board.motor_a.reverse(30)
if stalled.wait(timeout=10):
    print("end stop reached: position = 0, motor", board.motor_a.state.value)
else:
    board.motor_a.stop()
    print("no end stop found within 10 s")
if mock:
    backend.pins[19].level = True
board.close()
