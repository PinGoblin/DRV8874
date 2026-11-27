# Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Power LED off | No supply, supply reversed, or fuse blown | Check the battery is switched on and charged, or that the supply's positive lead goes to J2 pin 1 (VIN+). If a wired supply was reversed, fix the wiring (reverse polarity does not blow the fuse). A blown fuse (F1) is not resettable: It means a supply above 30 V or an internal fault, and F1 must be replaced. A supply above 30 V also destroys the surge suppressor D2, which must be replaced with F1 |
| Power LED on, motors do nothing, buttons do nothing | VLOGIC missing, or nSLEEP held low | Feed 3.3–5 V to J3 pin 2 and connect GND (pin 1). Disconnect nSLEEP (pin 9) or drive it high |
| Buttons work, host code does nothing | Wrong GPIO numbers, no common GND, or EN never goes high | Check the pin mapping and the GND link. Measure EN (pin 3/5) while the code runs |
| Buttons do nothing but host code works | JP1 bridged (PWM mode) | The buttons run motors only in PH/EN mode (JP1 open). In PWM mode FWD brakes and REV runs forward |
| A fault on one board stops motors on every board, or the library says the `fault_pin` is already used | Boards share an nFAULT line | Give each board its own nFAULT GPIO: See [Daisy-chaining boards](daisy-chain.md) |
| Motor runs only one direction | PH not connected or not changing | Check pin 4/6 wiring. With PH open, the motor always runs in reverse (PH has a pull-down) |
| Motor turns the wrong way | Motor wires swapped | Swap the wires at J4/J5, or set the library's `invert=True` option |
| Motor stutters, fault LED flickers | Current limit active (load near 4.6 A) | Reduce the load or speed. A larger motor needs a larger driver |
| Motor stops at 100% duty and the fault LED stays on | Current limit reached at 100% duty, which has no PWM edge to restart it | Change the speed or stop and restart. Run at 99% if stalls are likely: See [100% duty and the current limit](controlling-motors.md#practical-limits) |
| Fault LED on, or library reports `DRIVER_FAULT`, while no motor is running | Motor supply off, low or disconnected while VLOGIC is present. Below about 4.5 V the drivers shut down and pull nFAULT low | Check the motor supply, battery charge and fuse. After the supply returns, call `clear_fault()` |
| Motor starts, stops and restarts repeatedly on a battery | Battery voltage falls below about 4.5 V when the motor starts, so the drivers reset | Charge or replace the battery, use a higher-voltage battery, or set `ramp_time` for a soft start |
| Small motor stalls and gets hot, but no `STALL` is reported | Stall current below the 4.6 A current limit, so nFAULT never goes low | Fit a current sensor and set `stall_current`, or stop the motor with a time-out. See [Choosing a motor](choosing-a-motor.md#stall-detection-for-small-motors) |
| Large motor is slow, weak or reports `STALL` under load | Motor needs more than the 4.6 A current limit | Use a motor with a lower stall current. See [Choosing a motor](choosing-a-motor.md) |
| Motor runs, then stops and restarts every few seconds | Driver overheating | Improve airflow and reduce continuous current. Keep each motor under 2.5 A and the total under 5 A |
| Motor whines | PWM frequency in the audible range (the Raspberry Pi library defaults to 1 kHz) | Use 20 kHz PWM: On a Pi, enable [hardware PWM](../api/guide/concepts.md#pwm-frequency) |
| ISENSE always reads 0 | Motor not driven when sampled, or PWM off-time sampled | Read while the motor is driven. Average several samples |
| Host resets when motors start | Supply sag or ground bounce through shared wiring | Power the host separately, run separate GND wires from the supply to the board and to the host, and add bulk capacitance at the supply |
| Library raises `MotorFaultError` | A latched fault (stall, overload, open load, driver fault) | Fix the cause, then call `motor.clear_fault()`. See [Faults](../api/guide/faults.md) |
| Library reports `STALL` on every start | Start-up surge longer than `start_grace` | Raise `start_grace` or `stall_time`, or add `ramp_time` for a soft start |
