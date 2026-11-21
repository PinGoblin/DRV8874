# Installation

## Raspberry Pi

The package needs Python 3.8+ and gpiozero. It is not on PyPI yet, so install it from
the repository:

```bash
git clone https://github.com/PinGoblin/DRV8874.git
cd DRV8874/python
pip install ".[pi]"              # gpiozero and smbus2
pip install rpi-hardware-pwm     # optional: silent 20 kHz hardware PWM
```

`smbus2` is only needed for current sensing through a PinGoblin ADS1115 board. Enable I2C
with `sudo raspi-config` (Interface Options → I2C) if you use one.

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
