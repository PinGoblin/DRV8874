"""pingoblin_motor - control library for the PinGoblin Board A dual DC motor driver.

Quick start (Raspberry Pi)::

    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19)
    board.start_monitor()
    board.motor_a.forward(60, duration=2, wait=True)
    board.close()
"""
from .backends import Backend, GpiozeroBackend, MockBackend
from .board import MotorBoard
from .chain import MotorChain
from .faults import (ConfigError, Fault, FaultAction, FaultPolicy, FaultType, MotorError,
                     MotorFaultError, SensorError)
from .monitor import FaultMonitor
from .motor import ControlMode, Direction, Motor, MotorState
from .sensors import ADS1115, ADS1115Channel, MockCurrentSensor, MotorCurrentSensor

__version__ = "0.1.0"

__all__ = [
    "ADS1115", "ADS1115Channel", "Backend", "ConfigError", "ControlMode", "Direction", "Fault",
    "FaultAction", "FaultMonitor", "FaultPolicy", "FaultType", "GpiozeroBackend", "MockBackend",
    "MockCurrentSensor", "Motor", "MotorBoard", "MotorChain", "MotorCurrentSensor", "MotorError",
    "MotorFaultError", "MotorState", "SensorError",
]
