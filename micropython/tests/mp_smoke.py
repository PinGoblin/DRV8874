"""Smoke test that runs under real MicroPython (the Unix port in CI).

Plain asserts only: no pytest. Run from the micropython folder:

    micropython tests/mp_smoke.py
"""
import sys

sys.path.insert(0, ".")
import pingoblin_motor as pm  # noqa: E402

pins = pm.MockPins()
sa, sb = pm.MockSensor(), pm.MockSensor()
board = pm.MotorBoard("b1", a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                      pins=pins, a_sensor=sa, b_sensor=sb, sense_samples=1,
                      motor_options=dict(reverse_delay=0))
board.enable_monitor()
a, b = board.motor_a, board.motor_b

# Basic drive
a.forward(60)
assert a.is_running and a.direction == pm.Direction.FORWARD, a
assert abs(pins.pins[12].duty - 0.6) < 0.01
a.reverse(30)
assert a.direction == pm.Direction.REVERSE and pins.pins[5].value == 1
a.stop()
assert a.state == pm.MotorState.STOPPED

# Timed run on the real clock
b.forward(50, duration=0.1, wait=True)
assert not b.is_running, b

# Stall from the current sensor
a.forward(80)
sa.amps = 1.9
board.pause(1.2)
assert a.fault is not None and a.fault.type == pm.FaultType.STALL, a.fault
try:
    a.forward(10)
    raise AssertionError("latched fault should block the motor")
except pm.MotorFaultError:
    pass
sa.amps = 0
a.clear_fault()
a.forward(10)
assert a.is_running

# asyncio monitor
try:
    import asyncio
except ImportError:
    asyncio = None
if asyncio:
    async def main():
        t = asyncio.create_task(board.run_monitor())
        b.forward(40, duration=0.1)
        while b.busy:
            await asyncio.sleep(0.02)
        t.cancel()
    asyncio.run(main())
    assert not b.is_running

board.close()
print("mp_smoke: OK")
