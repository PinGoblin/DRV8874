"""Four-motor mode: four one-direction motors (pumps, fans) on one board.

Board setup:
- JP1 with all three pads open (no solder bridge).
- Each motor between its output (J4 A1, J4 A2, J5 B1, J5 B2) and a VM pin on J6.
- nSLEEP (J3 pin 9) wired to GPIO26 only (not also connected to VLOGIC). The pull-down
  keeps the drivers asleep whenever this program isn't running.

Run with --mock to try it without hardware.
"""
import sys
import time

from pingoblin_motor import MockBackend, MotorBoard

backend = MockBackend() if "--mock" in sys.argv else None

with MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                mode="independent", motor_names=("pump", "fan", "valve", "light"),
                backend=backend) as board:
    board.start_monitor(on_fault=print)
    board["pump"].forward(60)                       # 60 % speed
    board["fan"].forward(100)
    board["valve"].forward(100, duration=0.5)       # pulse for 0.5 s
    time.sleep(2)
    board["pump"].speed_pc = 30
    time.sleep(2)
    board.stop_all()
# Leaving the with-block puts the drivers to sleep before the pins are released.
