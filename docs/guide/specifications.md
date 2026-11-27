# Specifications

| Parameter | Value |
| --- | --- |
| Motor supply (VIN) | 6–30 V DC (30 V maximum, including supply tolerance), suits 12 V and 24 V systems |
| Logic supply (VLOGIC) | 3.0–5.25 V, from the host (3.3 V or 5 V logic, including 5 V USB-powered boards) |
| Logic input high | 1.5 V min (3.3 V and 5 V logic both work) |
| Default state | Drivers awake (nSLEEP pulled high); EN and PH pulled low, so motors are braked |
| Motor channels | 2, bidirectional |
| Continuous current per motor | 2.1–2.5 A at 25 °C target (to be confirmed by prototype thermal tests) |
| Total board current | 5 A continuous (7 A fast-acting fuse, not resettable) |
| Current limit per motor | About 4.6 A (4.2–5.1 A), fixed (independent of VLOGIC) |
| Current-sense output | 0.45 V per amp |
| PWM frequency | Up to 100 kHz (20 kHz recommended, which is above human hearing) |
| Driver IC | TI DRV8874 (×2) |
| Connectors | XT30 right-angle male and 5.08 mm screw terminal (power), 3.5 mm screw terminals (motors), 2.54 mm 10-pin header (logic) |
| Board size | 52.0 × 64.5 mm, 1.6 mm thick, 4-layer, 3 mm corner radius |
| Mounting | 4 × 2.7 mm holes for M2.5 screws, on a 45.0 × 57.5 mm rectangle, centres 3.5 mm from each edge |

!!! note "20 kHz and pets"
    20 kHz is above human hearing, but dogs, cats and some other animals can hear it.
    The motor windings make only a faint sound at this frequency; if an animal seems
    bothered, raise the PWM frequency (the DRV8874 accepts up to 100 kHz).
