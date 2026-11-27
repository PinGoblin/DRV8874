"""Home an actuator against its end stop using stall detection (no limit switch).

Drives slowly in reverse until the motor stalls, then treats that as position 0.
Stall detection needs current sensing: A_ISENSE (J3 pin 7) to AIN0 of a PinGoblin
ADS1115 board.

Run with --mock to simulate a stall after 1 s.
"""
import sys
import threading
import time

from pingoblin_motor import (FaultAction, FaultPolicy, FaultType, MockBackend,
                             MockCurrentSensor, MotorBoard)

mock = "--mock" in sys.argv
if mock:
    backend, sensor = MockBackend(), MockCurrentSensor(0.3)
    sensing = dict(a_sensor=sensor)
else:
    from pingoblin_ads1115 import ADS1115   # the PinGoblin ADS1115 library
    backend = None
    sensing = dict(adc=ADS1115(bus=1, address=0x48, rate=860), a_sense_channel=0)

# Brake on stall but don't latch: a stall at the end stop is expected here.
policy = FaultPolicy({FaultType.STALL: FaultAction.BRAKE}, latch=False)
board = MotorBoard(a_en=12, a_ph=5, sleep_pin=26, fault_pin=19, backend=backend,
                   a_options=dict(policy=policy, stall_time=0.3, stall_current=1.0), **sensing)
stalled = threading.Event()
board.motor_a.add_fault_handler(lambda f: f.type is FaultType.STALL and stalled.set())
board.start_monitor(interval=0.02)

if mock:   # pretend the actuator hits the end stop after 1 s
    threading.Timer(1.0, lambda: setattr(sensor, "amps", 2.0)).start()

print("homing...")
board.motor_a.reverse(30)
if stalled.wait(timeout=10):
    print("end stop reached: position = 0, motor", board.motor_a.state.value)
else:
    board.motor_a.stop()
    print("no end stop found within 10 s")
board.close()
