# Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Power LED off | No supply, supply reversed, or fuse blown | Check the battery is switched on and charged, or that the supply's positive lead goes to J2 pin 1 (VIN+). If a wired supply was reversed, fix the wiring (reverse polarity does not blow the fuse). A blown fuse (F1) is not resettable: it means a supply above 30 V or an internal fault, and F1 must be replaced |
| Power LED on, motors do nothing, buttons do nothing | VLOGIC missing, or nSLEEP held low | Feed 3.3–5 V to J3 pin 2 and connect GND (pin 1). Disconnect nSLEEP (pin 9) or drive it high |
| Buttons work, host code does nothing | Wrong GPIO numbers, no common GND, or EN never goes high | Check the pin mapping and the GND link. Measure EN (pin 3/5) while the code runs |
| Buttons do nothing but host code works | JP1 bridged (PWM mode) | The buttons run motors only in PH/EN mode (JP1 open). In PWM mode FWD brakes and REV runs forward |
| A fault on one board stops motors on every board, or the library says the `fault_pin` is already used | Boards share an nFAULT line | Give each board its own nFAULT GPIO: see [Daisy-chaining boards](daisy-chain.md) |
| Motor runs only one direction | PH not connected or not changing | Check pin 4/6 wiring. With PH open, the motor always runs in reverse (PH has a pull-down) |
| Motor turns the wrong way | Motor wires swapped | Swap the wires at J4/J5, or set the library's `invert=True` option |
| Motor stutters, fault LED flickers | Current limit active (load near 3 A) | Reduce the load or speed. A larger motor needs a larger driver |
| Motor stops at 100% duty and the fault LED stays on | Current limit reached at 100% duty, which has no PWM edge to restart it | Change the speed or stop and restart. Run at 99% if stalls are likely: see [100% duty and the current limit](controlling-motors.md#practical-limits) |
| Motor runs, then stops and restarts every few seconds | Driver overheating | Improve airflow and reduce continuous current. Keep the total under 3 A |
| Motor whines | PWM frequency in the audible range (the Raspberry Pi library defaults to 1 kHz) | Use 20 kHz PWM: on a Pi, enable [hardware PWM](../api/guide/concepts.md#pwm-frequency) |
| ISENSE always reads 0 | Motor not driven when sampled, or PWM off-time sampled | Read while the motor is driven. Average several samples |
| Host resets when motors start | Supply sag or ground bounce through shared wiring | Power the host separately, run separate GND wires from the supply to the board and to the host, and add bulk capacitance at the supply |
| Library raises `MotorFaultError` | A latched fault (stall, overload, open load, driver fault) | Fix the cause, then call `motor.clear_fault()`. See [Faults](../api/guide/faults.md) |
| Library reports `STALL` on every start | Start-up surge longer than `start_grace` | Raise `start_grace` or `stall_time`, or add `ramp_time` for a soft start |
