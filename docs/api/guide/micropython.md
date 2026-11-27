# MicroPython notes

The MicroPython version is one file, `micropython/pingoblin_motor.py`, for ESP32 and
Raspberry Pi Pico / Pico 2. It has the same classes and method names as the Raspberry Pi
package.

!!! warning "Status"
    Tested off-target (CPython with mock pins, plus a static check for MicroPython-only
    syntax and modules, and CI runs under the MicroPython Unix port). It has not yet been
    run on a real ESP32 or Pico. Please report problems as GitHub issues.

## How timing works (no threads)

MicroPython has no `threading.Timer`, so timed runs (`duration=`), ramps (`ramp_time`) and
fault checks all happen inside `update()`. Run it in one of three ways:

| Style | How |
| --- | --- |
| asyncio (recommended) | `asyncio.create_task(board.run_monitor())`. It calls `update()` every 20 ms |
| Blocking helpers | `motor.forward(..., duration=2, wait=True)`, `motor.wait()`, `board.pause(seconds)`. These call `update()` while they wait |
| Your own loop | Call `board.update()` every 10–50 ms |

If nothing calls `update()`, a `duration=` run will not stop on its own, a ramp will not
progress, and no faults are detected.

```python
import asyncio
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=2, a_ph=3, b_en=4, b_ph=5, sleep_pin=6, fault_pin=7)
board.enable_monitor(on_fault=print)

async def main():
    asyncio.create_task(board.run_monitor())
    board.motor_a.forward(70, duration=3)
    while board.motor_a.busy:
        await asyncio.sleep(0.1)
    board.motor_a.reverse(40)
    await asyncio.sleep(2)
    board.stop_all()

asyncio.run(main())
```

## Differences from the Raspberry Pi package

| Item | Raspberry Pi | MicroPython |
| --- | --- | --- |
| Timing | Background threads | `update()`, driven by asyncio, the blocking helpers or your loop |
| Fault monitor | `board.start_monitor()` | `board.enable_monitor()` plus something calling `update()` |
| PWM | Software 1 kHz by default; hardware 20 kHz optional | Hardware PWM on any pin, 20 kHz by default (`pwm_freq=`) |
| Enum-like names | `FaultType.STALL` is an `Enum` | `FaultType.STALL` is a string (`"stall"`) |
| Current sensing | ADS1115 board (`pingoblin_ads1115` library) | ADS1115 board (`ads1115` module) or the chip's own ADC (`ADCChannel`) |
| Pin access | `backend=` (gpiozero or mock) | `pins=` (`MachinePins` or `MockPins`) |
| Fault history | Last 1000 | Last 50 (`monitor.max_history`) |

The full API is in the [MicroPython reference](../reference/micropython.md).
