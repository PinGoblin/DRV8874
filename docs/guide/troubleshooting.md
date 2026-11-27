# Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Power LED off | No supply, supply reversed, or fuse blown | Check the battery is switched on and charged, or that the supply's positive lead goes to J2 pin 1 (VIN+). If a wired supply was reversed, fix the wiring (reverse polarity does not blow the fuse). A blown fuse (F1) means a supply above 30 V or an internal fault. F1 is not user-serviceable: Return the board for repair |
| Power LED on, buttons do nothing | nSLEEP held low by the host | Disconnect nSLEEP (pin 9) or drive it high |
| Buttons work, host code does nothing, fault LED never lights | VLOGIC missing | Connect J3 pin 2 to the host's 3.3 V pin (5 V only on a 5 V host) and GND to pin 1 |
| Buttons work, host code does nothing | Wrong GPIO numbers, no common GND, or EN never goes high | Check the pin mapping and the GND link. Measure EN (pin 3/5) while the code runs |
| Buttons do nothing but host code works | JP1 bridged (PWM mode) | The buttons run motors only in PH/EN mode (JP1 open). In PWM mode FWD brakes and REV runs forward |
| A fault on one board stops motors on every board, or the library says the `fault_pin` is already used | Boards share an nFAULT line | Give each board its own nFAULT GPIO: See [Daisy-chaining boards](daisy-chain.md) |
| Motor runs only one direction | PH not connected or not changing | Check pin 4/6 wiring. With PH open, the motor always runs in reverse (PH has a pull-down) |
| Motor turns the wrong way | Motor wires swapped | Swap the wires at J4/J5, or set the library's `invert=True` option |
| Motor is weak or slow under heavy load | Current limit active (load at 4.6 A) | Reduce the load or speed. A larger motor needs a larger driver |
| Fault LED on, or library reports `DRIVER_FAULT` | Output short, driver overheated, or motor supply below 4.5 V (flat battery) | Check the motor wiring, let the board cool, or charge the battery. The motor runs again on the next command once the cause has gone |
| Motor starts, stops and restarts repeatedly on a battery | Battery voltage falls below about 4.5 V when the motor starts, so the drivers reset | Charge or replace the battery, use a higher-voltage battery, or set `ramp_time` for a soft start |
| Motor stalls but no `STALL` is reported | Stall detection needs a current sensor | Fit a current sensor and set `stall_current`, or stop the motor with a time-out. See [Choosing a motor](choosing-a-motor.md#stall-detection) |
| Large motor is slow, weak or reports `STALL` under load | Motor needs more than the 4.6 A current limit | Use a motor with a lower stall current. See [Choosing a motor](choosing-a-motor.md) |
| Motor runs, then stops and restarts every few seconds | Driver overheating | Improve airflow and reduce continuous current. Keep each motor under 2.5 A and the total under 5 A |
| Motor whines | PWM frequency in the audible range (the Raspberry Pi library defaults to 1 kHz) | Use 20 kHz PWM: On a Pi, enable [hardware PWM](../api/guide/concepts.md#pwm-frequency) |
| ISENSE always reads 0 | Motor not driven when sampled, or PWM off-time sampled | Read while the motor is driven. Average several samples |
| Host resets when motors start | Supply sag or ground bounce through shared wiring | Power the host separately, run separate GND wires from the supply to the board and to the host, and add bulk capacitance at the supply |
| Library raises `MotorFaultError` | A fault stopped the motor. The message says what to check | Fix the cause and run the motor again. See [Faults](../api/guide/faults.md) |
| Library reports `STALL` on every start | Start-up surge longer than `start_grace` | Raise `start_grace` or `stall_time`, or add `ramp_time` for a soft start |
