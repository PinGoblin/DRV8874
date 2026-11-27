# Concepts

## Object model

| Class | What it is |
| --- | --- |
| [`MotorBoard`][pingoblin_motor.board.MotorBoard] | One PinGoblin DRV8874 board: two motors plus its nSLEEP and nFAULT lines |
| [`Motor`][pingoblin_motor.motor.Motor] | One motor channel (`board.motor_a`, `board.motor_b`, or `board["a"]`) |
| [`MotorChain`][pingoblin_motor.chain.MotorChain] | Several daisy-chained boards managed as one system, with one fault monitor |
| [`ADS1115Channel`][pingoblin_motor.sensors.ADS1115Channel] | Connects one input of a PinGoblin ADS1115 board, read with its own [`pingoblin_ads1115`](https://pingoblin.github.io/ADS1115/) library, to a motor for current sensing |
| [`FaultMonitor`][pingoblin_motor.monitor.FaultMonitor] | Detects faults. Started by `board.start_monitor()` or by `MotorChain` |
| [`Fault`][pingoblin_motor.faults.Fault], [`FaultType`][pingoblin_motor.faults.FaultType], [`FaultPolicy`][pingoblin_motor.faults.FaultPolicy], [`FaultAction`][pingoblin_motor.faults.FaultAction] | Fault records and how each motor reacts to them |
| [`GpiozeroBackend`][pingoblin_motor.backends.GpiozeroBackend], [`MockBackend`][pingoblin_motor.backends.MockBackend] | Hardware access. `MockBackend` runs without a Pi |

## Creating a board

```python
from pingoblin_motor import MotorBoard

board = MotorBoard(
    "front",                     # board name, used in "front.a"
    a_en=12, a_ph=5,             # J3 pins 3, 4
    b_en=13, b_ph=6,             # J3 pins 5, 6 (optional)
    sleep_pin=26,                # J3 pin 9 (optional; needed for coast in PH/EN mode)
    fault_pin=19,                # J3 pin 10 (optional; one GPIO per board)
    mode="ph_en",                # "ph_en" (JP1 open, default) or "pwm" (JP1 bridged)
    motor_names=("left", "right"),
    motor_options=dict(ramp_time=0.5),   # options for both motors
)
```

Several boards can share one `sleep_pin`, but each needs its own `fault_pin`. The current
limit is fixed at about 3 A per motor (`board.current_limit`).

Boards work as context managers (`with MotorBoard(...) as board:`), which brake the motors
and release the pins on exit.

## Speed and direction

Speed is a percentage, 0–100. Direction is chosen by the method:

```python
m = board.motor_a
m.forward(60)              # 60 % forward
m.reverse(40)              # 40 % reverse
m.run(-25)                 # signed: negative = reverse, 0 = stop
m.speed_pc = 80            # change speed while running
m.start()                  # resume the last direction and speed
m.forward(50, duration=2)  # stop after 2 s (returns at once)
m.forward(50, duration=2, wait=True)   # ... and block until it stops
```

Useful motor options (pass in `motor_options=`, `a_options=` or `b_options=`):

| Option | Default | Meaning |
| --- | --- | --- |
| `invert` | `False` | Swap forward and reverse (instead of swapping wires) |
| `min_speed_pc` | `0` | Raise any non-zero speed to at least this (motor deadband) |
| `ramp_time` | `0` | Seconds to ramp 0→100 %. Soft start and soft speed changes |
| `reverse_delay` | `0.1` | Brake time before reversing a running motor |
| `motor_voltage` | `None` | The motor's rated voltage. Limits PWM duty to `motor_voltage / supply_voltage`, so 100 % speed never over-volts the motor. Needs `supply_voltage=` on the board |

For example, a 6 V motor on a 12 V supply:

```python
board = MotorBoard(a_en=12, a_ph=5, supply_voltage=12.0,
                   a_options=dict(motor_voltage=6.0))
board.motor_a.forward(100)     # 50 % duty: 6 V average across the motor
```

See [Choosing a motor](../../guide/choosing-a-motor.md) for which motors suit the board.

The fault-detection options are covered in [Faults](faults.md). The full list is in the
[`Motor`][pingoblin_motor.motor.Motor] reference.

## Stop, brake and coast

| Call | Outputs | Effect |
| --- | --- | --- |
| `stop()` / `brake()` | Both low | Motor stops quickly |
| `coast()` | Open | Motor spins down freely |
| `board.sleep()` | Open, both motors | Both drivers sleep (near-zero current) |

In PH/EN mode the DRV8874 can only coast by sleeping, and nSLEEP is shared by both motors
on a board (and by every board wired to the same GPIO). `coast()` therefore sleeps the line
only if every other motor on it is idle. Otherwise it brakes and returns `False`. In PWM
mode (`mode="pwm"`), each motor coasts independently.

## PWM frequency

On the Raspberry Pi, gpiozero uses software PWM. The default of 1 kHz works on any GPIO
but makes motors whine. For silent 20 kHz, use the hardware PWM pins (GPIO12, 13, 18 or
19) for the EN lines:

```python
from pingoblin_motor import GpiozeroBackend, MotorBoard

backend = GpiozeroBackend(hardware_pwm=True, pwm_chip=0)   # pwm_chip=2 on some Pi 5 kernels
board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, backend=backend, pwm_frequency=20000)
```

This needs `dtoverlay=pwm-2chan` in `/boot/firmware/config.txt` and the
`rpi-hardware-pwm` package. The Pi has two hardware PWM channels, so it covers two motors
(one board).

MicroPython boards use hardware PWM on any pin at 20 kHz by default (`pwm_freq=`).

## Thread safety (Raspberry Pi)

Motor commands are protected by a lock, so you can call them from several threads. The
fault monitor, `duration` timers and ramps run in daemon threads. Fault handlers run on the
monitor thread, so keep them short.
