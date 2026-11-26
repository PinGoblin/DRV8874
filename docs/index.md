---
hide:
  - navigation
---

# PinGoblin Dual DC Motor Board

Board A drives two brushed DC motors in both directions from a Raspberry Pi, ESP32,
Raspberry Pi Pico or any other 3.3 V or 5 V microcontroller. It uses two TI DRV8874
H-bridges, runs from a 6–30 V motor supply, and adds current sensing, protection and
test buttons.

This site is the reference for the board and its software. It has two parts:

<div class="grid cards" markdown>

-   **[User Guide](guide/index.md)**

    ---

    Setting up and using the board: specifications, safety, wiring, the J3 pinout,
    current sensing, the PMODE jumper and troubleshooting.

-   **[API](api/index.md)**

    ---

    The `pingoblin_motor` library for the Raspberry Pi, and the single-file version for
    MicroPython (ESP32 and Pico): stall and fault detection, current sensing and
    daisy-chained boards.

</div>

## Ten-second example

=== "Raspberry Pi"

    ```python
    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
    board.start_monitor()                              # stall and fault detection
    board.motor_a.forward(60, duration=2, wait=True)   # 60 % for 2 s, then brake
    board.close()
    ```

=== "MicroPython (ESP32)"

    ```python
    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39)
    board.enable_monitor(on_fault=print)
    board.motor_a.forward(60, duration=2, wait=True)
    ```

The source, hardware notes and issue tracker are on
[GitHub](https://github.com/PinGoblin/DRV8874). Everything is released under the MIT licence.
