# Specifications

| Parameter | Value |
| --- | --- |
| Motor supply (VIN) | 6–30 V DC (30 V maximum, including supply tolerance), suits 12 V and 24 V systems |
| Logic supply (VLOGIC) | 3.3–5 V, from the host |
| Logic input high | 1.5 V min (3.3 V and 5 V logic both work) |
| Default state | Drivers awake (nSLEEP pulled high); EN and PH pulled low, so motors are braked |
| Motor channels | 2, bidirectional |
| Continuous current per motor | About 1.5–2 A at 25 °C (to be confirmed by prototype thermal tests) |
| Total board current | 3 A continuous (resettable fuse: 3 A hold, 6 A trip) |
| Current limit per motor | About 3.0 A, fixed (independent of VLOGIC) |
| Current-sense output | 0.675 V per amp |
| PWM frequency | Up to 100 kHz (20 kHz recommended, which is above human hearing) |
| Driver IC | TI DRV8874 (×2) |
| Connectors | XT30 right-angle male and 5.08 mm screw terminal (power), 3.5 mm screw terminals (motors), 2.54 mm 10-pin header (logic) |
| Mounting | M2.5 holes |

!!! note "20 kHz and pets"
    20 kHz is above human hearing, but dogs, cats and some other animals can hear it.
    The motor windings make only a faint sound at this frequency; if an animal seems
    bothered, raise the PWM frequency (the DRV8874 accepts up to 100 kHz).
