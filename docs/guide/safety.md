# Important safety information

Read these before connecting power.

!!! danger "Never connect VIN (6–18 V) to J3"
    J3 is logic only. VIN on any J3 pin will destroy the host and the drivers.

- **Do not exceed 18 V on VIN, including supply tolerance.** A supply labelled 18 V can
  measure higher: check it with a meter, or use a lower voltage. The surge suppressor
  starts conducting at about 20 V and is not meant to carry continuous current.
- **Connect GND between the board and the host.** J3 pin 1 must go to a host GND pin.
- **Wire with the power off.** Connect and disconnect motors only while the supply is off.
- **The drivers get hot.** At high currents the chips and the board around them can exceed
  60 °C. Allow airflow and do not touch them while running.
- **Daisy-chaining:** the VIN through-terminal (J2) shares one supply between boards. Keep
  the total current through a board's terminals at or below 6 A.
- **Use a fused or current-limited supply.** The on-board fuse protects the board, not your
  wiring or batteries.
