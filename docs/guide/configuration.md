# Configuration: PMODE jumper (JP1)

JP1 is a 3-pad solder jumper that sets the control mode for both drivers. It ships with
pads 1–2 bridged (PH/EN mode).

!!! warning
    Never leave all three pads open: that selects a half-bridge mode this board isn't
    designed for.

| JP1 setting | Mode | J3 pin 3 / 5 | J3 pin 4 / 6 | Test buttons | Library |
| --- | --- | --- | --- | --- | --- |
| 1–2 bridged (default) | PH/EN | EN: on/off + PWM speed | PH: direction | Forward / reverse control | `mode="ph_en"` |
| 2–3 bridged | PWM (IN1/IN2) | IN1 | IN2 | Not supported: FWD brakes the motor and REV runs it forward | `mode="pwm"` |

To change it, cut the thin trace between pads 1 and 2 with a craft knife, check with a
multimeter that they're open, then bridge pads 2 and 3 with solder.

## PWM mode truth table

Motor A; motor B is the same.

| IN1 (pin 3) | IN2 (pin 4) | OUT1 | OUT2 | Motor |
| --- | --- | --- | --- | --- |
| Low | Low | Open | Open | Coast |
| High | Low | High | Low | Forward |
| Low | High | Low | High | Reverse |
| High | High | Low | Low | Brake |

PWM mode suits libraries written for two-input drivers such as the L298N or DRV8833
(gpiozero `Motor`, Arduino `analogWrite` on either pin). With gpiozero's `Motor` class,
pass `forward=` J3 pin 3 (IN1) and `backward=` J3 pin 4 (IN2) so its directions match the
table above.

In PWM mode each motor can coast on its own, without sleeping the board.

## Speed control in each mode

In both modes, speed comes from the **PWM duty cycle**: the fraction of each PWM period
for which the motor is connected to the supply. A motor driven at 60% duty sees, on
average, about 60% of VM, so it runs at roughly 60% of its full speed at that load. What
differs between the modes is which pin you switch, and what the motor does in the
off-time.

| Mode | Forward at speed *d* | Reverse at speed *d* | Off-time | Response |
| --- | --- | --- | --- | --- |
| PH/EN (default) | PH high, EN PWM at duty *d* | PH low, EN PWM at duty *d* | Brake | Firm, close to linear |
| PWM, slow decay (what the library uses) | IN1 high, IN2 PWM at duty 1 − *d* | IN2 high, IN1 PWM at duty 1 − *d* | Brake | The same as PH/EN |
| PWM, fast decay | IN1 PWM at duty *d*, IN2 low | IN2 PWM at duty *d*, IN1 low | Coast | Softer; speed falls away at low duty |

**PH/EN mode.** EN carries the speed and PH the direction, so a single PWM channel per
motor is enough. During the off-time both low-side switches are on (brake, also called
slow decay), so the motor's current keeps circulating and the speed follows the duty cycle
closely, even at light load. This is the easiest mode to use and gives the best low-speed
control. The library's `speed_pc` (0–100) is the EN duty cycle.

**PWM mode, slow decay.** One input is held high and the other is switched. The motor is
driven while the switched input is *low*, so its duty is inverted: for 30% speed forward,
hold IN1 high and run IN2 at 70%. The off-time is a brake, so the response matches PH/EN
mode. The library does this inversion for you in `mode="pwm"`.

**PWM mode, fast decay.** One input is held low and the other is switched at the speed
duty, which is how most two-input motor libraries work, including gpiozero's `Motor` class
and Arduino code that calls `analogWrite()` on one pin. In the off-time both outputs turn
off and the motor coasts, while its current flows back into the supply. Expect less torque
and a less linear response at low duty: a lightly loaded motor may barely slow until the
duty is well below 50%. It works, but slow decay gives finer control.

### Practical limits

- **Minimum speed.** Most small motors don't start turning until the duty cycle reaches
  about 10–30%, because of friction and gearbox losses. Below that they hum without
  turning. The library's `min_speed_pc` raises any non-zero speed to this value.
- **PWM frequency.** Use 20 kHz where the host supports it: it's above human hearing and
  gives smooth current. Lower frequencies (1–5 kHz, such as the Pi's software PWM) work the
  same way but make the motor whine.
- **Full speed.** 100% duty applies the full supply to the motor. The test buttons drive
  EN high, so they always run at 100%.

!!! warning "100% duty and the current limit"
    The drivers limit current on every PWM cycle and restart on the next PWM edge. At
    exactly 100% duty there are no edges, so if a motor stalls and reaches the current
    limit, the driver holds it in brake (and lights the fault LED) until the input
    changes. To recover, change the speed, stop and restart, or release and press the test
    button again. If a stall is likely at full speed, run at 99% instead: the motor is
    effectively at full speed, and the current limit then recovers on its own.
