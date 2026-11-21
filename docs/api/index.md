# API

`pingoblin_motor` controls PinGoblin Board A from Python. There are two versions with
the same classes and method names, so code moves between them with little change:

| Version | Runs on | Install |
| --- | --- | --- |
| Raspberry Pi package (`python/`) | Raspberry Pi with Python 3.8+ and gpiozero (Pi 5 supported) | `pip install ".[pi]"` |
| MicroPython module (`micropython/`) | ESP32, Raspberry Pi Pico / Pico 2, MicroPython 1.20+ | `mpremote mip install github:PinGoblin/DRV8874/micropython` |

Both handle one board or many daisy-chained boards, optional current sensing, and fault
detection that includes stalled motors.

```python
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
board.start_monitor()                              # Pi; on MicroPython: enable_monitor()

board.motor_a.forward(60, duration=2, wait=True)   # 60 % for 2 s, then brake
board.motor_b.reverse(40)
board.motor_b.speed_pc = 80                        # change speed while running
board.motor_b.coast()                              # spin down freely
board.close()
```

## Guide

- [Installation](guide/install.md)
- [Concepts](guide/concepts.md): boards, motors, speed, braking and coasting, PWM frequency
- [Faults and stall detection](guide/faults.md)
- [Current sensing](guide/current-sensing.md)
- [Daisy-chained boards](guide/daisy-chain.md)
- [MicroPython notes](guide/micropython.md): timing without threads and the differences from the Pi package
- [Testing without hardware](guide/testing.md)

## Reference

The Raspberry Pi reference documents each module of the package. The main classes are
[`MotorBoard`][pingoblin_motor.board.MotorBoard], [`Motor`][pingoblin_motor.motor.Motor] and
[`MotorChain`][pingoblin_motor.chain.MotorChain]; all are importable from
`pingoblin_motor`. The [MicroPython reference](reference/micropython.md) documents the
single-file module.
