# Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Power LED off | No supply, supply reversed, or fuse tripped | Check the battery is switched on and charged, or that the supply's positive lead goes to J2 pin 1 (VIN+). If a wired supply was reversed, fix the wiring. A tripped fuse resets about a minute after power is removed |
| Power LED on, motors do nothing, buttons do nothing | VLOGIC missing, or nSLEEP not driven high (the board pulls it low) | Feed 3.3–5 V to J3 pin 2 and connect GND (pin 1). Drive nSLEEP (pin 9) high from the host (pass `sleep_pin=` to the library), or link pin 9 to pin 2 for button tests |
| Buttons work (with pin 9 linked to pin 2), host code does nothing | Wrong GPIO numbers, no common GND, nSLEEP not driven high, or EN never goes high | Check the pin mapping and the GND link. Pass `sleep_pin=` to the library. Measure nSLEEP (pin 9) and EN (pin 3/5) while the code runs |
| Buttons do nothing but host code works | JP1 set to PWM or four-motor mode | The buttons run motors only in PH/EN mode (JP1 pads 1–2). In PWM mode FWD brakes and REV runs forward; in four-motor mode the buttons only turn motors off |
| Board works without a host, but not once the host is connected | The nSLEEP GPIO is low, or is connected to VLOGIC as well | Remove the link between pins 9 and 2 when the host is connected, and drive nSLEEP high from the host |
| Motors run as soon as power is applied, or keep running after the program stops | JP1 open (four-motor mode) with nSLEEP held high: connected to VLOGIC, or a GPIO left high | Wire nSLEEP to a GPIO only, and drive it low when the program stops (the library does this in `close()`). See [Four-motor mode](four-motor-mode.md). If four-motor mode was not intended, bridge JP1 pads 1–2 |
| Direction LEDs glow or flicker while motors run in four-motor mode | Normal: the LEDs show the difference between a pair of outputs | Ignore the direction LEDs in four-motor mode |
| A fault on one board stops motors on every board, or the library says the `fault_pin` is already used | Boards share an nFAULT line | Give each board its own nFAULT GPIO: see [Daisy-chaining boards](daisy-chain.md) |
| Four-motor mode: a motor runs when it should be off, and the reverse | Motor control inverted by hand-written code | The motor runs while its input is low. Drive the input at 1 − speed, or use the library's `mode="independent"` |
| Motor runs only one direction | PH not connected or not changing | Check pin 4/6 wiring. With PH open, the motor always runs in reverse (PH has a pull-down) |
| Motor turns the wrong way | Motor wires swapped | Swap the wires at J4/J5, or set the library's `invert=True` option |
| Motor stutters, fault LED flickers | Current limit active (load near 2 A at 3.3 V logic, 3 A at 5 V) | Reduce the load or speed. A larger motor needs 5 V logic or a larger driver |
| Motor stops at 100% duty and the fault LED stays on | Current limit reached at 100% duty, which has no PWM edge to restart it | Change the speed or stop and restart. Run at 99% if stalls are likely: see [100% duty and the current limit](controlling-motors.md#practical-limits) |
| Motor runs, then stops and restarts every few seconds | Driver overheating, or the board fuse tripping | Improve airflow and reduce continuous current. Keep the total under 3 A |
| Motor whines | PWM frequency in the audible range (the Raspberry Pi library defaults to 1 kHz) | Use 20 kHz PWM: on a Pi, enable [hardware PWM](../api/guide/concepts.md#pwm-frequency) |
| ISENSE always reads 0 | Motor not driven when sampled, or PWM off-time sampled | Read while the motor is driven. Average several samples |
| ISENSE reads above VLOGIC in four-motor mode | Two motors on one driver drawing more than about 4.9 A in total (for example, both stalled) | Stop the motors. Use motors with a lower stall current, or read ISENSE through an ADS1115 board |
| Host resets when motors start | Supply sag or ground bounce through shared wiring | Power the host separately, run separate GND wires from the supply to the board and to the host, and add bulk capacitance at the supply |
| Library raises `MotorFaultError` | A latched fault (stall, overload, open load, driver fault) | Fix the cause, then call `motor.clear_fault()`. See [Faults](../api/guide/faults.md) |
| Library reports `STALL` on every start | Start-up surge longer than `start_grace` | Raise `start_grace` or `stall_time`, or add `ramp_time` for a soft start |
