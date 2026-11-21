# PinGoblin Board A – DRV8874 dual DC motor driver

A breakout board that drives two brushed DC motors from a Raspberry Pi, ESP32 or other 3.3 V / 5 V microcontroller. It uses two TI DRV8874 H-bridges, runs from a 6–16 V motor supply, and includes current sensing, protection and test buttons.

**Documentation: <https://pingoblin.github.io/DRV8874/>**

The documentation site is the source of truth for the board and the libraries: the User Guide (specifications, safety, wiring, J3 pinout, current sensing, troubleshooting) and the API reference. It is built from [`docs/`](docs/) and the code's docstrings, and published by CI on every push to `main`.

## Contents

| Folder | What it is |
|---|---|
| [`python/`](python/) | `pingoblin_motor`: Python library for the Raspberry Pi. Controls one board or several daisy-chained boards, with optional current sensing through a PinGoblin ADS1115 board and detection of stalls and other faults |
| [`docs/`](docs/) | MkDocs source for the documentation site (`mkdocs.yml` in the repo root) |
| [`micropython/`](micropython/) | The same library as a single MicroPython file for ESP32 and Raspberry Pi Pico. Install with `mpremote mip install github:PinGoblin/DRV8874/micropython` |

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

See the [documentation](https://pingoblin.github.io/DRV8874/) for the full API, fault handling and daisy-chain examples.

## Building the docs locally

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

## Licence

MIT. See [LICENSE](LICENSE).
