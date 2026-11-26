# Daisy-chaining boards

Several boards can share one motor supply and one host.

## Power

- Connect one power source to the first board (J1 or J2), then wire J2 of each board to
  J2 of the next. Only one power source for the whole chain: see
  [Powering the board](power.md).
- J1 and J2 are wired in parallel, so every board's terminals carry the current of all the
  boards after it. **Keep the total current through any board's terminals at or below
  6 A.** For more boards, run a separate supply lead (a star) to each group.
- Each board still has its own 4 A fuse.

## Logic

- Each board needs its own EN and PH pins (J3 pins 3–6), and its **own nFAULT pin**
  (pin 10, see below).
- nSLEEP (pin 9) can be shared: wire it to every board and connect it to one GPIO. That
  gives one emergency-stop line that stops every board at once. One 3.3 V GPIO can drive
  nSLEEP for up to four boards (about 0.35 mA per board).
- Connect GND (pin 1) and VLOGIC (pin 2) on every board.
- One PinGoblin ADS1115 board reads the ISENSE outputs of two boards. Up to four ADS1115
  boards share one I2C bus.

!!! warning "Give every board its own nFAULT line"
    Never wire the nFAULT pins of two boards together. Each board's fault LED and pull-up
    load its nFAULT line with up to about 3.5 mA, and the driver that pulls the line low is
    rated for 5 mA. A shared line would also hide which board has the fault, so the library
    would have to stop every motor on every board. The library raises an error if two boards
    are given the same `fault_pin`.

In software, manage the boards as one [`MotorChain`](../api/guide/daisy-chain.md).
