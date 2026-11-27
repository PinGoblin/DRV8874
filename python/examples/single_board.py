"""One PinGoblin DRV8874 board: run both motors, react to faults.

Wiring (Raspberry Pi BCM -> J3): GPIO12->3 A_EN, GPIO5->4 A_PH, GPIO13->5 B_EN,
GPIO6->6 B_PH, GPIO26->9 nSLEEP, GPIO19->10 nFAULT, 3V3->2, GND->1.

Run with --mock to try it without hardware.
"""
import logging
import sys
import time

from pingoblin_motor import MockBackend, MotorBoard

logging.basicConfig(level=logging.INFO)
backend = MockBackend() if "--mock" in sys.argv else None

with MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                backend=backend, motor_names=("left", "right"),
                motor_options=dict(ramp_time=0.5, min_speed_pc=15)) as board:
    board.start_monitor(on_fault=lambda f: print("FAULT:", f))
    left, right = board["left"], board["right"]

    left.forward(60)
    right.forward(60)
    time.sleep(2)

    left.speed_pc = 30                    # gentle turn
    time.sleep(1)

    left.reverse(50, duration=1)          # spin on the spot for 1 s
    right.forward(50, duration=1, wait=True)

    board.coast_all()                     # both idle, so the board sleeps and they coast
    print(left, right)
