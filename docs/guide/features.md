# Features

Board A is a dual brushed DC motor driver for 3.3 V and 5 V microcontrollers. It is
designed to be connected, tested and protected without additional parts, and to be
controlled from a documented Python and MicroPython library.

## Motor drive

- **Two independent motor channels**, each with its own TI DRV8874 H-bridge, current limit
  and current-sense output.
- **Low-loss MOSFET bridges.** The DRV8874's switches have a combined resistance of about
  0.2 Ω, so little of the supply voltage is lost in the driver and it runs cool at
  normal loads.
- **Fixed 3 A current limit per motor.** The limit is set by an on-board voltage reference,
  so it does not change with the host's logic voltage. Stalls and start-up surges are
  held at about 3 A instead of reaching the motor's full stall current.
- **Two control modes**, selected by jumper JP1: PH/EN (one direction pin and one PWM pin
  per motor) or two-input PWM (IN1/IN2, which also allows coasting each motor separately).
- **PWM up to 100 kHz.** 20 kHz is recommended, which is above human hearing.

## Power and protection

- **Wide motor supply range: 6–30 V.** It covers 12 V and 24 V systems, including 24 V
  lead-acid batteries while charging, 7-cell lithium-ion packs and 8-cell LiFePO4 packs.
- **Reverse-polarity protection.** A P-channel MOSFET blocks a reversed supply with almost
  no voltage loss in normal use.
- **Surge suppressor (TVS diode)** on the motor supply, to absorb voltage spikes from long
  supply leads and from the motors.
- **4 A fuse** on the motor supply, to protect the supply wiring if a component fails.
- **Driver protection** built into each DRV8874: overcurrent, over-temperature and
  undervoltage shutdown, with automatic recovery.
- **Safe start-up.** The drive inputs are pulled low, so both motors are held in brake
  while the host boots and before its pins are configured.

## Connections

- **XT30 power input** for batteries and supplies with an XT30 plug, plus a **5.08 mm screw
  terminal** for wired supplies.
- **Power through-terminal.** The screw terminal also carries the motor supply on to the
  next board, so several boards can share one supply. See
  [Daisy-chaining boards](daisy-chain.md).
- **3.5 mm screw terminals** for the motors.
- **One 10-pin 2.54 mm header** for all logic signals, with 1 kΩ series resistors that
  protect the host's GPIO pins.
- **Works with any 3.3 V or 5 V host**, such as a Raspberry Pi, ESP32, Raspberry Pi Pico or
  Arduino. The logic supply (VLOGIC) comes from the host, so the board always matches the
  host's logic level.

## Feedback

- **Current-sense output per motor** (0.675 V per amp), for reading motor current with an
  ADC to measure load or detect a stall. See
  [Current sensing and current limit](current-sensing.md).
- **Fault output** (nFAULT), shared by both drivers on the board, which signals current
  limiting, overcurrent, over-temperature and a low motor supply.

## Testing without code

- **Forward and reverse test buttons for each motor.** With only power and VLOGIC
  connected, each motor can be checked before any software is written. See
  [Test buttons and LEDs](buttons-leds.md).
- **Direction LEDs for each motor**, plus a power LED and a fault LED.

## Software

- **Python library for the Raspberry Pi and a MicroPython library** for the ESP32 and
  Raspberry Pi Pico, with the same interface on both.
- **Speed control** in percent, with optional soft start (ramping), a minimum speed for
  the motor's deadband, and a delay before reversing.
- **Motor voltage limiting.** A motor rated below the supply voltage can be used safely:
  the library limits the PWM duty so that the motor never receives more than its rated
  voltage. See [Choosing a motor](choosing-a-motor.md).
- **Fault detection and handling**: stall, current limiting, driver shutdown, open load and
  overload, each with a configurable response (report, brake, coast or sleep).
- **Several boards from one host**, with shared sleep control and a separate fault line for
  each board.
- **Test without hardware**, using the library's mock backend.

## What sets Board A apart

Compared with typical hobby motor-driver boards, Board A combines the following in one
board:

| Feature | Board A | Typical hobby motor-driver boards |
| --- | --- | --- |
| Motor channels | 2 | Often 1 |
| Motor supply | 6–30 V | Often limited to 10–16 V, or starting at 9 V |
| Current limit | Fixed at about 3 A per motor | Often none, or set by a trimmer |
| Reverse-polarity, surge and fuse protection | All three | Usually none |
| Current-sense output to the host | Yes, per motor | Often absent |
| Test buttons and direction LEDs | Yes | Rarely |
| Battery connector (XT30) and power through-terminal | Yes | Rarely |
| Host compatibility | Any 3.3 V or 5 V microcontroller | Often one controller family |
| Documented library with fault handling | Python and MicroPython | Often example code only |
