# Faults and stall detection

Start the fault monitor with `board.start_monitor()` (Raspberry Pi), `board.enable_monitor()`
(MicroPython), or by creating a [`MotorChain`][pingoblin_motor.chain.MotorChain].

| [`FaultType`][pingoblin_motor.faults.FaultType] | Detected when | Needs a current sensor? | Default action | Latches |
| --- | --- | --- | --- | --- |
| `STALL` | Current ≥ `stall_current` for `stall_time` while driven | ✓ | Brake | ✓ |
| `DRIVER_FAULT` | nFAULT low for 0.2 s: Output short, driver overheated, or motor supply below 4.5 V | ✗ | Sleep board (brake if no sleep pin) | ✓ |
| `OPEN_LOAD` | Under 30 mA for 1 s while driven at ≥ 20 %: Motor disconnected, broken wire or motor supply off | ✓ | Brake | ✓ |
| `OVERLOAD` | Over `continuous_current` for `overload_time` | ✓ | Brake | ✓ |
| `BOARD_OVERLOAD` | Board supply current over the 5 A continuous board rating for 1 s | ✓ | Brake | ✗ |
| `CHAIN_OVERLOAD` | Daisy-chain supply current over 6 A for 1 s | ✓ | Brake | ✗ |
| `SENSOR_ERROR` | Current-sensor read fails (reported once until it recovers) | ✓ | None | ✗ |

nFAULT goes low only for real driver faults, not for normal current limiting. Stall,
open-load and overload detection therefore need a current sensor. Without one, the driver
still limits each motor to 4.6 A and shuts down if it overheats (`DRIVER_FAULT`).

## Tuning detection

| Option | Default | Meaning |
| --- | --- | --- |
| `stall_current` | 80 % of the current limit | Amps treated as a stall |
| `stall_time` | `0.5` | Seconds the stall condition must last |
| `start_grace` | `0.3` | Ignore stall and open-load for this long after a start (start-up surge) |
| `open_load_current` / `open_load_time` | `0.03` A / `1.0` s | Open-load detection |
| `continuous_current` / `overload_time` | `1.5` A / `5` s | Overload detection |
| `fault_retry_time` | `2.0` | Seconds after a stall, open load or overload before the motor may run again |
| `policy` | defaults | A [`FaultPolicy`][pingoblin_motor.faults.FaultPolicy]: What to do on each fault, and whether faults latch |

## Reacting to faults

```python
from pingoblin_motor import FaultAction, FaultPolicy, FaultType, MotorBoard

def on_fault(fault):
    print(fault)   # [stall] front.a: motor stalled (3.90 A for 0.5 s): check for a jam or too much load

# Per-motor policy: coast on stall, and don't latch
policy = FaultPolicy({FaultType.STALL: FaultAction.COAST}, latch=False)
board = MotorBoard(a_en=12, a_ph=5, sleep_pin=26, fault_pin=19, a_options=dict(policy=policy))
board.start_monitor(on_fault=on_fault)

board.motor_a.add_fault_handler(lambda f: print("motor A:", f.message))
```

A latched fault stops the motor. The next command to that motor raises
[`MotorFaultError`][pingoblin_motor.faults.MotorFaultError] once, with the cause and what to
do. Errors are never silent: catch the exception to handle it.

| Fault | The motor runs again on the next command once |
| --- | --- |
| `DRIVER_FAULT` | nFAULT is high again (short removed, driver cooled, battery charged) |
| `STALL`, `OPEN_LOAD`, `OVERLOAD` | `fault_retry_time` (2 s) has passed. If the cause is still there, it is detected again |

```python
from pingoblin_motor import MotorFaultError

try:
    board.motor_a.forward(60)
except MotorFaultError as exc:
    print("Motor stopped:", exc)   # for example: check for a jam or too much load
```

`motor.clear_fault()` clears a latched fault at once, without waiting.

## Stall homing

Driving into an end stop and stopping on the stall is a low-cost way to home an axis without a
limit switch. It needs current sensing on that motor:

```python
from pingoblin_ads1115 import ADS1115
from pingoblin_motor import FaultAction, FaultPolicy, FaultType, MotorBoard

adc = ADS1115(bus=1, address=0x48, rate=860)      # A_ISENSE (J3 pin 7) on AIN0
policy = FaultPolicy({FaultType.STALL: FaultAction.BRAKE}, latch=False)
board = MotorBoard(a_en=12, a_ph=5, sleep_pin=26, fault_pin=19, adc=adc, a_sense_channel=0,
                   a_options=dict(policy=policy, stall_time=0.2, stall_current=1.0))
board.start_monitor()
board.motor_a.reverse(40)
board.motor_a.wait(timeout=10)       # returns when the stall brakes the motor
```

See `python/examples/stall_homing.py` and `micropython/examples/pico_asyncio_stall_homing.py`.
