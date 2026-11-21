# pingoblin_motor for MicroPython

Single-file MicroPython library for the **PinGoblin Board A** dual DC motor driver (2 × DRV8874), for **ESP32** and **Raspberry Pi Pico / Pico 2**. It has the same classes and method names as the [Raspberry Pi library](../python/), so code moves between them with little change.

> **Status:** tested off-target (CPython with mock pins, plus a static check for MicroPython-only syntax and modules). It has not yet been run on a real ESP32 or Pico. Please report problems as GitHub issues.

## Install

Needs MicroPython 1.20 or later.

**From GitHub with mip** (Wi-Fi boards, or through `mpremote`):

```bash
mpremote mip install github:PinGoblin/DRV8874/micropython
```

**Or copy the file:**

```bash
mpremote cp pingoblin_motor.py :
```

**Recommended on ESP32: precompile.** The source is about 42 KB, and compiling it on the board can run out of RAM on an ESP32 without PSRAM. Precompile it and copy the `.mpy` instead:

```bash
pip install mpy-cross
mpy-cross pingoblin_motor.py          # makes pingoblin_motor.mpy
mpremote cp pingoblin_motor.mpy :
```

## Wiring

| J3 pin | Signal | ESP32 DevKit | Pico |
|---|---|---|---|
| 1 | GND | GND | GND |
| 2 | VLOGIC | 3V3 | 3V3(OUT) |
| 3 | A_EN | GPIO25 | GP2 |
| 4 | A_PH | GPIO26 | GP3 |
| 5 | B_EN | GPIO27 | GP4 |
| 6 | B_PH | GPIO33 | GP5 |
| 7 | A_ISENSE | GPIO34 (ADC1) | GP26 (ADC0) |
| 8 | B_ISENSE | GPIO35 (ADC1) | GP27 (ADC1) |
| 9 | nSLEEP | GPIO32 | GP6 |
| 10 | nFAULT | GPIO39 (input only) | GP7 |

ESP32: avoid GPIO0, 2, 12, 15 (boot straps) and GPIO14. Use ADC1 pins, because ADC2 doesn't work while Wi-Fi is on.

## Quick start

```python
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39)
board.enable_monitor(on_fault=print)

board.motor_a.forward(60, duration=2, wait=True)   # blocks, still checks faults
board.motor_b.reverse(40)
board.pause(1.5)                                    # sleep that keeps checking faults
board.motor_b.speed_pc = 80
board.pause(1)
board.coast_all()
```

## How timing works (no threads)

MicroPython has no `threading.Timer`, so timed runs (`duration=`), ramps (`ramp_time`) and fault checks all happen inside `update()`. Run it in one of three ways:

| Style | How |
|---|---|
| **asyncio** (recommended) | `asyncio.create_task(board.run_monitor())`. It calls `update()` every 20 ms |
| **Blocking helpers** | `motor.forward(..., duration=2, wait=True)`, `motor.wait()`, `board.pause(seconds)`. These call `update()` while they wait |
| **Your own loop** | Call `board.update()` every 10–50 ms |

If nothing calls `update()`, a `duration=` run won't stop on its own, a ramp won't progress, and no faults are detected.

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

## API

The API is the same as the Raspberry Pi library. See [`../python/README.md`](../python/README.md) for full tables. In summary:

- **Motor:** `forward()`, `reverse()`, `run()` (signed), `start()`, `stop()` / `brake()`, `coast()`, `wait()`, `speed_pc`, `direction`, `state`, `is_running`, `busy`, `current`, `fault`, `clear_fault()`, `add_fault_handler()`.
- **MotorBoard:** `motor_a`, `motor_b`, `board["name"]`, `sleep()`, `wake()`, `stop_all()`, `coast_all()`, `fault_active`, `current_limit`, `total_current`, `enable_monitor()`, `update()`, `pause()`, `run_monitor()`, `close()`.
- **MotorChain:** `alias()`, `chain["board.motor"]`, `stop_all()`, `coast_all()`, `emergency_stop()`, `faults`, `active_faults`, `clear_faults()`, `total_current`, `update()`, `pause()`, `run_monitor()`, `check_faults()`.

Motor options (seconds and amps) are the same as on the Pi: `invert`, `min_speed_pc`, `ramp_time`, `reverse_delay`, `stall_current`, `stall_time`, `start_grace`, `open_load_current`, `open_load_time`, `continuous_current`, `overload_time`, `policy`.

**Differences from the Raspberry Pi library:**

| Item | Raspberry Pi | MicroPython |
|---|---|---|
| Timing | Background threads | `update()`, driven by asyncio, the blocking helpers or your loop |
| Fault monitor | `board.start_monitor()` | `board.enable_monitor()` plus something calling `update()` |
| PWM | Software 1 kHz by default; hardware 20 kHz optional | Hardware PWM on any pin, **20 kHz by default** (`pwm_freq=`) |
| Enum-like names | `FaultType.STALL` is an `Enum` | `FaultType.STALL` is a string (`"stall"`) |
| Current sensing | ADS1115 | ADS1115 (`machine.I2C`) **or** the chip's own ADC (`ADCChannel`) |
| Fault history | Last 1000 | Last 50 (`monitor.max_history`) |

## Current sensing

**PinGoblin ADS1115 board** (most accurate; it averages over the PWM cycle):

```python
from machine import I2C, Pin
from pingoblin_motor import ADS1115, MotorBoard

i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)      # ESP32. Pico: I2C(0, sda=Pin(0), scl=Pin(1))
adc = ADS1115(i2c, address=0x48)
board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, fault_pin=39,
                   adc=adc, a_sense_channel=0, b_sense_channel=1)
```

**The microcontroller's own ADC** (no extra board):

```python
from pingoblin_motor import ADCChannel, MotorBoard

board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, fault_pin=39,
                   a_sensor=ADCChannel(34), b_sensor=ADCChannel(35))
```

The built-in ADC takes instant samples, so with PWM each one is either the full motor current or zero. The library averages 16 samples per reading, which gives a usable mean but is noisier than the ADS1115. On the Pico, ISENSE is read against the 3.3 V supply (`ADCChannel(26, vref=3.3)`).

## Faults

The same eight fault types as the Pi library: `STALL`, `CURRENT_LIMIT`, `DRIVER_FAULT`, `OPEN_LOAD`, `OVERLOAD`, `BOARD_OVERLOAD`, `CHAIN_OVERLOAD` and `SENSOR_ERROR`, with the same default actions and latching. Stall detection works without a current sensor by watching nFAULT. See [`../python/README.md`](../python/README.md#faults).

## Daisy chain

```python
from pingoblin_motor import MotorBoard, MotorChain

front = MotorBoard("front", a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39)
rear = MotorBoard("rear", a_en=16, a_ph=17, b_en=18, b_ph=19, sleep_pin=32, fault_pin=39)
chain = MotorChain([front, rear])
chain.add_fault_handler(print)
chain.alias("left", "front.a")
chain["left"].forward(50, duration=2, wait=True)
chain.emergency_stop()
```

Shared nSLEEP / nFAULT: wire them together and pass the same pin number to every board.

## Tests

Off-target tests run on a PC with CPython:

```bash
cd micropython
python -m pytest tests
```
