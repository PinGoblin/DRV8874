# J3 pinout

J3 is a single row of 10 pins on the left edge of the board. Looking at the component
side, pin 10 (nFAULT) is at the top and pin 1 (GND, square pad) is at the bottom, nearest
the test buttons.

!!! tip "Minimum wiring for one motor"
    - **J3:** 4 wires: GND, VLOGIC, A_EN and A_PH (pins 1–4).
    - **Motor supply:** 2 wires to J2, or one XT30 plug in J1.
    - **Motor:** 2 wires to J4.

    Every other J3 pin is optional and can be left unconnected.

![J3 pinout. Pins 3 to 6 are A_EN/A_IN1, A_PH/A_IN2, B_EN/B_IN1 and B_PH/B_IN2: The first
name applies in PH/EN mode, the second in PWM mode.](../images/j3-pinout.svg)

| Pin | Signal | Connection | Direction | PH/EN mode (default) | PWM mode |
| --- | --- | --- | --- | --- | --- |
| 10 | nFAULT | (Optional) | Output | Low = fault or current limiting. One GPIO per board | Same |
| 9 | nSLEEP | (Optional) | Input | Low = sleep, both motors coast. Pulled high on the board | Same |
| 8 | B_ISENSE | (Optional) | Output | Motor B current, 0.45 V/A | Same |
| 7 | A_ISENSE | (Optional) | Output | Motor A current, 0.45 V/A | Same |
| 6 | B_PH / B_IN2 | (Optional) | Input | Motor B direction | IN2, motor B |
| 5 | B_EN / B_IN1 | (Optional) | Input | Motor B on / speed (PWM) | IN1, motor B |
| 4 | A_PH / A_IN2 | **(Required)** | Input | Motor A direction | IN2, motor A |
| 3 | A_EN / A_IN1 | **(Required)** | Input | Motor A on / speed (PWM) | IN1, motor A |
| 2 | VLOGIC | **(Required)** | Power | Logic supply in, 3.0–5.25 V | Same |
| 1 | GND | **(Required)** | Power | Ground, common with the host | Same |

All signal pins work at 3.3 V or 5 V logic, matching whatever you feed to VLOGIC. Take
VLOGIC from the host's own 3.3 V or 5 V pin, so the logic supply and the host's GPIOs
always power up and down together. EN and
PH have 10 kΩ pull-downs and nSLEEP has a 10 kΩ pull-up on the board, so unused inputs
can be left open.

nFAULT is open-drain with a 10 kΩ pull-up to VLOGIC, and also drives the fault LED. Give
each board its own nFAULT GPIO: See [Daisy-chaining boards](daisy-chain.md).

The 4.6 A current limit keeps ISENSE at or below about 2.1 V, within the range of any
3.3 V or 5 V ADC.

Signal names: **EN** = enable (on/off and PWM speed), **PH** = phase (direction),
**IN1 / IN2** = input 1 / input 2 (PWM mode), **ISENSE** = current sense output. A leading
**n** (nSLEEP, nFAULT) means the signal is active when low.

The mode is set by the [PMODE jumper](configuration.md).
