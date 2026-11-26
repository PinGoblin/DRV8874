# User Guide

![Board A, angled view of the top side](../images/board-a-3d.png)

Board A drives two brushed DC motors in both directions, or up to four motors in one
direction, from any 3.3 V or 5 V microcontroller, such as a Raspberry Pi, ESP32, Raspberry
Pi Pico or Arduino. It uses two TI DRV8874 drivers: speed is set by PWM, and each driver
has a current-sense output that can be read with an ADC.

- Two independent motor channels, motor supply 6–18 V (12 V nominal)
- Direction + speed control (PH/EN, phase/enable mode), with a jumper for two-input
  PWM (pulse-width modulation) mode
- [Four-motor mode](four-motor-mode.md): up to four one-direction motors, such as pumps
  and fans
- Analog current feedback per motor (0.675 V/A) for stall detection
- Built-in current limit, overcurrent and over-temperature protection
- Reverse-polarity protection, surge suppressor (TVS) and a 3 A resettable fuse on the motor supply
- Push buttons to test each motor without writing code (PH/EN mode, the default)
- Direction LEDs per motor (except in four-motor mode), plus power and fault LEDs
- Power through-terminal for daisy-chaining several boards from one supply
- Safe start-up: the drivers sleep until the host enables them, so motors stay off while
  the host boots, in every mode

## Where to start

1. Find your way around the board: [Board overview](board-overview.md).
2. Read [Important safety information](safety.md).
3. Wire the board using [Quick start](quick-start.md).
4. Check each motor with the [test buttons](buttons-leds.md) (PH/EN mode).
5. Install the library from the [API](../api/index.md) section and run the first example.

If something does not work, see [Troubleshooting](troubleshooting.md).
