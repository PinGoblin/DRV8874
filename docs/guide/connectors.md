# Connectors

The board has six connectors: two for power (see [Powering the board](power.md)), two for
motors, one logic header (J3, see [J3 pinout](j3-pinout.md)) and the VM header J6 for
[four-motor mode](four-motor-mode.md).

| Connector | Type | Pin 1 | Pin 2 | Use |
| --- | --- | --- | --- | --- |
| J1 VIN | XT30, right-angle male | GND (−) | VIN+ (+, 6–18 V) | Battery or XT30 supply in |
| J2 VIN / THRU | 5.08 mm screw terminal | VIN+ (6–18 V) | GND | Wired supply in, or power out to the next board. In parallel with J1 |
| J4 MOTOR A | 3.5 mm screw terminal | OUT1 (A1) | OUT2 (A2) | Motor A |
| J5 MOTOR B | 3.5 mm screw terminal | OUT1 (B1) | OUT2 (B2) | Motor B |
| J6 VMx4 | 2.54 mm 2×2 header | VM | VM | All four pins are VM. Common supply lead for the motors in [four-motor mode](four-motor-mode.md) |
| J3 LOGIC | 2.54 mm 1×10 header | GND | VLOGIC | Host connection, see [J3 pinout](j3-pinout.md) |

Motor polarity does not matter in PH/EN or PWM mode: if a motor turns the wrong way, swap
its two wires or invert the direction in code (the library's `invert` option). In
four-motor mode each motor runs one way only, so connect its + lead to J6 and its − lead
to the terminal. Screw terminals take wire up
to about 18 AWG. You can also solder wires straight into the pads.

!!! warning "J6 is the motor supply"
    J6 carries VM, the full motor supply (up to 18 V). Use it only for motors in
    four-motor mode. Never connect it to J3 or to the host.

The connectors are supplied loose, so you can fit screw terminals, headers or solder wires
directly.

!!! tip "Reduce motor noise"
    Brushed motors spark at their brushes and are the main source of electrical noise in a
    motor project. Solder a **100 nF ceramic capacitor directly across the motor's own
    terminals** (at the motor, not at the board), and **twist the two motor wires together**
    along their length. This keeps the noise out of your host's ADC readings, wireless
    signals and nearby electronics.
