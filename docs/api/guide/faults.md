# Faults and stall detection

Start the fault monitor with `board.start_monitor()` (Raspberry Pi), `board.enable_monitor()`
(MicroPython), or by creating a [`MotorChain`][pingoblin_motor.chain.MotorChain].

| [`FaultType`][pingoblin_motor.faults.FaultType] | Detected when | Needs a current sensor? | Default action | Latches |
| --- | --- | --- | --- | --- |
| `STALL` | Current ≥ `stall_current` for `stall_time` while driven, or nFAULT low (current limiting) for `stall_time` without a sensor | ✗ | Brake | ✓ |
| `CURRENT_LIMIT` | nFAULT low while driven (warning, at most every 5 s) | ✗ | None | ✗ |
| `DRIVER_FAULT` | nFAULT low for 0.2 s with no motor driven: Output short, overcurrent or over-temperature shutdown | ✗ | Sleep board (brake if no sleep pin) | ✓ |
| `OPEN_LOAD` | Under 30 mA for 1 s while driven at ≥ 20 %: Motor disconnected, broken wire, motor supply off or fuse blown | ✓ | Brake | ✓ |
| `OVERLOAD` | Over `continuous_current` for `overload_time` | ✓ | Brake | ✓ |
| `BOARD_OVERLOAD` | Board supply current over the 5 A continuous board rating for 1 s | ✓ | Brake | ✗ |
| `CHAIN_OVERLOAD` | Daisy-chain supply current over 6 A for 1 s | ✓ | Brake | ✗ |
| `SENSOR_ERROR` | Current-sensor read fails (reported once until it recovers) | ✓ | None | ✗ |

Without a sensor, a stall is inferred from nFAULT. If both motors on a board are running,
the board cannot tell which one stalled, so both are stopped.

## Tuning detection

| Option | Default | Meaning |
| --- | --- | --- |
| `stall_current` | 80 % of the current limit | Amps treated as a stall |
| `stall_time` | `0.5` | Seconds the stall condition must last |
| `start_grace` | `0.3` | Ignore stall and open-load for this long after a start (start-up surge) |
| `open_load_current` / `open_load_time` | `0.03` A / `1.0` s | Open-load detection |
| `continuous_current` / `overload_time` | `1.5` A / `5` s | Overload detection |
| `policy` | defaults | A [`FaultPolicy`][pingoblin_motor.faults.FaultPolicy]: What to do on each fault, and whether faults latch |

## Reacting to faults

```python
from pingoblin_motor import FaultAction, FaultPolicy, FaultType, MotorBoard

def on_fault(fault):
    print(fault)              # [stall] front.a: motor stalled: 2.61 A for 0.5 s

# Per-motor policy: coast on stall, and don't latch
policy = FaultPolicy({FaultType.STALL: FaultAction.COAST}, latch=False)
board = MotorBoard(a_en=12, a_ph=5, sleep_pin=26, fault_pin=19, a_options=dict(policy=policy))
board.start_monitor(on_fault=on_fault)

board.motor_a.add_fault_handler(lambda f: print("motor A:", f.message))
```

A latched fault stops the motor and blocks it: Commanding it raises
[`MotorFaultError`][pingoblin_motor.faults.MotorFaultError] until you clear it.

```python
board.motor_a.clear_fault()
```

## Stall homing

Driving into an end stop and stopping on the stall is a low-cost way to home an axis without a limit switch:

```python
from pingoblin_motor import FaultAction, FaultPolicy, FaultType, MotorBoard

policy = FaultPolicy({FaultType.STALL: FaultAction.BRAKE}, latch=False)
board = MotorBoard(a_en=12, a_ph=5, sleep_pin=26, fault_pin=19,
                   a_options=dict(policy=policy, stall_time=0.2))
board.start_monitor()
board.motor_a.reverse(40)
board.motor_a.wait(timeout=10)       # returns when the stall brakes the motor
```

See `python/examples/stall_homing.py` and `micropython/examples/pico_asyncio_stall_homing.py`.
