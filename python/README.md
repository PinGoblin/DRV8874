# pingoblin_motor

Python library for the **PinGoblin Board A** dual DC motor driver (2 × DRV8874) on a Raspberry Pi. It handles one board or many daisy-chained boards, optional current sensing through a PinGoblin ADS1115 board, and fault detection that includes stalled motors.

```python
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
board.start_monitor()                       # stall / fault detection in the background

board.motor_a.forward(60, duration=2, wait=True)   # 60 % for 2 s, then brake
board.motor_b.reverse(40)
board.motor_b.speed_pc = 80                 # change speed while running
board.motor_b.coast()                       # spin down freely
board.close()
```

## Install

```bash
pip install gpiozero smbus2          # smbus2 only needed for current sensing
pip install rpi-hardware-pwm         # optional: silent 20 kHz hardware PWM
pip install .                        # from this folder
```

Pin numbers are BCM GPIO numbers. The library needs Python 3.8+ and gpiozero (Pi 5 supported).

## Object model

| Class | What it is |
|---|---|
| `MotorBoard` | One Board A: two motors plus the shared nSLEEP and nFAULT lines |
| `Motor` | One motor channel (`board.motor_a`, `board.motor_b`, or `board["a"]`) |
| `MotorChain` | Several daisy-chained boards managed as one system, with one fault monitor |
| `ADS1115` | Driver for a PinGoblin ADS1115 board (or any ADS1115), used for current sensing |
| `FaultMonitor` | Background thread that detects faults. Started by `board.start_monitor()` or by `MotorChain` |
| `Fault`, `FaultType`, `FaultPolicy`, `FaultAction` | Fault records and how each motor reacts to them |
| `GpiozeroBackend`, `MockBackend` | Hardware access. `MockBackend` runs without a Pi, for tests and dry runs |

## Motor API

| Method / property | Description |
|---|---|
| `forward(speed_pc=100, duration=None, wait=False)` | Run forward. With `duration`, stop after that many seconds. With `wait=True`, block until it does |
| `reverse(speed_pc=100, duration=None, wait=False)` | Run in reverse |
| `run(speed_pc, duration=None, wait=False)` | Signed speed: `+50` forward, `-50` reverse, `0` stop |
| `start(duration=None, wait=False)` | Resume the last direction and speed |
| `stop()` / `brake()` | Brake: outputs shorted low, stops quickly |
| `coast()` | Outputs open, motor spins down freely. Returns `False` if it had to brake instead (see below) |
| `wait(timeout=None)` | Block until a timed run finishes |
| `speed_pc` | Commanded speed 0–100 %. Setting it while running changes speed |
| `direction` | `Direction.FORWARD` / `Direction.REVERSE` / `None` |
| `state` | `MotorState.RUNNING`, `STOPPED`, `COASTING` or `FAULT` |
| `is_running` | `True` while driven |
| `current` | Motor current in amps (reads the sensor), or `None` without a sensor |
| `fault` / `clear_fault()` | Latched fault, and clearing it so the motor can run again |
| `add_fault_handler(fn)` | Call `fn(fault)` when this motor has a fault |

Motor options, passed through `MotorBoard(..., a_options={...}, b_options={...})` or `motor_options={...}` for both motors:

| Option | Default | Meaning |
|---|---|---|
| `invert` | `False` | Swap forward and reverse (instead of swapping wires) |
| `min_speed_pc` | `0` | Raise any non-zero speed to at least this (motor deadband) |
| `ramp_time` | `0` | Seconds to ramp 0→100 %. Soft start and soft speed changes |
| `reverse_delay` | `0.1` | Brake time before reversing a running motor |
| `stall_current` | 80 % of limit | Amps treated as a stall |
| `stall_time` | `0.5` | Seconds the stall condition must last |
| `start_grace` | `0.3` | Ignore stall/open-load for this long after a start (start-up surge) |
| `open_load_current` / `open_load_time` | `0.03` A / `1.0` s | Open-load detection |
| `continuous_current` / `overload_time` | `1.5` A / `5` s | Overload detection |
| `policy` | defaults | A `FaultPolicy`: what to do on each fault, and whether faults latch |

## Board options

```python
MotorBoard(
    "front",                     # board name, used in "front.a"
    a_en=12, a_ph=5,             # J3 pins 3, 4
    b_en=13, b_ph=6,             # J3 pins 5, 6 (optional)
    sleep_pin=26,                # J3 pin 9 (optional; needed for coast in PH/EN mode)
    fault_pin=19,                # J3 pin 10 (optional; needed for stall detection without a sensor)
    mode="ph_en",                # "ph_en" (JP1 pads 1-2, default) or "pwm" (JP1 pads 2-3)
    logic_voltage=3.3,           # VLOGIC: sets the current limit (about 2.0 A at 3.3 V, 3.0 A at 5 V)
    adc=adc, a_sense_channel=0, b_sense_channel=1,   # optional current sensing
    pwm_frequency=1000,          # software PWM; use hardware PWM for 20 kHz
    motor_names=("left", "right"),
)
```

`board.sleep()`, `board.wake()`, `board.stop_all()`, `board.coast_all()`, `board.fault_active` (nFAULT state), `board.current_limit`, `board.total_current`, `board.start_monitor()` and `board.close()` are also available. Boards work as context managers (`with MotorBoard(...) as board:`).

### Coast in PH/EN mode

In PH/EN mode the DRV8874 can only coast by sleeping, and nSLEEP is shared by both motors on a board (and by every board wired to the same GPIO). `coast()` therefore puts the line to sleep only if every other motor on it is idle. Otherwise it brakes and returns `False`. In PWM mode (`mode="pwm"`), each motor coasts independently.

## Current sensing (PinGoblin ADS1115 board)

Wire A_ISENSE and B_ISENSE (J3 pins 7, 8) to the ADS1115 inputs. One ADS1115 reads two boards. Up to four ADS1115 boards share the I2C bus (addresses 0x48–0x4B).

```python
from pingoblin_motor import ADS1115, MotorBoard

adc = ADS1115(bus=1, address=0x48)
board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, fault_pin=19,
                   adc=adc, a_sense_channel=0, b_sense_channel=1)
board.motor_a.forward(70)
print(f"{board.motor_a.current:.2f} A")
```

Board A's ISENSE output is 0.675 V/A and is zero during the PWM off-time. The ADS1115 averages each reading over about 1.2 ms, so the library divides by the PWM duty to estimate the motor current. Below 10 % duty the estimate is unreliable, so the raw reading is returned. ISENSE measures load, not speed: see the user manual section "Is ISENSE related to motor speed?".

## Faults

| `FaultType` | Detected when | Needs ADS1115? | Default action | Latches |
|---|---|---|---|---|
| `STALL` | Current ≥ `stall_current` for `stall_time` while driven, or nFAULT low (current limiting) for `stall_time` without a sensor | No | Brake | Yes |
| `CURRENT_LIMIT` | nFAULT low while driven (warning, at most every 5 s) | No | None | No |
| `DRIVER_FAULT` | nFAULT low for 0.2 s with no motor driven: output short, overcurrent or over-temperature shutdown | No | Sleep board (brake if no sleep pin) | Yes |
| `OPEN_LOAD` | Under 30 mA for 1 s while driven at ≥ 20 %: motor disconnected, broken wire, motor supply off or fuse tripped | Yes | Brake | Yes |
| `OVERLOAD` | Over `continuous_current` for `overload_time` | Yes | Brake | Yes |
| `BOARD_OVERLOAD` | Board supply current over the 3 A fuse rating for 1 s | Yes | Brake | No |
| `CHAIN_OVERLOAD` | Daisy-chain supply current over 6 A for 1 s | Yes | Brake | No |
| `SENSOR_ERROR` | ADS1115 read fails (reported once until it recovers) | Yes | None | No |

Without a sensor, a stall is inferred from nFAULT. If both motors on a board are running, the board can't tell which one stalled, so both are stopped.

React to faults:

```python
from pingoblin_motor import FaultAction, FaultPolicy, FaultType

def on_fault(fault):
    print(fault)              # [stall] front.a: motor stalled: 1.82 A for 0.5 s

board.start_monitor(on_fault=on_fault)

# Per-motor policy: coast on stall, and don't latch
policy = FaultPolicy({FaultType.STALL: FaultAction.COAST}, latch=False)
board = MotorBoard(..., a_options=dict(policy=policy))

# After a latched fault
board.motor_a.clear_fault()
```

Commanding a motor with a latched fault raises `MotorFaultError`.

## Daisy-chained boards

Each board has its own EN/PH pins. nSLEEP and nFAULT can be shared: wire them together and pass the same GPIO to every board, which gives one e-stop line and one fault line.

```python
from pingoblin_motor import ADS1115, MotorBoard, MotorChain

adc = ADS1115(address=0x48)
front = MotorBoard("front", a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                   adc=adc, a_sense_channel=0, b_sense_channel=1)
rear = MotorBoard("rear", a_en=16, a_ph=20, b_en=21, b_ph=7, sleep_pin=26, fault_pin=19,
                  adc=adc, a_sense_channel=2, b_sense_channel=3)

with MotorChain([front, rear]) as chain:          # starts the fault monitor
    chain.alias("left", "front.a")
    chain.alias("right", "front.b")
    chain["left"].forward(50)
    chain["rear.a"].reverse(30, duration=1.5)
    chain.add_fault_handler(print)
    ...
    chain.emergency_stop()                        # brake all, then sleep all boards
```

`MotorChain` also has `stop_all()`, `coast_all()`, `faults` (history), `active_faults`, `clear_faults()`, `total_current` and `check_faults()`.

## PWM frequency

gpiozero uses software PWM. The default of 1 kHz works on GPIO but makes motors whine. For silent 20 kHz, use the hardware PWM pins (GPIO12, 13, 18 or 19) for the EN lines:

```python
from pingoblin_motor import GpiozeroBackend, MotorBoard

backend = GpiozeroBackend(hardware_pwm=True, pwm_chip=0)   # pwm_chip=2 on some Pi 5 kernels
board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, backend=backend, pwm_frequency=20000)
```

This needs `dtoverlay=pwm-2chan` in `/boot/firmware/config.txt`. The Pi has two hardware PWM channels, so it covers two motors (one board).

## Testing without hardware

```python
from pingoblin_motor import MockBackend, MockCurrentSensor, MotorBoard

sensor = MockCurrentSensor()
board = MotorBoard(a_en=12, a_ph=5, backend=MockBackend(), a_sensor=sensor)
```

Run the test suite with `python -m pytest`.

## Thread safety

Motor commands are protected by a lock, so you can call them from several threads. The fault monitor, `duration` timers and ramps run in daemon threads. Fault handlers run on the monitor thread, so keep them short.
