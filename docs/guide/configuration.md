# Configuration: PMODE jumper (JP1)

JP1 is a 3-pad solder jumper that sets the control mode for both drivers. It ships with
pads 1–2 bridged (PH/EN mode).

!!! warning
    Never leave all three pads open: that selects a half-bridge mode this board isn't
    designed for.

| JP1 setting | Mode | J3 pin 3 / 5 | J3 pin 4 / 6 | Test buttons | Library |
| --- | --- | --- | --- | --- | --- |
| 1–2 bridged (default) | PH/EN | EN: on/off + PWM speed | PH: direction | Work | `mode="ph_en"` |
| 2–3 bridged | PWM (IN1/IN2) | IN1 | IN2 | Do not use | `mode="pwm"` |

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
