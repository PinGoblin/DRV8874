# Current sensing and current limit

A_ISENSE and B_ISENSE output 0.675 V for every amp flowing in that motor. Read them with
an ADC to measure load or detect a stall. On a Raspberry Pi, use a PinGoblin ADS1115
board; an ESP32 or Pico can use its own ADC.

\[
I_{motor} = \frac{V_{ISENSE}}{0.675\ \mathrm{V/A}}
\]

- The reading is only valid while the motor is driven (EN high). During PWM off-time it
  drops to zero, so average several samples, or sample in the PWM on-time. The library
  does this for you (see [Current sensing in the API](../api/guide/current-sensing.md)).
- A stalled motor shows as a reading that sits at the current limit while the shaft isn't
  turning. A typical approach: if the reading stays above about 80% of the limit for more
  than 200 ms, stop the motor. The library's stall detection works this way.
- Each driver limits motor current on every PWM cycle (cycle-by-cycle chopping). The limit
  is set from VLOGIC:

| Host logic (VLOGIC) | Current limit per motor | ISENSE at the limit |
| --- | --- | --- |
| 3.3 V | About 2.0 A | About 1.32 V |
| 5.0 V | About 3.0 A | About 2.0 V |

- While limiting, the red fault LED lights and nFAULT goes low. Normal operation resumes
  on the next PWM cycle once the load drops. At exactly 100% duty there is no next cycle,
  so the motor stays braked until the input changes: see
  [100% duty and the current limit](configuration.md#practical-limits).
- A short circuit or overheating shuts the driver down. It retries automatically once the
  fault clears.
- In [four-motor mode](four-motor-mode.md) there is no current limit, and each ISENSE
  output carries the combined current of the two motors on that driver.
- Both motors share the 3 A board fuse. If both run near their limit at 5 V logic for more
  than a few seconds, the fuse will trip. Once power is removed it resets within about a
  minute.

## Is ISENSE related to motor speed?

Not directly. ISENSE measures current, and in a brushed DC motor current follows the
**load torque**, not the speed. At a fixed supply voltage and PWM duty, current and speed
are linearly related but in opposite directions: as load slows the motor, its back-EMF
falls and the current rises.

\[
\omega = \frac{D \cdot V_{M} - I \cdot R}{K_e}
\]

Here \(\omega\) is motor speed, \(D\) the PWM duty (0–1), \(V_M\) the motor supply
voltage, \(I\) the motor current (\(V_{ISENSE} / 0.675\)), \(R\) the motor's winding
resistance and \(K_e\) its back-EMF constant.

What this means in practice:

- **Fixed duty and supply:** speed and current fall on a straight line. Speed is highest
  at the no-load current and zero at the stall current.
- **Change the duty or the supply:** the line shifts, so the same current can mean very
  different speeds. ISENSE alone can't tell you RPM.
- **No load:** a free-running motor draws almost the same small current at any speed,
  because only friction loads it. ISENSE barely changes with RPM.

For a rough speed estimate at one fixed duty, calibrate two points. Measure the no-load
speed \(\omega_0\) and current \(I_0\), then the stall current \(I_{stall}\) (hold the
shaft for under a second). Then:

\[
\omega \approx \omega_0 \cdot \frac{I_{stall} - I}{I_{stall} - I_0}
\]

Limits of this estimate:

- The current limit (2 A or 3 A) clamps the current, so the line ends there. Any load
  heavier than that just reads as the limit.
- Winding resistance rises about 0.4% per °C as the motor warms, which shifts the line.
- Gearbox friction and brush noise add error. Average several readings.

For real speed measurement or closed-loop speed control, use a motor with an encoder (many
hobby gearmotors have a Hall encoder) and read it on the host. Use ISENSE for load and
stall detection.
