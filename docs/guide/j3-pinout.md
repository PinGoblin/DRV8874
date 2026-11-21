# J3 pinout

J3 is a single row of 10 pins on the left edge of the board. Looking at the component
side, pin 10 (nFAULT) is at the top and pin 1 (GND, square pad) is at the bottom, nearest
the test buttons.

![J3 pinout. Pins 3 to 6 are A_EN, A_PH, B_EN and B_PH in PH/EN mode, and IN1/IN2 for each
motor in PWM mode.](../images/j3-pinout.svg)

| Pin | Signal | Direction | PH/EN mode (default) | PWM mode |
| --- | --- | --- | --- | --- |
| 10 | nFAULT | Output | Low = fault or current limiting | Same |
| 9 | nSLEEP | Input | Low = sleep, both motors coast | Same |
| 8 | B_ISENSE | Output | Motor B current, 0.675 V/A | Same |
| 7 | A_ISENSE | Output | Motor A current, 0.675 V/A | Same |
| 6 | B_PH | Input | Motor B direction | IN2, motor B |
| 5 | B_EN | Input | Motor B on / speed (PWM) | IN1, motor B |
| 4 | A_PH | Input | Motor A direction | IN2, motor A |
| 3 | A_EN | Input | Motor A on / speed (PWM) | IN1, motor A |
| 2 | VLOGIC | Power | Logic supply in, 3.3–5 V | Same |
| 1 | GND | Power | Ground, common with the host | Same |

All signal pins work at 3.3 V or 5 V logic, matching whatever you feed to VLOGIC. Inputs
have pull-downs (pull-up on nSLEEP), so unused inputs can be left open. nFAULT is
open-drain with a 10 kΩ pull-up to VLOGIC. The ISENSE outputs never exceed VLOGIC.

The mode is set by the [PMODE jumper](configuration.md).
