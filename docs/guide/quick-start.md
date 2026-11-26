# Quick start

Wire J3 to the host first, then the motors, then the motor supply last.

1. With everything unpowered, connect J3 to the host using the table below. You need at
   least GND, VLOGIC, nSLEEP, and one EN and one PH pin per motor.
2. Connect each motor to J4 (A) or J5 (B). For less electrical noise, solder a 100 nF
   capacitor across each motor's terminals and twist its leads (see [Connectors](connectors.md)).
3. Connect power: a battery to J1 (XT30), or a 6–18 V supply to J2 (positive to VIN+,
   negative to GND). See [Powering the board](power.md). The green power LED
   lights.
4. Power the host. The drivers stay asleep, with the motors off, until your program drives
   nSLEEP high.
5. Optional: check each motor turns with the FWD and REV [test buttons](buttons-leds.md)
   before writing any code. With no program running, link J3 pin 9 to pin 2 while you
   test, so the drivers wake.

## Wiring

| J3 pin | Signal | Raspberry Pi (BCM) | ESP32 DevKit | Pico |
| --- | --- | --- | --- | --- |
| 1 | GND | GND (pin 6) | GND | GND |
| 2 | VLOGIC | 3V3 (pin 1) | 3V3 | 3V3(OUT) |
| 3 | A_EN | GPIO12 (PWM0) | GPIO25 | GP2 |
| 4 | A_PH | GPIO5 | GPIO26 | GP3 |
| 5 | B_EN | GPIO13 (PWM1) (optional) | GPIO27 (optional) | GP4 (optional) |
| 6 | B_PH | GPIO6 (optional) | GPIO33 (optional) | GP5 (optional) |
| 7 | A_ISENSE | PinGoblin ADS1115 board (optional; the Pi has no ADC) | GPIO34, ADC1 (optional) | GP26, ADC0 (optional) |
| 8 | B_ISENSE | PinGoblin ADS1115 board (optional) | GPIO35, ADC1 (optional) | GP27, ADC1 (optional) |
| 9 | nSLEEP | GPIO26 | GPIO32 | GP6 |
| 10 | nFAULT | GPIO19 (optional) | GPIO39 (optional, input only) | GP7 (optional) |

nSLEEP is pulled low on the board, so the drivers sleep until the host drives it high.
The library does this automatically. If you do not need sleep or coast control, you can
link J3 pin 9 to pin 2 (VLOGIC) instead of using a GPIO, except in
[four-motor mode](four-motor-mode.md). Pins 5 and 6 are needed only for motor B, and pins
7 and 8 only for current sensing.

Every input on J3 has a 10 kΩ pull-down, so the motors stay off while the host boots,
whichever GPIOs you use. On a Raspberry Pi, do not use GPIO2 and GPIO3: they carry I2C for
the ADS1115 board. On an ESP32, avoid the boot-strapping pins (GPIO0, 2, 12, 15): the
board's pull-downs can stop the ESP32 booting normally. Also avoid GPIO14, which toggles
during boot. Use ADC1 pins for current sense, because ADC2 cannot be read while Wi-Fi is
on. If you use more than one board, give each its own nFAULT GPIO (see
[Daisy-chaining boards](daisy-chain.md)).

## First program

Install the library (see [Installation](../api/guide/install.md)), then:

=== "Raspberry Pi"

    ```python
    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
    board.start_monitor(on_fault=print)        # stall and fault detection

    board.motor_a.forward(60, duration=2, wait=True)   # 60 % for 2 s, then brake
    board.motor_b.reverse(40)
    board.motor_b.speed_pc = 80                # change speed while running
    board.motor_b.coast()                      # spin down freely
    board.close()
    ```

=== "MicroPython (ESP32)"

    ```python
    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39)
    board.enable_monitor(on_fault=print)

    board.motor_a.forward(60, duration=2, wait=True)   # blocks, still checks faults
    board.motor_b.reverse(40)
    board.pause(1.5)                                   # sleep that keeps checking faults
    board.coast_all()
    ```

=== "MicroPython (Pico)"

    ```python
    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=2, a_ph=3, b_en=4, b_ph=5, sleep_pin=6, fault_pin=7)
    board.enable_monitor(on_fault=print)
    board.motor_a.forward(60, duration=2, wait=True)
    ```

The MicroPython library uses 20 kHz hardware PWM by default. On a Raspberry Pi the library
defaults to 1 kHz, because the Pi's standard GPIO PWM is generated in software and is
unreliable at higher frequencies; at 1 kHz the motors whine audibly. For silent 20 kHz
drive on a Pi, enable hardware PWM on GPIO12 and GPIO13: see
[PWM frequency](../api/guide/concepts.md#pwm-frequency).
