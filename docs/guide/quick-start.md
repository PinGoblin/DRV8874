# Quick start

Wire J3 to the host first, then the motors, then the motor supply last.

1. With everything unpowered, connect J3 to the host using the table below. One motor
   needs only 4 wires to J3: GND, VLOGIC, A_EN and A_PH. Add B_EN and B_PH for a second
   motor.
2. Connect each motor to J4 (A) or J5 (B). For less electrical noise, solder a 100 nF
   capacitor across each motor's terminals and twist its leads (see [Connectors](connectors.md)).
3. Connect power: A battery to J1 (XT30), or a 6–30 V supply to J2 (positive to VIN+,
   negative to GND). See [Powering the board](power.md). The green power LED
   lights.
4. Power the host. Motors stay stopped (braked) until the host drives an EN pin high.
5. Optional: Check each motor turns with the FWD and REV [test buttons](buttons-leds.md)
   before writing any code.

## Wiring

| J3 pin | Signal | Connection | Raspberry Pi (BCM) | ESP32 DevKit | Pico |
| --- | --- | --- | --- | --- | --- |
| 1 | GND | **(Required)** | GND (pin 6) | GND | GND |
| 2 | VLOGIC | **(Required)** | 3V3 (pin 1) | 3V3 | 3V3(OUT) |
| 3 | A_EN | **(Required)** | GPIO12 (PWM0) | GPIO25 | GP2 |
| 4 | A_PH | **(Required)** | GPIO5 | GPIO26 | GP3 |
| 5 | B_EN | (Optional) | GPIO13 (PWM1) | GPIO27 | GP4 |
| 6 | B_PH | (Optional) | GPIO6 | GPIO33 | GP5 |
| 7 | A_ISENSE | (Optional) | PinGoblin ADS1115 board (the Pi has no ADC) | GPIO34, ADC1 | GP26, ADC0 |
| 8 | B_ISENSE | (Optional) | PinGoblin ADS1115 board | GPIO35, ADC1 | GP27, ADC1 |
| 9 | nSLEEP | (Optional) | GPIO26 | GPIO32 | GP6 |
| 10 | nFAULT | (Optional) | GPIO19 | GPIO39 (input only) | GP7 |

nSLEEP is pulled high on the board, so it can be left unconnected if sleep and coast
control are not needed. Pins 5 and 6 are needed only for motor B, pins 7 and 8 only for
current sensing, and pin 10 only for fault detection.

EN and PH have 10 kΩ pull-downs, so the motors stay braked while the host boots,
whichever GPIOs you use. On a Raspberry Pi, do not use GPIO2 and GPIO3: They carry I2C for
the ADS1115 board. On an ESP32, avoid the boot-strapping pins (GPIO0, 2, 12, 15): The
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
drive on a Pi, enable hardware PWM on GPIO12 and GPIO13: See
[PWM frequency](../api/guide/concepts.md#pwm-frequency).
