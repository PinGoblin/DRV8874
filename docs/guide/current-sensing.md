# Current sensing and current limit

A_ISENSE and B_ISENSE output 0.45 V for every amp flowing in that motor. Read them with
an ADC to measure load or detect a stall. On a Raspberry Pi, use a PinGoblin ADS1115
board; an ESP32 or Pico can use its own ADC.

\[
I_{motor} = \frac{V_{ISENSE}}{0.45\ \mathrm{V/A}}
\]

- The reading is only valid while the motor is driven (EN high). During PWM off-time it
  drops to zero, so average several samples, or sample in the PWM on-time. The library
  does this for you (see [Current sensing in the API](../api/guide/current-sensing.md)).
- A stalled motor shows as a reading that sits at the current limit while the shaft is not
  turning. A typical approach: If the reading stays above about 80% of the limit for more
  than 200 ms, stop the motor. The library's stall detection works this way.
- Each driver limits motor current by itself: When the current reaches the limit, the
  driver brakes for 25 µs, then drives again. This works at any duty, including 100%. The
  limit is fixed:

| Current limit per motor | ISENSE at the limit |
| --- | --- |
| 4.6 A (peak), fixed | 2.07 V |

- Current limiting is normal operation: The fault LED stays off and nFAULT stays high.
- A short circuit, overheating or a motor supply below 4.5 V shuts the driver down, lights
  the red fault LED and pulls nFAULT low. The driver restarts by itself once the cause
  clears.
- Both motors share a 5 A continuous board rating. Two motors held at the 4.6 A current
  limit (for example, both stalled) draw 9.2 A, which can blow the board's 7 A fuse,
  and the fuse is not resettable. Detect stalls and stop the motors, as the library does.

## ISENSE and motor speed

ISENSE does not measure motor speed. It measures current, and in a brushed DC motor
current follows the **load torque**, not the speed. At a fixed supply voltage and PWM duty, current and speed
are linearly related but in opposite directions: As load slows the motor, its back-EMF
falls and the current rises.

\[
\omega = \frac{D \cdot V_{M} - I \cdot R}{K_e}
\]

Here \(\omega\) is motor speed, \(D\) the PWM duty (0–1), \(V_M\) the motor supply
voltage, \(I\) the motor current (\(V_{ISENSE} / 0.45\)), \(R\) the motor's winding
resistance and \(K_e\) its back-EMF constant.

What this means in practice:

- **Fixed duty and supply:** Speed and current fall on a straight line. Speed is highest
  at the no-load current and zero at the stall current.
- **Change the duty or the supply:** The line shifts, so the same current can mean very
  different speeds. ISENSE alone cannot give the RPM.
- **No load:** A free-running motor draws almost the same small current at any speed,
  because only friction loads it. ISENSE barely changes with RPM.

For a rough speed estimate at one fixed duty, calibrate two points. Measure the no-load
speed \(\omega_0\) and current \(I_0\), then the stall current \(I_{stall}\) (hold the
shaft for under a second). Then:

\[
\omega \approx \omega_0 \cdot \frac{I_{stall} - I}{I_{stall} - I_0}
\]

Limits of this estimate:

- The 4.6 A current limit clamps the current, so the line ends there. Any heavier
  load reads as the limit.
- Winding resistance rises about 0.4% per °C as the motor warms, which shifts the line.
- Gearbox friction and brush noise add error. Average several readings.

For real speed measurement or closed-loop speed control, use a motor with an encoder (many
hobby gearmotors have a Hall encoder) and read it on the host. Use ISENSE for load and
stall detection.
