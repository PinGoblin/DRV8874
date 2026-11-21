# pingoblin_motor for MicroPython

Single-file MicroPython library for the **PinGoblin Board A** dual DC motor driver (2 × DRV8874), for **ESP32** and **Raspberry Pi Pico / Pico 2**. It has the same classes and method names as the [Raspberry Pi library](../python/).

**Documentation: <https://pingoblin.github.io/DRV8874/>**: see *API → Guide → MicroPython notes* and the *MicroPython reference*.

> **Status:** tested off-target (CPython with mock pins) and under the MicroPython Unix port in CI. It has not yet been run on a real ESP32 or Pico. Please report problems as GitHub issues.

## Install

Needs MicroPython 1.20 or later.

```bash
mpremote mip install github:PinGoblin/DRV8874/micropython
```

On an ESP32 without PSRAM, precompile the file and copy the `.mpy` (it leaves out the docstrings and avoids compiling on the board):

```bash
mpy-cross pingoblin_motor.py
mpremote cp pingoblin_motor.mpy :
```

CI also builds a `.mpy` for each push; download it from the workflow run's artifacts.

## Example (ESP32)

```python
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39)
board.enable_monitor(on_fault=print)

board.motor_a.forward(60, duration=2, wait=True)   # blocks, still checks faults
board.motor_b.reverse(40)
board.pause(1.5)                                   # sleep that keeps checking faults
board.coast_all()
```

Timed runs, ramps and fault checks happen in `board.update()`, which the blocking helpers, `board.run_monitor()` (asyncio) or your own loop must call. More examples are in [`examples/`](examples/).

## Tests

```bash
python -m pytest tests            # CPython, mock pins
micropython tests/mp_smoke.py     # MicroPython Unix port
```
