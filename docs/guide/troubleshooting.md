# Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Power LED off | No supply, supply reversed, or fuse tripped | Check the battery is switched on and charged, or that VIN+ goes to J2 pin 1. If a wired supply was reversed, fix the wiring. A tripped fuse resets about a minute after power is removed |
| Power LED on, motors do nothing, buttons do nothing | VLOGIC missing, or nSLEEP not driven high (the board pulls it low) | Feed 3.3–5 V to J3 pin 2 and connect GND (pin 1). Drive nSLEEP (pin 9) high from the host (pass `sleep_pin=` to the library), or link pin 9 to pin 2 for button tests |
| Buttons work, host code does nothing | Wrong GPIO numbers, no common GND, or EN never goes high | Check the pin mapping and the GND link. Measure EN (pin 3/5) while the code runs |
| Buttons do nothing but host code works | PMODE jumper set to PWM or four-motor mode | Buttons run motors only in PH/EN mode (JP1 pads 1–2) |
| Motors run as soon as power is applied, or keep running after the program stops | JP1 open (four-motor mode) with nSLEEP held high: linked to VLOGIC, or a GPIO left high | Wire nSLEEP to a GPIO that your program drives low when it stops. See [Four-motor mode](four-motor-mode.md). If you didn't mean to use four-motor mode, bridge JP1 pads 1–2 |
| A fault on one board stops motors on every board, or the library says the `fault_pin` is already used | Boards share an nFAULT line | Give each board its own nFAULT GPIO: see [Daisy-chaining boards](daisy-chain.md) |
| Four-motor mode: a motor runs when it should be off, and the reverse | Motor control inverted by hand-written code | The motor runs while its input is low. Drive the input at 1 − speed, or use the library's `mode="independent"` |
| Motor runs only one direction | PH not connected or not changing | Check pin 4/6 wiring. With PH open, the motor always runs in reverse (PH has a pull-down) |
| Motor turns the wrong way | Motor wires swapped | Swap the wires at J4/J5, or set the library's `invert=True` option |
| Motor stutters, fault LED flickers | Current limit active (load near 2 A at 3.3 V logic, 3 A at 5 V) | Reduce load or speed. A larger motor needs 5 V logic or a bigger driver |
| Motor runs, then stops and restarts every few seconds | Driver overheating, or the board fuse tripping | Improve airflow and reduce continuous current. Keep the total under 3 A |
| Motor whines | PWM frequency in the audible range | Use 20 kHz PWM |
| ISENSE always reads 0 | Motor not driven when sampled, or PWM off-time sampled | Read while EN is high. Average several samples |
| Host resets when motors start | Supply sag or ground bounce through shared wiring | Power the host separately, run separate GND wires from the supply to the board and to the host, and add bulk capacitance at the supply |
| Library raises `MotorFaultError` | A latched fault (stall, overload, open load, driver fault) | Fix the cause, then call `motor.clear_fault()`. See [Faults](../api/guide/faults.md) |
| Library reports `STALL` on every start | Start-up surge longer than `start_grace` | Raise `start_grace` or `stall_time`, or add `ramp_time` for a soft start |
