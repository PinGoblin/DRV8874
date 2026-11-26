# Choosing a motor

The board suits brushed DC motors that draw no more than about 3 A in normal use. Each
driver limits its motor to about 3 A (2.8–3.4 A across component tolerances), and the
board as a whole is rated for 3 A continuous. A motor that needs more current than this
still runs, but only with reduced torque.

Check two figures on the motor's datasheet before buying: its **stall current** and its
**rated voltage**.

## Current

| Stall current at the voltage used | Result on this board |
| --- | --- |
| Up to 3 A | Full performance. The current limit never acts, even at stall |
| 3–6 A | Good. The current limit acts only near stall, and the motor's efficient operating range is fully available |
| 6–25 A | Light loads only. The motor reaches its no-load speed, but torque is limited to roughly 10–40 % of its stall torque and the fault LED flickers under load |
| Above 25 A, or no-load current above 2 A | Not suitable. The motor spends most of its time at the current limit, the driver runs hot, and start-up may be reported as a stall |

Where only the no-load current and the stall current are given, estimate the share of
stall torque available at the board's limit as:

\[
\frac{3\,\text{A} - I_{no\text{-}load}}{I_{stall} - I_{no\text{-}load}}
\]

Motor manufacturers recommend running continuously at no more than 20–30 % of stall
torque, so a motor whose stall current is 4–12 A uses the board well.

### Typical motors

| Motor type | Rated voltage | No-load current | Stall current | Suitability |
| --- | --- | --- | --- | --- |
| Small plastic gearmotor (robot wheel) | 3–10 V | About 0.07 A | About 0.25 A | Full performance |
| Slow gearhead motor | 12 V | 0.03–0.07 A | 0.35–1.7 A | Full performance |
| 37 mm metal gearmotor, 24 V | 24 V | About 0.1 A | About 3 A | Full performance |
| 37 mm metal gearmotor, 12 V | 12 V | About 0.2 A | About 5.5 A | Good |
| 130-size hobby motor | 1.5–4.5 V | About 0.25 A | Up to about 3.5 A | Good. Set `motor_voltage` (see below) |
| 280/300-size motor | 6 V | About 0.55 A | About 5.6 A | Good. About half of stall torque available. Set `motor_voltage` above a 6 V supply |
| Large gearhead motor (high torque) | 12 V | About 0.45 A | About 18 A | Light loads only |
| 380/540-size high-speed motor | 12 V | 0.6–0.8 A | 17–24 A | Light loads only |
| 550/775-size high-power motor | 6–12 V | 1.3–4 A | 60–110 A | Not suitable |

!!! tip "Choose the higher-voltage version of a motor"
    Many motors are sold in 12 V and 24 V versions with the same speed and torque. The 24 V
    version draws half the current, so on this board it delivers twice the torque before the
    current limit acts. The board accepts supplies up to 30 V for this reason.

## Voltage

A motor can run from a supply above its rated voltage only if the PWM duty is limited, so
that the average voltage across it does not exceed its rating. For example, a 6 V motor on
a 12 V supply must never run above 50 % duty. At higher duty it overheats and its brushes
wear quickly.

The library does this for you. Give the board its supply voltage and each motor its rated
voltage, and 100 % speed is scaled to the safe duty:

```python
board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6,
                   supply_voltage=12.0,                 # motor supply on J1/J2
                   a_options=dict(motor_voltage=6.0),   # 100 % speed = 50 % duty
                   b_options=dict(motor_voltage=12.0))  # 100 % speed = 100 % duty
```

The test buttons always drive the motor at 100 % duty. Do not use them with a motor rated
below the supply voltage.

## Stall detection for small motors

Without a current sensor, the library detects a stall from the driver's current-limit
signal (nFAULT). A motor whose stall current is below 3 A never reaches the current
limit, so a stall is not detected and the motor carries its full stall current until it is
stopped. Small gearmotors can overheat within seconds in this condition. To protect them,
fit a current sensor and set `stall_current`
(see [Current sensing and current limit](current-sensing.md)), or stop the motor in your
own code with a time-out or an end-stop switch.

## Large motors and start-up

A motor with a high no-load current, or a heavy load on its shaft, can take longer than
the library's default stall time (0.8 s in total) to reach speed at the current limit.
If the library reports `STALL` at every start, set `ramp_time` for a soft start, or raise
`start_grace`.
