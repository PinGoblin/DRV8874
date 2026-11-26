"""Four-motor mode on an ESP32: four one-direction motors on one board.

Board setup:
- JP1 with all three pads open (no solder bridge).
- Each motor between its output (J4 A1, J4 A2, J5 B1, J5 B2) and a VM pin on J6.
- nSLEEP (J3 pin 9) wired to GPIO32, never linked to VLOGIC. The board's pull-down
  keeps the drivers asleep whenever this program isn't running.
"""
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39,
                   mode="independent")
board.enable_monitor(on_fault=print)

board["a1"].forward(60)                       # motor on J4 A1 at 60 %
board["b2"].forward(100, duration=3)          # motor on J5 B2 for 3 s
board.pause(4)                                # keeps update() running
board["a1"].stop()
board.close()                                 # sleeps the drivers, then releases the pins
