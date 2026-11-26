# Configuration: PMODE jumper (JP1)

JP1 is a 3-pad solder jumper that sets the control mode for both drivers. It is supplied
with pads 1–2 bridged (PH/EN mode). The drivers read JP1 when they wake, so a change takes
effect at the next power-up or wake from sleep.

| JP1 setting | Mode | Motors | Library | Details |
| --- | --- | --- | --- | --- |
| Pads 1–2 bridged (default) | PH/EN | 2, both directions | `mode="ph_en"` | [PH/EN mode](controlling-motors.md#phen-mode-default) |
| Pads 2–3 bridged | PWM (IN1/IN2) | 2, both directions | `mode="pwm"` | [PWM mode](controlling-motors.md#pwm-mode-in1in2) |
| All pads open | Four-motor | 4, one direction each | `mode="independent"` | [Four-motor mode](four-motor-mode.md) |

!!! warning
    Leaving all three pads open selects four-motor mode. Do this only on purpose: in that
    mode an input that is not driven runs its motor at full speed while the drivers are
    awake. Read [Four-motor mode](four-motor-mode.md) first.

## Changing the mode

1. Disconnect the motor supply and VLOGIC.
2. Cut the thin trace between pads 1 and 2 with a craft knife.
3. Check with a multimeter that pads 1 and 2 are no longer connected.
4. For PWM mode, bridge pads 2 and 3 with solder. For four-motor mode, leave all pads open.
5. Clean off any flux. In four-motor mode PMODE must float: the drivers recognise "open"
   only between about 0.9 V and 1.2 V, so flux residue can select the wrong mode.

To return to PH/EN mode, remove any bridge between pads 2 and 3 and bridge pads 1 and 2.
