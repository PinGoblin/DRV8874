# Four-motor mode

In four-motor mode, each DRV8874 runs its two outputs separately instead of as one
H-bridge. Each output can then drive its own **one-direction** (unidirectional) motor,
so one board drives up to four. This suits pumps, fans, blowers and other motors that
only ever turn one way. Each motor connects between one of the motor terminals and one of
the four VM pins on J6.

| | PH/EN or PWM mode | Four-motor mode |
| --- | --- | --- |
| Motors per board | 2, both directions | 4, one direction each |
| Motor wiring | Across J4 or J5 | From one J4 / J5 terminal to a J6 VM pin |
| Current limit | 2 A (3.3 V logic) or 3 A (5 V logic) per motor | **None** |
| Current sensing | Per motor | Per pair: A1 + A2, B1 + B2 |
| Coast one motor on its own | PWM mode only | No (only by sleeping the whole board) |
| JP1 | Pads 1–2 or 2–3 bridged | All three pads open |

!!! danger "In four-motor mode a motor runs while its input is low"
    The board's pull-down resistors, which keep the motors stopped in the other modes,
    hold every input low. Whenever the drivers are awake and the host is not driving the
    inputs high, **all four motors run at full speed with no current limit**.

    The board guards against this with a 10 kΩ pull-down on nSLEEP: the drivers sleep
    (outputs open, motors off) unless the host holds nSLEEP high. This protection requires that you:

    1. Wire **nSLEEP (J3 pin 9) to a GPIO** on the host, and drive it high only while your
       program is controlling the inputs. The library does this: it keeps the drivers
       asleep until the first run command, and puts them to sleep again when the board is
       closed.
    2. **Do not also connect nSLEEP to VLOGIC** while in four-motor mode, as you might for
       button tests in the other modes. With nSLEEP held at VLOGIC the drivers stay awake,
       so any input that is not driven runs its motor. In addition, whenever the nSLEEP GPIO drives
       low, it is shorted to VLOGIC: the current can exceed the GPIO pin's limit and damage
       your microcontroller board.

    To verify: with your program stopped and VLOGIC present, nSLEEP should measure below
    0.5 V and no motor should turn.

## Setting up

1. **Set JP1 to all pads open.** Cut the thin trace between pads 1 and 2 with a craft
   knife. Leave pads 2 and 3 unbridged. Check with a multimeter that pad 2 is open to both
   pad 1 and pad 3. The drivers read JP1 each time they wake, so the change takes effect
   at the next wake-up or power-up.
2. **Wire nSLEEP to a GPIO**, as described above.
3. **Wire the motors.** Connect each motor between its terminal and any of the four pins on
   J6. J6 carries VM: the motor supply after the fuse and reverse-polarity protection.
4. **Check the direction.** Current flows from VM, through the motor, into the terminal.
   Connect the motor's **+** lead to J6 and its **−** lead to the terminal, so it turns
   the way it would on a battery. To reverse it, swap its two leads.

| Motor | Terminal | Controlled by | Library name |
| --- | --- | --- | --- |
| A1 | J4 A1 (OUT1 of U1) | J3 pin 3 (A_EN) | `a1` |
| A2 | J4 A2 (OUT2 of U1) | J3 pin 4 (A_PH) | `a2` |
| B1 | J5 B1 (OUT1 of U2) | J3 pin 5 (B_EN) | `b1` |
| B2 | J5 B2 (OUT2 of U2) | J3 pin 6 (B_PH) | `b2` |

The terminal labels A1, A2, B1 and B2 are printed on the board next to J4 and J5.

You do not need all four motors: leave unused terminals empty. You also do not need
external flyback diodes. When an input goes high, the driver's high-side switch carries
the motor's current back to VM. That makes this mode suitable for solenoids and valves
too.

!!! tip "Reduce motor noise"
    As in the other modes, solder a 100 nF ceramic capacitor across each motor's own
    terminals and twist its two wires together.

## How it works

Each output is a half-bridge: one switch to VM and one to ground. The input selects
which switch is on.

| nSLEEP | Input | Output | Motor |
| --- | --- | --- | --- |
| High | Low | Low-side on: 0 V | **Runs**: full VM across it |
| High | High | High-side on: VM | Off. Both motor leads are at VM, so it brakes gently |
| Low | Any | Open | Off, coasting (drivers asleep) |

### Speed

Speed comes from the PWM duty cycle, as in the other modes, but the motor is driven
while the input is **low**. The duty is therefore inverted: for 30% speed, the input is
low 30% of the time, so it runs at 70% duty. The library does this inversion for you.
During the off-time the motor brakes through the high-side switch, so the speed follows
the duty cycle closely, like slow decay in the other modes. See
[Speed control](controlling-motors.md#speed-control) for the
practical limits on minimum speed and PWM frequency.

### No current limit

The DRV8874 turns its current regulation off in this mode, so the current limit set by
VLOGIC does not apply. A stalled motor draws its full stall current. What still protects
the board:

- each driver's overcurrent shutdown, which trips at several amps and retries
  automatically;
- the drivers' over-temperature shutdown;
- the 3 A resettable fuse, shared by all four motors.

Choose motors whose **running** current, all four together, stays under 3 A. Keep each
pair (A1 + A2, or B1 + B2) under about 2 A continuous, which is the same thermal budget
as one motor in the other modes. If the board fuse keeps tripping, a motor is probably
stalling or the total load is too high.

### Current sensing

ISENSE now measures the low-side current of both outputs of a driver together. A_ISENSE
reads A1 + A2, and B_ISENSE reads B1 + B2, at the usual 0.675 V per amp.

!!! warning "ISENSE can exceed 3.3 V in this mode"
    With no current limit, ISENSE passes 3.3 V once a pair draws about 4.9 A (for example,
    two stalled motors) and can rise to about 4.5 V. The 1 kΩ series resistor limits the
    current into the host's pin to about 1 mA, but that is still outside a 3.3 V ADC's
    rating. Use a PinGoblin ADS1115 board, or choose motors that cannot draw that much
    between them. Averaged over
several samples, it gives the supply current the pair draws. The library reads it with
`board.driver_current("a")`. Per-motor stall detection is not possible in this mode,
because the board cannot tell the two motors apart.

nFAULT, and the red fault LED, now only signal a real driver fault: an overcurrent,
over-temperature or undervoltage shutdown.

## Test buttons and LEDs in four-motor mode

The test buttons can only turn motors **off** in this mode, never on. Pressing a button
pulls its inputs high, and a high input is "off". When no program is driving nSLEEP high,
the drivers are asleep and the buttons do nothing.

| Button | While held |
| --- | --- |
| SW1 A FWD | A1 and A2 off (drives both A_EN and A_PH high) |
| SW2 A REV | A1 off (drives A_EN high) |
| SW3 B FWD | B1 and B2 off |
| SW4 B REV | B1 off |

A button press overrides your program, so a motor can stop while the software still
reports it running.

The direction LEDs sit across each driver's two outputs, so they light only when the two
outputs differ. They show the **difference** between a pair of motors, not what either
motor is doing. For driver A (D8 green, D9 red; D13 and D14 work the same way for driver B):

| A1 | A2 | J4 A1 / A2 | LEDs |
| --- | --- | --- | --- |
| Off | Off | VM / VM | Both off |
| Running | Off | 0 V / VM | Red |
| Off | Running | VM / 0 V | Green |
| Running | Running | 0 V / 0 V | Both off |
| Asleep | Asleep | Open | Both off |

With PWM speed control, the LEDs glow dimly and may flicker, depending on how the two
duty cycles overlap. Ignore the direction LEDs in this mode.

The other LEDs work normally. The green power LED shows the motor supply, and the red
fault LED shows a driver shutdown.

## Using the library

Pass `mode="independent"` and a `sleep_pin`. The board then has four motors named `a1`,
`a2`, `b1` and `b2` (or your own names). Each one has the usual `forward()`, `run()`,
`stop()`, `speed_pc`, `duration=` and ramp options, but no `reverse()`.

```python
from pingoblin_motor import MotorBoard

with MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                mode="independent") as board:
    board["a1"].forward(60)                    # J4 A1 at 60 %
    board["b2"].forward(100, duration=3, wait=True)
    print(board.driver_current("a"))           # A1 + A2, if a sensor is configured
```

The MicroPython library works the same way. See
[`HalfBridgeMotor`][pingoblin_motor.motor.HalfBridgeMotor] in the API reference.

## Driving the pins directly

Without the library, set the inputs **high** before you drive nSLEEP high, and drive
nSLEEP low before your program releases the pins. To run a motor at speed *s* (0–1),
drive its input with PWM at duty 1 − *s*. A steady high stops it; a steady low runs it
at full speed.
