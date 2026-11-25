# Board overview

![Board A top view with labelled connectors, controls and indicators](../images/board-a-top-labelled.png)

## Inputs

| Ref | Name | What it does |
| --- | --- | --- |
| J1 | Power in (XT30) | Battery or supply with an XT30 plug, 6–18 V. See [Powering the board](power.md) |
| J2 | Power in / through | Screw terminal in parallel with J1: a wired supply in, or power out to the next board |
| J3 | Logic header | Connects to the host: power, direction and speed inputs, current sense, sleep and fault. See [J3 pinout](j3-pinout.md) |

## Outputs

| Ref | Name | What it does |
| --- | --- | --- |
| J4 | Motor A | Motor A terminals (OUT1, OUT2) |
| J5 | Motor B | Motor B terminals (OUT1, OUT2) |

## Controls

| Ref | Name | What it does |
| --- | --- | --- |
| SW1 / SW2 | A FWD / A REV | Run motor A forward or reverse at full speed while held |
| SW3 / SW4 | B FWD / B REV | Run motor B forward or reverse at full speed while held |
| JP1 | PMODE jumper | Selects PH/EN mode (default) or PWM mode. See [Configuration](configuration.md) |

See [Test buttons and LEDs](buttons-leds.md) for how the buttons behave with a host connected.

## Indicators

| Ref | Colour | Meaning |
| --- | --- | --- |
| D3 | Green | PWR: motor supply present |
| D4 | Red | FAULT: a driver is limiting current or has a fault |
| D8 / D13 | Green | Motor A / B running forward (OUT1 positive) |
| D9 / D14 | Red | Motor A / B running reverse (OUT2 positive) |

## Main parts

| Ref | Part | Role |
| --- | --- | --- |
| U1, U2 | TI DRV8874 | H-bridge drivers for motors A and B |
| F1 | 3 A resettable fuse | Protects the board's supply |
| Q1 | P-channel MOSFET | Reverse-polarity protection |
| D2 | SMBJ18A | Surge suppressor on the motor supply |
| C1 | 220 µF | Bulk capacitor shared by both drivers |
| H1–H4 | M2.5 holes | Mounting |
