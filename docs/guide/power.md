# Powering the board

The board runs from **6–30 V DC**, which covers 12 V and 24 V systems. It has two power connectors, wired in parallel:

| Connector | Type | Use |
| --- | --- | --- |
| J1 | XT30, right-angle male | Batteries and supplies with an XT30 plug |
| J2 | 5.08 mm screw terminal (pin 1 VIN+, pin 2 GND) | Wired supplies, or power out to the next board |

The board draws up to 5 A continuously in total (both motors), and briefly up to 9.2 A when both motors are at the current limit. The supply or battery must be able to deliver that, plus the motors' start-up surge.

!!! danger "Only connect one power source at a time to J1 and J2"
    J1 and J2 are connected together, and so is every board in a daisy chain. For example,
    never connect a battery to J1 and a separate power supply to J2 at the same time, on
    this board or on any other board in the chain: the supply would push current into the
    battery with no charge control.

## PinGoblin battery packs

### One pack (6.0–8.4 V)

Plug a PinGoblin QUAD or DUAL pack (from the [UPS HAT+](https://github.com/PinGoblin/UPS_HAT)) straight into J1. The board runs
normally, but motors rated for 12 V run at roughly two-thirds of their 12 V speed.

### Two packs in series (12.0–16.8 V)

Two packs in series give 14.4 V nominal: the right supply for 12 V motors, solenoids and
steppers. Join them with an XT30 series lead:

| Lead connector | Type | Connects to |
| --- | --- | --- |
| Input A | XT30 male (cable) | Pack A |
| Input B | XT30 male (cable) | Pack B |
| Output | XT30 female (cable) | J1 on the board |

Inside the lead, using 18 AWG wire:

- Input A **−** to Output **−**
- Input A **+** to Input B **−**
- Input B **+** to Output **+**

Rules for two packs:

- Use two packs of the same type (both QUAD or both DUAL), fully charged on the UPS HAT+
  before use, and switch both on.
- Charge each pack on its own on the UPS HAT+. Never charge through the series lead.
- If either pack's protection switches off, the whole string stops. This is safe: recharge
  both packs.

!!! danger "Never plug the series lead into a UPS HAT+"
    The lead outputs up to 16.8 V. The UPS HAT+ battery input is for one 2S pack (8.4 V
    maximum) and will be destroyed. Label the lead "MOTOR BOARDS ONLY – 16.8 V".

### Low battery

The board has no low-voltage cut-off: it keeps running until the packs' own protection
switches off at 2.8 V per cell (5.6 V for one pack, 11.2 V for two). This is safe, but
regularly discharging that far shortens cell life. For the longest life, stop at 3.1 V per
cell, where the UPS HAT+ software stops:

| Packs | Full | Stop at | Packs switch off at |
| --- | --- | --- | --- |
| One | 8.4 V | 6.2 V | 5.6 V |
| Two in series | 16.8 V | 12.4 V | 11.2 V |

To measure the supply from your host, use a resistor divider into an ADC input (for
example 100 kΩ over 22 kΩ, which gives 3.0 V at 16.8 V).

## Other batteries

Any battery with its own protection circuit (BMS), an XT30 plug and a full-charge voltage
of 30 V or less:

| Battery | Full charge | Suitable? |
| --- | --- | --- |
| 2S Li-ion / LiPo | 8.4 V | ✓ |
| 3S Li-ion / LiPo | 12.6 V | ✓ |
| 4S Li-ion / LiPo | 16.8 V | ✓ |
| 4S LiFePO4 | 14.6 V | ✓ |
| 12 V lead-acid / AGM | 13.8–14.7 V while charging | ✓ |
| 5S Li-ion / LiPo | 21.0 V | ✓ |
| 6S Li-ion / LiPo | 25.2 V | ✓ |
| 7S Li-ion / LiPo | 29.4 V | ✓ |
| 8S LiFePO4 (24 V) | 29.2 V | ✓ |
| 24 V lead-acid / AGM | 27.6–29.4 V while charging | ✓ if the charger stays at or below 30 V |
| 8S Li-ion / LiPo or more | 33.6 V or more | ✗ |

## Wired supplies

Connect plug-packs and bench supplies to J2: positive to pin 1 (VIN+), negative to pin 2
(GND). Keep the supply at or below 30 V, including its tolerance: a supply labelled 30 V can
measure higher. A 12 V supply suits most hobby motors, and a 24 V supply suits industrial
pumps, valves and actuators.
