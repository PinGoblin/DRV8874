# Test buttons and LEDs

Each motor has a FWD and a REV button that runs it at full speed while held, in PH/EN mode
(the default). Use them to check the wiring before writing any code.

| Button | What it does |
| --- | --- |
| SW1 A FWD | Motor A forward (EN high, PH high: OUT1 positive) |
| SW2 A REV | Motor A reverse (EN high, PH low: OUT2 positive) |
| SW3 B FWD | Motor B forward |
| SW4 B REV | Motor B reverse |

- The buttons need only the motor supply. No host and no VLOGIC are required: The board
  powers itself from the motor supply while a button is pressed.
- Without a host, the motor coasts to a stop when the button is released. With a host
  connected, it brakes.
- They do nothing while the host holds nSLEEP (J3 pin 9) low.
- They are safe to press while a host is connected, even if the host is driving the pins
  low: 1 kΩ resistors protect the host's GPIOs. A pressed button drives its inputs high
  whatever the host does, but cannot drive them low. For example, if the host holds PH
  high, REV runs the motor forward.
- They always drive the motor at 100 % duty, that is, at the full supply voltage. Do not
  use them with a motor rated below the supply voltage.
- The table applies to PH/EN mode (the default jumper setting) only. For PWM mode, see
  the next section.

## Buttons in PWM mode (JP1 bridged)

In PWM mode the drivers read the EN and PH lines as IN1 and IN2. The buttons still drive
the same lines, so their labels no longer match what the motor does:

| Button held | IN1 (EN line) | IN2 (PH line) | Motor |
| --- | --- | --- | --- |
| None, host absent | Low | Low | Coasts (outputs off) |
| FWD (SW1 / SW3) | High | High | Brakes (both outputs low) |
| REV (SW2 / SW4) | High | Low | Runs forward (OUT1 positive, green LED) |

There is no button combination that runs a motor in reverse in PWM mode. To check reverse
wiring with the buttons, open JP1 (see [Configuration](configuration.md)), or run the
motor in reverse from the host.

## LEDs

| LED | Colour | Meaning |
| --- | --- | --- |
| Power | Green | Motor supply present (after the reverse-polarity switch) |
| Fault | Red | A driver has shut down: Output short, overheating, or motor supply below 4.5 V (same signal as nFAULT) |
| Motor A / B direction | Green | Motor running forward (OUT1 positive). Brightness follows PWM duty |
| Motor A / B direction | Red | Motor running reverse (OUT2 positive). Brightness follows PWM duty |

A direction LED may glow faintly when an unpowered motor is turned by hand. This is
normal: The motor is acting as a generator.
