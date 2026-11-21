# Daisy-chaining boards

Several boards can share one motor supply and one host.

## Power

- Feed the supply into J1 of the first board and take it on from J2 (VIN THRU) to J1 of
  the next.
- J1 and J2 are wired in parallel, so every board's terminals carry the current of all the
  boards after it. **Keep the total current through any board's terminals at or below
  6 A.** For more boards, run a separate supply lead (a star) to each group.
- Each board still has its own 3 A fuse.

## Logic

- Each board needs its own EN and PH pins (J3 pins 3–6).
- nSLEEP (pin 9) and nFAULT (pin 10) can be shared: wire them together across boards and
  connect them to one GPIO each. That gives one emergency-stop line and one fault line.
  nFAULT is open-drain, so any board can pull the shared line low.
- Connect GND (pin 1) and VLOGIC (pin 2) on every board.
- One PinGoblin ADS1115 board reads the ISENSE outputs of two boards. Up to four ADS1115
  boards share one I2C bus.

In software, manage the boards as one [`MotorChain`](../api/guide/daisy-chain.md).
