# Controlling the motors

!!! info "Terms used on this page"
    - **PWM (pulse-width modulation):** The host switches a pin on and off rapidly, many
      thousands of times a second. The **duty cycle** is the percentage of each cycle the pin
      is on, and it sets the average power, and so the speed, of the motor.
    - **PH (phase):** The direction input. High runs the motor forward, low runs it in
      reverse.
    - **EN (enable):** The drive input. High drives the motor, low brakes it. Feeding it PWM
      sets the speed.
    - **IN1 / IN2 (input 1 / input 2):** In PWM mode, the same two pins become two direct
      inputs, each controlling one side of the motor (OUT1 and OUT2).
    - **nSLEEP / nFAULT:** The leading *n* means the signal is active when low: nSLEEP low
      puts the drivers to sleep, and nFAULT goes low on a fault or current limiting.

    The [Glossary](glossary.md) lists every abbreviation used in this manual.

The board has two control modes, selected with the [PMODE jumper JP1](configuration.md):
PH/EN mode (the default) and PWM mode.

The tables on this page are for motor A. Motor B is identical, using B_EN and B_PH (J3
pins 5 and 6).

## PH/EN mode (default)

JP1 open (as supplied). Each motor uses two pins: **EN** (enable) turns the
motor on and sets its speed with PWM, and **PH** (phase) sets the direction. One PWM
channel per motor is enough. This is the same scheme as gpiozero's `PhaseEnableMotor`,
except that gpiozero calls PH low "forward" (see [Direction](#direction)).

| nSLEEP | A_EN (pin 3) | A_PH (pin 4) | OUT1 | OUT2 | Motor | LED |
| --- | --- | --- | --- | --- | --- | --- |
| High (default) | Low | Any | Low | Low | Brake (stops quickly) | Off |
| High | High / PWM | High | High | Low | Forward | Green |
| High | High / PWM | Low | Low | High | Reverse | Red |
| Low | Any | Any | Open | Open | Coast (sleep, near-zero current) | Off |

**Speed:** Drive EN with PWM. The duty cycle sets the speed. During the PWM off-time the
motor brakes, which gives a firm, close-to-linear response. The library's `speed_pc`
(0–100) is the EN duty cycle.

**Coast:** In PH/EN mode a motor can only coast by putting the drivers to sleep, and
nSLEEP is shared by both motors. The library's `coast()` therefore sleeps the board only
when the other motor is idle, and otherwise brakes.

**Test buttons:** FWD runs the motor forward and REV runs it in reverse, at full speed
while held. See [Test buttons and LEDs](buttons-leds.md).

## PWM mode (IN1/IN2)

JP1 bridged. Each pin drives one side of the motor directly, as on two-input
drivers such as the L298N and DRV8833. PWM mode lets each motor coast on its own, without
sleeping the board, but needs PWM on both pins for full control.

| nSLEEP | A_EN = IN1 (pin 3) | A_PH = IN2 (pin 4) | OUT1 | OUT2 | Motor | LED |
| --- | --- | --- | --- | --- | --- | --- |
| High (default) | Low | Low | Open | Open | Coast | Off |
| High | High | Low | High | Low | Forward | Green |
| High | Low | High | Low | High | Reverse | Red |
| High | High | High | Low | Low | Brake | Off |
| Low | Any | Any | Open | Open | Coast (sleep, near-zero current) | Off |

**Speed:** Hold one input high and switch the other (slow decay), or hold one input low
and switch the other (fast decay). See [Speed control](#speed-control) below. In
`mode="pwm"` the library uses slow decay, so the response matches PH/EN mode.

**Other libraries:** PWM mode suits code written for two-input drivers (gpiozero `Motor`,
Arduino `analogWrite()` on either pin). With gpiozero's `Motor` class, pass `forward=`
J3 pin 3 (IN1) and `backward=` J3 pin 4 (IN2), so its directions match the table above.

**Test buttons:** Not supported in PWM mode. FWD drives IN1 and IN2 high, which brakes
the motor, and REV drives IN1 only, which runs it forward. See
[Buttons in PWM mode](buttons-leds.md#buttons-in-pwm-mode-jp1-bridged).

## Speed control

In every mode, speed comes from the **PWM duty cycle**: The fraction of each PWM period
for which the motor is connected to the supply. A motor driven at 60% duty sees, on
average, about 60% of VM, so it runs at roughly 60% of its full speed at that load. The
modes differ in which pin is switched, and in what the motor does during the off-time.

| Mode | Forward at speed *d* | Reverse at speed *d* | Off-time | Response |
| --- | --- | --- | --- | --- |
| PH/EN (default) | PH high, EN PWM at duty *d* | PH low, EN PWM at duty *d* | Brake | Firm, close to linear |
| PWM, slow decay (used by the library) | IN1 high, IN2 PWM at duty 1 − *d* | IN2 high, IN1 PWM at duty 1 − *d* | Brake | The same as PH/EN |
| PWM, fast decay | IN1 PWM at duty *d*, IN2 low | IN2 PWM at duty *d*, IN1 low | Coast | Softer; speed falls away at low duty |

**PH/EN mode.** During the off-time both low-side switches are on (brake, also called slow
decay), so the motor's current keeps circulating and the speed follows the duty cycle
closely, even at light load. PH/EN mode is the simplest to use and gives the best
low-speed control.

**PWM mode, slow decay.** One input is held high and the other is switched. The motor is
driven while the switched input is *low*, so the duty is inverted: For 30% speed forward,
hold IN1 high and run IN2 at 70%. The off-time is a brake, so the response matches PH/EN
mode.

**PWM mode, fast decay.** One input is held low and the other is switched at the speed
duty. This is how most two-input motor libraries work, including gpiozero's `Motor` class
and Arduino code that calls `analogWrite()` on one pin. During the off-time both outputs
turn off and the motor coasts, while its current flows back into the supply. Torque is
lower and the response is less linear at low duty: A lightly loaded motor may slow very
little until the duty is well below 50%. Slow decay gives finer control.

### Practical limits

- **Minimum speed.** Most small motors do not start turning until the duty cycle reaches
  about 10–30%, because of friction and gearbox losses. Below that they hum without
  turning. The library's `min_speed_pc` raises any non-zero speed to this value.
- **PWM frequency.** Use 20 kHz where the host supports it: It is above human hearing and
  gives smooth current. Lower frequencies (1–5 kHz, such as the Raspberry Pi's software
  PWM) work the same way but make the motor whine.
- **Full speed.** 100% duty applies the full supply to the motor. The test buttons drive
  EN high, so they always run at 100%.

!!! warning "100% duty and the current limit"
    The drivers limit current on every PWM cycle and restart on the next PWM edge. At
    exactly 100% duty there are no edges, so if a motor stalls and reaches the current
    limit, the driver holds it in brake (and lights the fault LED) until the input
    changes. To recover, change the speed, stop and restart, or release and press the test
    button again. If a stall is likely at full speed, run at 99% instead: The motor runs
    at effectively full speed, and the current limit then recovers automatically.

## Direction

"Forward" and "reverse" follow TI's convention for the DRV8874: Forward is OUT1 positive
(green LED). In PH/EN mode that is PH high; in PWM mode, IN1 high and IN2 low. Which way
the shaft turns depends on how the motor is wired: Swap its two leads, or use
`invert=True` in the library, to change it.

To protect gearboxes, slow down or stop briefly before reversing a heavily loaded motor.
The library brakes for `reverse_delay` (0.1 s by default) before reversing a running
motor.

## Sleep, emergency stop and start-up

**Sleep / emergency stop:** Pull nSLEEP low to put both drivers to sleep (outputs open,
motors coast). Wake-up takes about 1 ms. nSLEEP has a 10 kΩ pull-up to VLOGIC on the
board, so the drivers are awake whenever VLOGIC is present and nSLEEP is not driven low.
Connecting nSLEEP is optional.

**Start-up behaviour:** EN and PH have 10 kΩ pull-downs, so while the host is booting,
and after your program exits, both motors are held in brake in PH/EN mode. In PWM mode
the same pull-downs make the motors coast.

## Driving the pins directly

The [library](../api/index.md) is the recommended way to use the board. The protocol can
also be driven directly, as below (PH/EN mode). Speed runs from −1.0 (full reverse) to 1.0
(full forward).

=== "ESP32, MicroPython"

    ```python
    from machine import Pin, PWM, ADC
    import time

    SLEEP = Pin(32, Pin.OUT, value=1)             # J3 pin 9: high = drivers awake
    A_EN = PWM(Pin(25), freq=20000, duty_u16=0)   # J3 pin 3
    A_PH = Pin(26, Pin.OUT, value=0)              # J3 pin 4
    A_SENSE = ADC(Pin(34)); A_SENSE.atten(ADC.ATTN_11DB)  # J3 pin 7
    FAULT = Pin(39, Pin.IN)                       # J3 pin 10 (pulled up on board)

    def drive(en, ph, speed):
        """speed -1.0..1.0; positive = forward (PH high, OUT1 positive)."""
        ph.value(1 if speed > 0 else 0)
        en.duty_u16(int(min(abs(speed), 1.0) * 65535))

    def amps(adc):
        return adc.read_uv() / 1_000_000 / 0.45    # 0.45 V per amp

    drive(A_EN, A_PH, 0.6)
    for _ in range(30):
        a = amps(A_SENSE)
        print("Motor A: %.2f A  fault/limit: %s" % (a, FAULT.value() == 0))
        if a > 3.7:              # about 80% of the 4.6 A current limit
            print("Stall - stopping")
            break
        time.sleep(0.1)
    drive(A_EN, A_PH, 0)         # EN low = brake
    ```

=== "Raspberry Pi, gpiozero"

    ```python
    from gpiozero import PhaseEnableMotor, DigitalInputDevice, DigitalOutputDevice
    from time import sleep

    wake = DigitalOutputDevice(26, initial_value=True)   # J3 pin 9: high = drivers awake
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
