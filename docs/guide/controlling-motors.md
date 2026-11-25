# Controlling the motors

!!! info "Terms used on this page"
    - **PWM (pulse-width modulation):** the host switches a pin on and off rapidly, many
      thousands of times a second. The **duty cycle** is the percentage of each cycle the pin
      is on, and it sets the average power, and so the speed, of the motor.
    - **PH (phase):** the direction input. High runs the motor forward, low runs it in
      reverse.
    - **EN (enable):** the drive input. High drives the motor, low brakes it. Feeding it PWM
      sets the speed.
    - **IN1 / IN2 (input 1 / input 2):** in PWM mode, the same two pins become two direct
      inputs, each controlling one side of the motor (OUT1 and OUT2).
    - **nSLEEP / nFAULT:** the leading *n* means the signal is active when low: nSLEEP low
      puts the drivers to sleep, and nFAULT goes low on a fault or current limiting.

In the default PH/EN (phase/enable) mode, each motor needs two pins: **EN** (enable) turns it
on and sets the speed with PWM (pulse-width modulation), and **PH** (phase) sets the direction. This is the same scheme as gpiozero's
`PhaseEnableMotor`, except that gpiozero calls PH low "forward" (see below). The table is for motor A; motor B is identical using B_EN and B_PH.

| nSLEEP | A_EN | A_PH | OUT1 | OUT2 | Motor | LED |
| --- | --- | --- | --- | --- | --- | --- |
| High (default) | Low | Any | Low | Low | Brake (stops quickly) | Off |
| High | High / PWM | High | High | Low | Forward | Green |
| High | High / PWM | Low | Low | High | Reverse | Red |
| Low | Any | Any | Open | Open | Coast (sleep, near-zero current) | Off |

**Speed:** drive EN with PWM. The duty cycle sets the speed, and in the PWM off-time the
motor brakes, which gives a firm, linear response. Use 20 kHz to keep the motor quiet.
1–5 kHz also works but makes the motor whine.
See [Speed control in each mode](configuration.md#speed-control-in-each-mode) for how
duty cycle maps to speed in each mode, and the limits at very low and 100% duty.

**Changing direction:** change PH at any time. To protect gearboxes, slow down or stop
briefly before reversing a heavily loaded motor. The library does this for you: it brakes
for `reverse_delay` (0.1 s by default) before reversing a running motor.

**Sleep / emergency stop:** pull nSLEEP low to put both drivers to sleep (outputs open,
motors coast). Wake-up takes about 1 ms. nSLEEP is pulled high on the board, so the
drivers are awake whenever VLOGIC is present.

**Start-up behaviour:** EN and PH have pull-down resistors, so while the host is booting
(pins floating) both motors are held in brake.

"Forward" and "reverse" here follow TI's convention for the DRV8874: PH high = forward, with
OUT1 positive (green LED). Which way the shaft actually turns depends on how the motor is
wired; swap its two leads, or use `invert=True` in the library, to change it.

!!! note "Coast and nSLEEP"
    In PH/EN mode the only way to coast is to sleep the driver, and nSLEEP is shared by
    both motors. The library's `coast()` therefore sleeps the board only when the other
    motor is idle, and otherwise brakes. In PWM mode each motor coasts on its own.

## Driving the pins directly

The [library](../api/index.md) is the easiest way to use the board, but the protocol is
simple enough to drive by hand. Speed runs from −1.0 (full reverse) to 1.0 (full forward).

=== "ESP32, MicroPython"

    ```python
    from machine import Pin, PWM, ADC
    import time

    A_EN = PWM(Pin(25), freq=20000, duty_u16=0)   # J3 pin 3
    A_PH = Pin(26, Pin.OUT, value=0)              # J3 pin 4
    A_SENSE = ADC(Pin(34)); A_SENSE.atten(ADC.ATTN_11DB)  # J3 pin 7
    FAULT = Pin(39, Pin.IN)                       # J3 pin 10 (pulled up on board)

    def drive(en, ph, speed):
        """speed -1.0..1.0; positive = forward (PH high, OUT1 positive)."""
        ph.value(1 if speed > 0 else 0)
        en.duty_u16(int(min(abs(speed), 1.0) * 65535))

    def amps(adc):
        return adc.read_uv() / 1_000_000 / 0.675   # 0.675 V per amp

    drive(A_EN, A_PH, 0.6)
    for _ in range(30):
        a = amps(A_SENSE)
        print("Motor A: %.2f A  fault/limit: %s" % (a, FAULT.value() == 0))
        if a > 1.6:              # about 80% of the 2 A limit at 3.3 V logic
            print("Stall - stopping")
            break
        time.sleep(0.1)
    drive(A_EN, A_PH, 0)         # EN low = brake
    ```

=== "Raspberry Pi, gpiozero"

    ```python
    from gpiozero import PhaseEnableMotor, DigitalInputDevice
    from time import sleep

    motor_a = PhaseEnableMotor(phase=5, enable=12)   # J3 pins 4, 3
    motor_b = PhaseEnableMotor(phase=6, enable=13)   # J3 pins 6, 5
    motor_a.enable_device.frequency = 1000           # software PWM
    motor_b.enable_device.frequency = 1000
    fault = DigitalInputDevice(19, pull_up=None, active_state=False)  # J3 pin 10

    # gpiozero's forward() drives PH low, which is this board's reverse,
    # so backward() runs a motor forward here.
    motor_a.backward(0.5)   # forward (OUT1 positive, green LED)
    motor_b.forward(0.75)   # reverse (OUT2 positive, red LED)
    sleep(2)
    print("Fault or current limit:", fault.is_active)
    motor_a.stop()   # brake
    motor_b.stop()
    ```

    gpiozero uses software PWM, which is unreliable above about 1 kHz, so the motors may
    whine. For silent 20 kHz drive on a Pi, use the hardware PWM pins (GPIO12, GPIO13).
