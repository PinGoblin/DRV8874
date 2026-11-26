"""`pingoblin_motor`: control library for the PinGoblin Board A dual DC motor driver (2 × DRV8874) on a Raspberry Pi.

The main classes are importable from the package:

| Class | Purpose |
|---|---|
| [`MotorBoard`][pingoblin_motor.board.MotorBoard] | One board: two motors (four in four-motor mode) plus its nSLEEP / nFAULT lines |
| [`Motor`][pingoblin_motor.motor.Motor] | One motor channel |
| [`HalfBridgeMotor`][pingoblin_motor.motor.HalfBridgeMotor] | One unidirectional motor in four-motor mode |
| [`MotorChain`][pingoblin_motor.chain.MotorChain] | Several daisy-chained boards |
| [`ADS1115`][pingoblin_motor.sensors.ADS1115] | Current sensing through a PinGoblin ADS1115 board |
| [`FaultMonitor`][pingoblin_motor.monitor.FaultMonitor] | Background fault detection |

Example:
    ```python
    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
    board.start_monitor()
    board.motor_a.forward(60, duration=2, wait=True)
    board.close()
    ```
"""
from .backends import Backend, GpiozeroBackend, MockBackend
from .board import MotorBoard
from .chain import MotorChain
from .faults import (ConfigError, Fault, FaultAction, FaultPolicy, FaultType, MotorError,
                     MotorFaultError, SensorError)
from .monitor import FaultMonitor
from .motor import ControlMode, Direction, HalfBridgeMotor, Motor, MotorState
from .sensors import ADS1115, ADS1115Channel, MockCurrentSensor, MotorCurrentSensor

__version__ = "0.1.0"

__all__ = [
    "ADS1115", "ADS1115Channel", "Backend", "ConfigError", "ControlMode", "Direction", "Fault",
    "FaultAction", "FaultMonitor", "FaultPolicy", "FaultType", "GpiozeroBackend", "HalfBridgeMotor",
    "MockBackend",
    "MockCurrentSensor", "Motor", "MotorBoard", "MotorChain", "MotorCurrentSensor", "MotorError",
    "MotorFaultError", "MotorState", "SensorError",
]
