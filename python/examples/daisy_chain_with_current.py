"""Two daisy-chained boards, one PinGoblin ADS1115 board for current sensing.

Shared lines: nSLEEP (GPIO26) and nFAULT (GPIO19) are wired to both boards.
ADS1115 (address 0x48): AIN0 = front A_ISENSE, AIN1 = front B_ISENSE,
AIN2 = rear A_ISENSE, AIN3 = rear B_ISENSE.

Run with --mock to try it without hardware (each motor reads about 0.5 A).
"""
import sys
import time

from pingoblin_motor import (ADS1115, FaultType, MockBackend, MockCurrentSensor, MotorBoard,
                             MotorChain)

mock = "--mock" in sys.argv
backend = MockBackend() if mock else None


def sensing(channel_a, channel_b):
    if mock:
        return dict(a_sensor=MockCurrentSensor(0.35), b_sensor=MockCurrentSensor(0.35))
    return dict(adc=ADC, a_sense_channel=channel_a, b_sense_channel=channel_b)


ADC = None if mock else ADS1115(bus=1, address=0x48)

front = MotorBoard("front", a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                   backend=backend, **sensing(0, 1))
rear = MotorBoard("rear", a_en=16, a_ph=20, b_en=21, b_ph=7, sleep_pin=26, fault_pin=19,
                  backend=backend, **sensing(2, 3))


def on_fault(fault):
    print("FAULT:", fault)
    if fault.type in (FaultType.CHAIN_OVERLOAD, FaultType.DRIVER_FAULT):
        chain.emergency_stop()


with MotorChain([front, rear]) as chain:
    chain.add_fault_handler(on_fault)
    for alias, target in (("fl", "front.a"), ("fr", "front.b"), ("rl", "rear.a"), ("rr", "rear.b")):
        chain.alias(alias, target)

    for m in chain:
        m.forward(70)
    for _ in range(10):
        time.sleep(0.2)
        readings = ", ".join(f"{m.full_name}={m.last_current or 0:.2f} A" for m in chain)
        print(readings, f"| chain total {chain.total_current or 0:.2f} A")

    chain["fl"].reverse(40, duration=1, wait=True)
    chain.stop_all()
    print("fault history:", [str(f) for f in chain.faults])
