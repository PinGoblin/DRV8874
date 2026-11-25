# Quick start

Wire J3 to the host first, then the motors, then the motor supply last.

1. With everything unpowered, connect J3 to the host using the table below. You need at
   least GND, VLOGIC, and one EN and one PH pin per motor.
2. Connect each motor to J4 (A) or J5 (B).
3. Connect power: a battery to J1 (XT30), or a 6–18 V supply to J2 (positive to VIN+,
   negative to GND). See [Powering the board](power.md). The green power LED
   lights.
4. Power the host. Motors stay stopped (braked) until the host drives an EN pin high.
5. Optional: press a FWD or REV [test button](buttons-leds.md) to check each motor turns
   before writing any code.

## Wiring

| J3 pin | Signal | Raspberry Pi (BCM) | ESP32 DevKit | Pico |
| --- | --- | --- | --- | --- |
| 1 | GND | GND (pin 6) | GND | GND |
| 2 | VLOGIC | 3V3 (pin 1) | 3V3 | 3V3(OUT) |
| 3 | A_EN | GPIO12 (PWM0) | GPIO25 | GP2 |
| 4 | A_PH | GPIO5 | GPIO26 | GP3 |
| 5 | B_EN | GPIO13 (PWM1) | GPIO27 | GP4 |
| 6 | B_PH | GPIO6 | GPIO33 | GP5 |
| 7 | A_ISENSE | PinGoblin ADS1115 board (the Pi has no ADC) | GPIO34 (ADC1) | GP26 (ADC0) |
| 8 | B_ISENSE | PinGoblin ADS1115 board | GPIO35 (ADC1) | GP27 (ADC1) |
| 9 | nSLEEP | GPIO26 (optional) | GPIO32 (optional) | GP6 (optional) |
| 10 | nFAULT | GPIO19 (optional) | GPIO39 (optional, input only) | GP7 (optional) |

On an ESP32, avoid the boot-strapping pins (GPIO0, 2, 12, 15) and GPIO14, which toggles
during boot. Use ADC1 pins for current sense, because ADC2 cannot be read while Wi-Fi is
on. Leave nSLEEP unconnected if you don't need it: the board pulls it high.

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

On a Raspberry Pi the library uses 1 kHz software PWM by default, which makes motors
whine. For silent 20 kHz drive, use hardware PWM on GPIO12 and GPIO13: see
[PWM frequency](../api/guide/concepts.md#pwm-frequency). MicroPython boards use 20 kHz
hardware PWM by default.
