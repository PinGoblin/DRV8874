# Raspberry Pi Pico: home an actuator against its end stop using stall detection,
# with the fault monitor running as an asyncio task. No limit switch needed.
# Without a current sensor, a stall is detected from nFAULT (the driver current-limiting).
import asyncio
from pingoblin_motor import FaultAction, FaultPolicy, FaultType, MotorBoard

policy = FaultPolicy({FaultType.STALL: FaultAction.BRAKE}, latch=False)   # stall is expected here
board = MotorBoard(a_en=2, a_ph=3, fault_pin=7,
                   a_options=dict(policy=policy, stall_time=0.3))
stalled = asyncio.Event()
board.motor_a.add_fault_handler(lambda f: f.type == FaultType.STALL and stalled.set())
board.enable_monitor(interval=0.02)


async def main():
    asyncio.create_task(board.run_monitor())
    print("homing...")
    board.motor_a.reverse(30)
    try:
        await asyncio.wait_for(stalled.wait(), 10)
        print("end stop reached: position = 0")
    except asyncio.TimeoutError:
        board.motor_a.stop()
        print("no end stop found within 10 s")

asyncio.run(main())
