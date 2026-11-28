# Installation

## Raspberry Pi

The package needs Python 3.8 or later and gpiozero. Install it from the repository:

```bash
git clone https://github.com/PinGoblin/DRV8874.git
cd DRV8874/python
pip install ".[pi]"              # gpiozero
pip install ".[ads1115]"         # optional: current sensing through a PinGoblin ADS1115 board
pip install rpi-hardware-pwm     # optional: silent 20 kHz hardware PWM
```

The `ads1115` option installs the ADS1115 board's own library,
[`pingoblin_ads1115`](https://pingoblin.github.io/ADS1115/), from its repository. Enable
I2C with `sudo raspi-config` (Interface Options → I2C) if you use an ADS1115 board.

Pin numbers are BCM GPIO numbers.

## MicroPython (ESP32, Pico)

Needs MicroPython 1.20 or later.

From GitHub with mip (on a Wi-Fi board, or through `mpremote`):

```bash
mpremote mip install github:PinGoblin/DRV8874/micropython
```

Or copy the file:

```bash
mpremote cp micropython/pingoblin_motor.py :
```

For current sensing through a PinGoblin ADS1115 board, also install its `ads1115` module:

```bash
mpremote mip install github:PinGoblin/ADS1115/micropython
```

!!! tip "Precompile on ESP32"
    The source is about 63 KB, much of it docstrings, and compiling it on the board can
    run out of RAM on an ESP32 without PSRAM. Precompile it and copy the `.mpy` instead.
    `.mpy` files leave the docstrings out.

    ```bash
    pip install mpy-cross
    mpy-cross micropython/pingoblin_motor.py      # makes pingoblin_motor.mpy
    mpremote cp micropython/pingoblin_motor.mpy :
    ```

    Use an `mpy-cross` version that matches the board's MicroPython version.
