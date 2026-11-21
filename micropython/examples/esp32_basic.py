# ESP32: drive both motors with blocking helpers (fault checks keep running).
# Wiring: see README. Copy pingoblin_motor.py (or .mpy) and this file to the board.
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39,
                   motor_names=("left", "right"),
                   motor_options=dict(ramp_time=0.5, min_speed_pc=15))
board.enable_monitor(on_fault=lambda f: print("FAULT:", f))

left, right = board["left"], board["right"]
left.forward(60)
right.forward(60)
board.pause(2)

left.speed_pc = 30            # gentle turn (ramps over 0.5 s)
board.pause(1)

left.reverse(50, duration=1)  # spin on the spot for 1 s
right.forward(50, duration=1, wait=True)

board.coast_all()
print(left, right)
