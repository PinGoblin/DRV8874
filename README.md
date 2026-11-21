# PinGoblin Board A – DRV8874 dual DC motor driver

A breakout board that drives two brushed DC motors from a Raspberry Pi, ESP32 or other 3.3 V / 5 V microcontroller. It uses two TI DRV8874 H-bridges, runs from a 6–16 V motor supply, and includes current sensing, protection and test buttons.

## Contents

| Folder | What it is |
|---|---|
| [`python/`](python/) | `pingoblin_motor`: Python library for the Raspberry Pi. Controls one board or several daisy-chained boards, with optional current sensing through a PinGoblin ADS1115 board and detection of stalls and other faults |

## Quick start (Python)

```bash
cd python
pip install ".[pi]"
```

```python
from pingoblin_motor import MotorBoard

board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
board.start_monitor()
board.motor_a.forward(60, duration=2, wait=True)
board.close()
```

See [`python/README.md`](python/README.md) for the full API, fault handling and daisy-chain examples.

## Licence

MIT. See [LICENSE](LICENSE).
