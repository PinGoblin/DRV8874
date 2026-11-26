# Test buttons and LEDs

Each motor has a FWD and a REV button that runs it at full speed while held, in PH/EN mode
(the default). Use them to check the wiring before writing any code.

| Button | What it does |
| --- | --- |
| SW1 A FWD | Motor A forward (EN high, PH high: OUT1 positive) |
| SW2 A REV | Motor A reverse (EN high, PH low: OUT2 positive) |
| SW3 B FWD | Motor B forward |
| SW4 B REV | Motor B reverse |

- The buttons need VLOGIC (J3 pin 2) and the drivers awake (nSLEEP, J3 pin 9, high).
  With a host connected, they work while your program holds nSLEEP high. With no host,
  feed 3.3–5 V to VLOGIC from any source, such as a USB 5 V lead, connect GND to J3 pin 1,
  and link J3 pin 9 to pin 2 while you test. Do not use this link in
  [four-motor mode](four-motor-mode.md).
- They are safe to press while a host is connected, even if the host is driving the pins
  low: 1 kΩ resistors protect the host's GPIOs.
- They work as described here only in PH/EN mode (the default jumper setting). In PWM
  mode FWD brakes the motor and REV runs it forward. In four-motor mode the buttons can
  only turn motors off, and the direction LEDs do not show motor status: see
  [buttons and LEDs in four-motor mode](four-motor-mode.md#test-buttons-and-leds-in-four-motor-mode).

## LEDs

| LED | Colour | Meaning |
| --- | --- | --- |
| Power | Green | Motor supply present (after the reverse-polarity switch) |
| Fault | Red | A driver is limiting current or has detected a fault (same signal as nFAULT). In four-motor mode, a driver fault only |
| Motor A / B direction | Green | Motor running forward (OUT1 positive). Brightness follows PWM duty |
| Motor A / B direction | Red | Motor running reverse (OUT2 positive). Brightness follows PWM duty |

The direction LEDs do not show motor status in four-motor mode: see
[buttons and LEDs in four-motor mode](four-motor-mode.md#test-buttons-and-leds-in-four-motor-mode).

A direction LED may glow faintly when an unpowered motor is turned by hand. This is
normal: the motor is acting as a generator.
