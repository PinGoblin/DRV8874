# Configuration: PMODE jumper (JP1)

JP1 is a 2-pad solder jumper that sets the control mode for both drivers. It is supplied
open (PH/EN mode). The drivers read JP1 when they wake, so a change takes effect at the
next power-up or wake from sleep. Disconnect and reconnect power after changing JP1.

When a `sleep_pin` is configured, the library holds nSLEEP low for at least 1.5 ms when the board
is created, then releases it. This makes the drivers read JP1 again after VLOGIC has
settled, so a slowly rising logic supply cannot leave them in the wrong mode. If you do
not connect nSLEEP to the host, disconnect and reconnect power if a motor in PWM mode
does not stop at the 4.6 A current limit.

| JP1 setting | Mode | Library | Details |
| --- | --- | --- | --- |
| Open (default) | PH/EN | `mode="ph_en"` | [PH/EN mode](controlling-motors.md#phen-mode-default) |
| Bridged | PWM (IN1/IN2) | `mode="pwm"` | [PWM mode](controlling-motors.md#pwm-mode-in1in2) |

## Changing the mode

1. Disconnect the motor supply and VLOGIC.
2. For PWM mode, bridge the two JP1 pads with solder.
3. To return to PH/EN mode, remove the solder with desoldering braid and check with a
   multimeter that the pads are no longer connected.
4. Tell the library which mode is set (`mode="pwm"` or `mode="ph_en"`).
