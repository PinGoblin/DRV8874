# J3 pinout

J3 is a single row of 10 pins on the left edge of the board. Looking at the component
side, pin 10 (nFAULT) is at the top and pin 1 (GND, square pad) is at the bottom, nearest
the test buttons.

![J3 pinout. Pins 3 to 6 are A_EN, A_PH, B_EN and B_PH in PH/EN mode, IN1/IN2 for each
motor in PWM mode, and one input per motor (A1, A2, B1, B2) in four-motor
mode.](../images/j3-pinout.svg)

| Pin | Signal | Direction | PH/EN mode (default) | PWM mode | Four-motor mode |
| --- | --- | --- | --- | --- | --- |
| 10 | nFAULT | Output | Low = fault or current limiting | Same | Low = driver fault |
| 9 | nSLEEP | Input | Low = sleep, both motors coast | Same | Must be driven high to run. Needs a GPIO and a 4.7 kΩ pull-down |
| 8 | B_ISENSE | Output | Motor B current, 0.675 V/A | Same | Motors B1 + B2 together |
| 7 | A_ISENSE | Output | Motor A current, 0.675 V/A | Same | Motors A1 + A2 together |
| 6 | B_PH | Input | Motor B direction | IN2, motor B | Motor B2, low = on |
| 5 | B_EN | Input | Motor B on / speed (PWM) | IN1, motor B | Motor B1, low = on |
| 4 | A_PH | Input | Motor A direction | IN2, motor A | Motor A2, low = on |
| 3 | A_EN | Input | Motor A on / speed (PWM) | IN1, motor A | Motor A1, low = on |
| 2 | VLOGIC | Power | Logic supply in, 3.3–5 V | Same | Same |
| 1 | GND | Power | Ground, common with the host | Same | Same |

All signal pins work at 3.3 V or 5 V logic, matching whatever you feed to VLOGIC. Inputs
have pull-downs (pull-up on nSLEEP), so unused inputs can be left open in PH/EN and PWM
modes. In four-motor mode an open input turns its motor **on**: see
[Four-motor mode](four-motor-mode.md). nFAULT is
open-drain with a 10 kΩ pull-up to VLOGIC. The ISENSE outputs never exceed VLOGIC.

Signal names: **EN** = enable (on/off and PWM speed), **PH** = phase (direction),
**IN1 / IN2** = input 1 / input 2 (PWM mode), **ISENSE** = current sense output. A leading
**n** (nSLEEP, nFAULT) means the signal is active when low.

The mode is set by the [PMODE jumper](configuration.md).
