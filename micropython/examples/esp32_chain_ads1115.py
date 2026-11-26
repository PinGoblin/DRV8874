# ESP32: two daisy-chained boards with current sensing on one PinGoblin ADS1115 board.
# ADS1115 at 0x48: AIN0/1 = front A/B ISENSE, AIN2/3 = rear A/B ISENSE.
# nSLEEP (GPIO32) is shared by both boards. Each board has its own nFAULT line:
# front = GPIO39, rear = GPIO36 (both input-only pins).
from machine import I2C, Pin
from pingoblin_motor import ADS1115, FaultType, MotorBoard, MotorChain

adc = ADS1115(I2C(0, sda=Pin(21), scl=Pin(22), freq=400000), address=0x48)
front = MotorBoard("front", a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39,
                   adc=adc, a_sense_channel=0, b_sense_channel=1)
rear = MotorBoard("rear", a_en=16, a_ph=17, b_en=18, b_ph=19, sleep_pin=32, fault_pin=36,
                  adc=adc, a_sense_channel=2, b_sense_channel=3)
chain = MotorChain([front, rear])


def on_fault(f):
    print("FAULT:", f)
    if f.type in (FaultType.CHAIN_OVERLOAD, FaultType.DRIVER_FAULT):
        chain.emergency_stop()


chain.add_fault_handler(on_fault)
for m in chain:
    m.forward(70)
for _ in range(10):
    chain.pause(0.2)
    print(", ".join("%s=%.2f A" % (m.full_name, m.last_current or 0) for m in chain),
          "| total %.2f A" % (chain.total_current or 0))
chain.stop_all()
