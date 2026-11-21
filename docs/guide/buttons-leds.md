# Test buttons and LEDs

Each motor has a FWD and a REV button that runs it at full speed while held. Use them to
check the wiring before writing any code.

| Button | What it does |
| --- | --- |
| SW1 A FWD | Motor A forward (EN high, PH low) |
| SW2 A REV | Motor A reverse (EN high, PH high) |
| SW3 B FWD | Motor B forward |
| SW4 B REV | Motor B reverse |

- The buttons need VLOGIC (J3 pin 2). With no host connected, feed 3.3–5 V to VLOGIC from
  any source, such as a USB 5 V lead, and GND to J3 pin 1.
- They are safe to press while a host is connected, even if the host is driving the pins
  low: 1 kΩ resistors protect the host's GPIOs.
- They work only in PH/EN mode (the default jumper setting).

!!! info "Pressing FWD and REV together gives reverse"
    REV drives both EN and PH high, while FWD only drives EN, so REV wins. The result is
    the same as pressing REV alone and can't harm the board or the host. Release one
    button before pressing the other: flipping from forward to reverse at full speed
    causes a current surge (the fault LED flickers as the current limit catches it) and is
    hard on gearboxes.

## LEDs

| LED | Colour | Meaning |
| --- | --- | --- |
| Power | Green | Motor supply present (after the reverse-polarity switch) |
| Fault | Red | A driver is limiting current or has detected a fault (same signal as nFAULT) |
| Motor A / B direction | Red | Motor running forward (OUT2 positive). Brightness follows PWM duty |
| Motor A / B direction | Green | Motor running reverse (OUT1 positive) |

A direction LED may glow faintly if you spin an unpowered motor by hand. This is normal:
the motor is acting as a generator.
