# Connectors

The board has five connectors: two for power (see [Powering the board](power.md)), two for motors and one logic header
(J3, see [J3 pinout](j3-pinout.md)).

| Connector | Type | Pin 1 | Pin 2 | Use |
| --- | --- | --- | --- | --- |
| J1 VIN | XT30, right-angle male | GND (−) | VIN+ (+, 6–18 V) | Battery or XT30 supply in |
| J2 VIN / THRU | 5.08 mm screw terminal | VIN+ (6–18 V) | GND | Wired supply in, or power out to the next board. In parallel with J1 |
| J4 MOTOR A | 3.5 mm screw terminal | OUT1 | OUT2 | Motor A |
| J5 MOTOR B | 3.5 mm screw terminal | OUT1 | OUT2 | Motor B |
| J3 LOGIC | 2.54 mm 1×10 header | GND | VLOGIC | Host connection, see [J3 pinout](j3-pinout.md) |

Motor polarity does not matter: if a motor turns the wrong way, swap its two wires or
invert the direction in code (the library's `invert` option). Screw terminals take wire up
to about 18 AWG. You can also solder wires straight into the pads.

The connectors are supplied loose, so you can fit screw terminals, headers or solder wires
directly.
