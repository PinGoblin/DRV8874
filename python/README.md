# pingoblin_motor

Python library for the **PinGoblin Board A** dual DC motor driver (2 × DRV8874) on a Raspberry Pi. It handles one board or many daisy-chained boards, optional current sensing through a PinGoblin ADS1115 board, and fault detection that includes stalled motors.

**Documentation: <https://pingoblin.github.io/DRV8874/>**: the user guide for the board and the full API reference.

## Install

```bash
pip install ".[pi]"              # from this folder: gpiozero and smbus2
pip install rpi-hardware-pwm     # optional: silent 20 kHz hardware PWM
```

## Example

```python
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
board.start_monitor()                              # stall / fault detection in the background

board.motor_a.forward(60, duration=2, wait=True)   # 60 % for 2 s, then brake
board.motor_b.reverse(40)
board.motor_b.speed_pc = 80                        # change speed while running
board.motor_b.coast()                              # spin down freely
board.close()
```

More examples are in [`examples/`](examples/).

## Tests

```bash
python -m pytest
```

The tests use `MockBackend`, so they run on any computer.

## Licence

MIT. See [LICENSE](../LICENSE).
