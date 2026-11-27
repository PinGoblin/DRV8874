# Glossary

Abbreviations and terms used in this manual, in alphabetical order.

| Term | Full name | Meaning on this board |
| --- | --- | --- |
| 2S / 3S / 4S | 2, 3 or 4 cells in series | Battery pack size. A 3S lithium pack has three cells in series (12.6 V when full) |
| ADC | Analog-to-digital converter | The part of a microcontroller (or an add-on chip) that measures a voltage. Used to read ISENSE |
| ADS1115 | — | A common 16-bit, 4-channel I2C ADC module. Adds analog inputs to a Raspberry Pi, which has none |
| AGM | Absorbent glass mat | A sealed type of lead-acid battery |
| API | Application programming interface | The functions and classes the Python / MicroPython library provides. See the API section |
| AWG | American wire gauge | Wire size. Smaller numbers are thicker wire (18 AWG is thicker than 22 AWG) |
| Back-EMF | Back electromotive force | The voltage a spinning motor generates, which opposes the supply. It rises with speed |
| BCM | Broadcom numbering | Raspberry Pi GPIO numbering by the chip's pin names (GPIO12 and so on), not the header pin positions |
| BMS | Battery management system | Protection circuit inside a battery pack that guards against over-charge, over-discharge and short circuits |
| Brake | — | Both motor terminals connected to ground. The motor stops quickly |
| Coast | — | Both motor terminals disconnected. The motor spins down freely |
| DC | Direct current | Current that flows in one direction. The board drives brushed DC motors from a DC supply |
| Duty cycle | — | The percentage of each PWM cycle that the signal is on. Sets the motor speed |
| EN | Enable | PH/EN mode input. High drives the motor, low brakes it. PWM on EN sets the speed |
| ESP32 | — | A family of Wi-Fi microcontrollers made by Espressif, often programmed in MicroPython |
| FWD / REV | Forward / reverse | Test button labels. Forward means OUT1 positive (green LED) |
| GND | Ground | The 0 V reference, common to the board, the motor supply and the host |
| GPIO | General-purpose input/output | A microcontroller pin that software can set high or low, or read. On the Pico these are named GP0, GP1 and so on |
| Half-bridge | — | One pair of switches on one output: One to the supply (high side) and one to ground (low side). An H-bridge is two half-bridges |
| H-bridge | — | Four switches around the motor that can connect each terminal to the supply or to ground, so the motor can run in both directions. Each DRV8874 is one H-bridge |
| HAT | Hardware attached on top | A Raspberry Pi add-on board that plugs onto the Pi's 40-pin header |
| High side / low side | — | The switch from an output to the supply (high side), or to ground (low side) |
| I2C | Inter-integrated circuit | A two-wire bus (SDA and SCL) for connecting chips such as the ADS1115 |
| IC | Integrated circuit | A chip |
| IN1 / IN2 | Input 1 / input 2 | PWM mode inputs. Each one controls one side of the motor (OUT1 or OUT2) |
| ISENSE | Current sense | J3 output giving a voltage proportional to motor current (0.45 V per amp) |
| LED | Light-emitting diode | An indicator light |
| Li-ion / LiPo / LiFePO4 | Lithium-ion / lithium polymer / lithium iron phosphate | Rechargeable battery types. Full-charge voltage per cell is 4.2 V for Li-ion and LiPo, and 3.65 V for LiFePO4 |
| MIT | Massachusetts Institute of Technology licence | The open-source licence the software is released under |
| MOSFET | Metal-oxide-semiconductor field-effect transistor | An electronic switch. Q1 is a MOSFET that blocks a reversed supply |
| n (prefix) | Not | A leading n means the signal is active when low. nSLEEP low = sleep, nFAULT low = fault |
| nFAULT | Not fault | J3 output that goes low on a fault or while current limiting. Use one host GPIO per board |
| nSLEEP | Not sleep | J3 input. Low puts both drivers to sleep (motors coast). Pulled high on the board |
| OUT1 / OUT2 | Output 1 / output 2 | The two motor terminals of each driver, labelled A1 / A2 (J4) and B1 / B2 (J5). Forward = OUT1 positive |
| PH | Phase | PH/EN mode input that sets direction. High = forward, low = reverse |
| PH/EN | Phase / enable | The default control mode: PH sets the direction, EN sets on/off and speed |
| PMODE | Mode select (TI's pin name) | The driver input, set by jumper JP1, that selects PH/EN or PWM mode |
| PWM | Pulse-width modulation | Switching a pin on and off rapidly. The duty cycle sets the average power to the motor |
| PWR | Power | Label of the power LED (D3) |
| Reference designators | — | Part labels printed on the board: C = capacitor, D = diode or LED, F = fuse, H = mounting hole, J = connector, JP = jumper, Q = transistor, R = resistor, SW = switch, U = IC |
| RPM | Revolutions per minute | Motor speed |
| Slow decay / fast decay | — | What the motor does in the PWM off-time: Slow decay brakes it (firm, linear speed control), fast decay lets it coast |
| TI | Texas Instruments | Maker of the DRV8874 motor driver |
| TVS | Transient-voltage suppressor | A diode (D2) that clamps voltage spikes on the motor supply |
| UPS | Uninterruptible power supply | As in the PinGoblin UPS HAT+. Its QUAD and DUAL battery packs can also power this board |
| USB | Universal serial bus | The connector on most microcontroller boards. A USB lead can supply the 5 V for VLOGIC when testing |
| VIN | Voltage in | The motor supply input at J1 and J2, 6–30 V |
| VLOGIC | Logic voltage | The host's supply at its GPIO voltage (3.3 V on a Raspberry Pi, ESP32 or Pico), fed in on J3 pin 2. Sets the logic level |
| VM | Motor voltage | The motor supply after the fuse and reverse-polarity protection |
| XT30 | — | A small, keyed, two-pin power connector made by AMASS, common on battery packs. J1 is an XT30 |
