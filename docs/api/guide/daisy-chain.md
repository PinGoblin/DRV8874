# Daisy-chained boards

Each board has its own EN/PH pins and its **own nFAULT pin**. nSLEEP can be shared: wire
it to every board and pass the same GPIO, which gives one e-stop line.
[`MotorBoard`][pingoblin_motor.board.MotorBoard] raises
[`ConfigError`][pingoblin_motor.faults.ConfigError] if a `fault_pin` is already used by
another open board.
See [Daisy-chaining boards](../../guide/daisy-chain.md) for the wiring and current limits.

```python
from pingoblin_motor import ADS1115, MotorBoard, MotorChain

adc = ADS1115(address=0x48)
front = MotorBoard("front", a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                   adc=adc, a_sense_channel=0, b_sense_channel=1)
rear = MotorBoard("rear", a_en=16, a_ph=20, b_en=21, b_ph=7, sleep_pin=26, fault_pin=24,
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

Motors are addressed as `"board.motor"` (for example `"front.a"`), or by an alias.
[`MotorChain`][pingoblin_motor.chain.MotorChain] also has `stop_all()`, `coast_all()`,
`faults` (history), `active_faults`, `clear_faults()`, `total_current` and
`check_faults()`.
