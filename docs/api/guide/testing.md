# Testing without hardware

Both versions include mock pins and a mock current sensor, so you can develop and test on
any computer.

=== "Raspberry Pi package"

    ```python
    from pingoblin_motor import MockBackend, MockCurrentSensor, MotorBoard

    sensor = MockCurrentSensor()
    board = MotorBoard(a_en=12, a_ph=5, backend=MockBackend(), a_sensor=sensor)
    board.motor_a.forward(50)
    sensor.amps = 1.9          # simulate a stall
    ```

=== "MicroPython module"

    ```python
    from pingoblin_motor import MockPins, MockSensor, MotorBoard

    board = MotorBoard(a_en=1, a_ph=2, pins=MockPins(), a_sensor=MockSensor())
    ```

    The MicroPython file also runs under CPython, which is how its tests run.

## Running the test suites

```bash
cd python && python -m pytest                 # Raspberry Pi package
cd micropython && python -m pytest tests      # MicroPython module, under CPython
```

CI also runs a smoke test under the MicroPython Unix port, checks that the file
precompiles with `mpy-cross`, and builds this documentation with `mkdocs build --strict`.
