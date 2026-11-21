# Current sensing

Board A's ISENSE outputs give 0.675 V per amp (see the
[User Guide](../../guide/current-sensing.md)). The library turns that into amps on
`motor.current`, and uses it for stall, overload and open-load detection.

## PinGoblin ADS1115 board

The Raspberry Pi has no ADC, so use a PinGoblin ADS1115 board. Wire A_ISENSE and B_ISENSE
(J3 pins 7, 8) to the ADS1115 inputs. One ADS1115 reads two boards, and up to four
ADS1115 boards share the I2C bus (addresses 0x48–0x4B).

=== "Raspberry Pi"

    ```python
    from pingoblin_motor import ADS1115, MotorBoard

    adc = ADS1115(bus=1, address=0x48)
    board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, fault_pin=19,
                       adc=adc, a_sense_channel=0, b_sense_channel=1)
    board.motor_a.forward(70)
    print(f"{board.motor_a.current:.2f} A")
    ```

=== "MicroPython"

    ```python
    from machine import I2C, Pin
    from pingoblin_motor import ADS1115, MotorBoard

    i2c = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)   # Pico: I2C(0, sda=Pin(0), scl=Pin(1))
    adc = ADS1115(i2c, address=0x48)
    board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, fault_pin=39,
                       adc=adc, a_sense_channel=0, b_sense_channel=1)
    ```

ISENSE is zero during the PWM off-time. The ADS1115 averages each reading over about
1.2 ms, so the library divides by the PWM duty to estimate the motor current. Below 10 %
duty the estimate is unreliable, so the raw reading is returned.

## The microcontroller's own ADC (MicroPython)

```python
from pingoblin_motor import ADCChannel, MotorBoard

board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, fault_pin=39,
                   a_sensor=ADCChannel(34), b_sensor=ADCChannel(35))
```

The built-in ADC takes instant samples, so with PWM each one is either the full motor
current or zero. The library averages 16 samples per reading, which gives a usable mean
but is noisier than the ADS1115. On the Pico, ISENSE is read against the 3.3 V supply
(`ADCChannel(26, vref=3.3)`).

## Board and chain totals

`board.total_current` and `chain.total_current` add up the motor currents. They drive the
`BOARD_OVERLOAD` (3 A fuse) and `CHAIN_OVERLOAD` (6 A terminals) checks.

!!! note
    ISENSE measures load, not speed. A free-running motor draws about the same current at
    any speed.
