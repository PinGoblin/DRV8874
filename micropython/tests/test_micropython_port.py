"""Off-target tests for the MicroPython port (run with CPython + pytest).

The library falls back to time.monotonic() when time.ticks_ms() is missing,
and _advance_clock() moves that clock forward, so time-based behaviour
(timed runs, ramps, fault debouncing) is tested without waiting.
"""
import ast
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "pingoblin_motor.py")
sys.path.insert(0, os.path.join(HERE, ".."))

import pingoblin_motor as pm  # noqa: E402
from pingoblin_motor import (ADS1115, ConfigError, Direction, FaultAction, FaultMonitor,  # noqa: E402
                             FaultPolicy, FaultType, MockPins, MockSensor, MotorBoard, MotorChain,
                             MotorFaultError, MotorState)


def adv(ms):
    pm._advance_clock(ms)


def make_board(name="b1", pins=None, sensors=False, mode="ph_en", **kw):
    pins = pins or MockPins()
    sa = MockSensor() if sensors else None
    sb = MockSensor() if sensors else None
    kw.setdefault("motor_options", dict(reverse_delay=0))
    b = MotorBoard(name, a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19, mode=mode,
                   pins=pins, a_sensor=sa, b_sensor=sb, sense_samples=1, **kw)
    return b, pins, sa, sb


def P(pins):
    return pins.pins


# ------------------------------------------------------------- MicroPython compatibility
ALLOWED_IMPORTS = {"time", "asyncio", "uasyncio", "machine"}


def test_source_uses_only_micropython_features():
    tree = ast.parse(open(SRC).read())
    shim = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "ticks_ms"]
    shim_lines = set()
    for f in shim:
        shim_lines.update(range(f.lineno, f.end_lineno + 1))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            problems += [a.name for a in node.names if a.name not in ALLOWED_IMPORTS]
        elif isinstance(node, ast.ImportFrom):
            problems.append("from-import %s" % node.module)
        elif isinstance(node, ast.JoinedStr):
            problems.append("f-string at line %d" % node.lineno)
        elif isinstance(node, ast.AnnAssign) or (isinstance(node, ast.arg) and node.annotation):
            problems.append("annotation at line %d" % node.lineno)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            problems.append("return annotation at line %d" % node.lineno)
        elif isinstance(node, ast.Dict) and None in node.keys:
            problems.append("dict unpacking at line %d" % node.lineno)
        elif isinstance(node, ast.Raise) and node.cause is not None:
            problems.append("raise-from at line %d" % node.lineno)
        elif isinstance(node, ast.NamedExpr):
            problems.append("walrus at line %d" % node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr in ("partition", "rpartition", "monotonic"):
            if node.attr != "monotonic" or node.lineno not in shim_lines:   # only in the CPython shim
                problems.append("%s at line %d" % (node.attr, node.lineno))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "__init__" and isinstance(node.func.value, ast.Name)):
            # MicroPython built-in exception types have no __init__ attribute; use super().
            problems.append("%s.__init__() at line %d" % (node.func.value.id, node.lineno))
    assert problems == []


# ------------------------------------------------------------- control
def test_forward_reverse_stop():
    b, pins, *_ = make_board()
    a = b.motor_a
    a.forward(50)
    assert P(pins)[5].value is True and P(pins)[12].duty == 0.5
    assert a.state == MotorState.RUNNING and a.direction == Direction.FORWARD
    a.reverse(75)
    assert P(pins)[5].value is False and P(pins)[12].duty == 0.75
    a.stop()
    assert P(pins)[12].duty == 0 and a.state == MotorState.STOPPED
    b.close()


def test_default_pwm_frequency_is_20k():
    b, pins, *_ = make_board()
    assert P(pins)[12].freq == 20000
    b.close()


def test_run_signed_invert_and_min_speed():
    b, pins, *_ = make_board(a_options=dict(invert=True, min_speed_pc=20, reverse_delay=0))
    b.motor_a.run(-10)
    assert P(pins)[5].value is True and P(pins)[12].duty == pytest.approx(0.2)
    with pytest.raises(ValueError):
        b.motor_a.forward(101)
    b.close()


def test_speed_setter_and_start():
    b, pins, *_ = make_board()
    a = b.motor_a
    a.reverse(30)
    a.speed_pc = 60
    assert P(pins)[12].duty == pytest.approx(0.6)
    a.stop()
    a.start()
    assert a.direction == Direction.REVERSE and P(pins)[12].duty == pytest.approx(0.6)
    b.close()


def test_timed_run_stops_in_update():
    b, pins, *_ = make_board()
    a = b.motor_a
    a.forward(80, duration=2)
    adv(1500); b.update()
    assert a.is_running
    adv(600); b.update()
    assert a.state == MotorState.STOPPED and P(pins)[12].duty == 0
    b.close()


def test_timed_run_wait_blocks():
    b, pins, *_ = make_board()
    b.motor_a.forward(50, duration=0.1, wait=True)
    assert b.motor_a.state == MotorState.STOPPED
    b.close()


def test_ramp_progresses_in_update():
    b, pins, *_ = make_board(a_options=dict(ramp_time=1.0, reverse_delay=0))
    a = b.motor_a
    a.forward(100)
    assert P(pins)[12].duty == 0
    adv(500); b.update()
    assert 0.4 < P(pins)[12].duty < 0.6
    adv(600); b.update()
    assert P(pins)[12].duty == 1.0 and not a.busy
    b.close()


def test_pwm_mode_slow_decay_and_coast():
    b, pins, *_ = make_board(mode="pwm")
    a = b.motor_a
    a.forward(30)
    assert P(pins)[12].duty == 1.0 and P(pins)[5].duty == pytest.approx(0.7)
    a.reverse(30)
    assert P(pins)[12].duty == pytest.approx(0.7) and P(pins)[5].duty == 1.0
    assert a.coast() is True and P(pins)[12].duty == 0 and P(pins)[5].duty == 0
    b.close()


def test_coast_ph_en_needs_other_motor_idle():
    b, pins, *_ = make_board()
    b.motor_a.forward(50); b.motor_b.forward(50)
    assert b.motor_a.coast() is False and not b.is_asleep
    b.motor_b.stop(); b.motor_a.forward(50)
    assert b.motor_a.coast() is True and b.is_asleep
    b.motor_a.forward(40)
    assert not b.is_asleep
    b.close()


def test_current_limit_and_config_errors():
    b, *_ = make_board(logic_voltage=5.0)
    assert b.current_limit == pytest.approx(2.963, abs=0.01)
    b.close()
    with pytest.raises(ConfigError):
        MotorBoard(a_en=1, a_ph=1, pins=MockPins())
    with pytest.raises(ConfigError):
        MotorBoard(a_en=1, a_ph=2, mode="x", pins=MockPins())


def test_current_duty_corrected():
    b, pins, sa, _ = make_board(sensors=True)
    b.motor_a.forward(50)
    sa.amps = 0.4
    assert b.motor_a.current == pytest.approx(0.8)
    b.close()


# ------------------------------------------------------------- faults
def mon(*boards, limit=None):
    return FaultMonitor(boards, chain_current_limit=limit)


def test_stall_with_sensor_latches():
    b, pins, sa, _ = make_board(sensors=True)
    m = mon(b)
    b.motor_a.forward(100)
    sa.amps = 1.9
    adv(400); m.check_once()
    adv(600)
    assert [f.type for f in m.check_once()] == [FaultType.STALL]
    assert b.motor_a.state == MotorState.FAULT
    with pytest.raises(MotorFaultError):
        b.motor_a.forward(10)
    b.motor_a.clear_fault()
    b.motor_a.forward(10)
    b.close()


def test_stall_from_nfault_without_sensor():
    b, pins, *_ = make_board()
    m = mon(b)
    b.motor_a.forward(100)
    P(pins)[19].level = False
    adv(400)
    assert FaultType.CURRENT_LIMIT in [f.type for f in m.check_once()]
    adv(600)
    assert [f.type for f in m.check_once()] == [FaultType.STALL]
    b.close()


def test_driver_fault_sleeps_board():
    b, pins, *_ = make_board()
    m = mon(b)
    P(pins)[19].level = False
    m.check_once(); adv(250)
    assert m.check_once()[0].type == FaultType.DRIVER_FAULT
    assert b.is_asleep and b.motor_a.state == MotorState.FAULT
    b.close()


def test_open_load_and_overload():
    b, pins, sa, sb = make_board(sensors=True, b_options=dict(continuous_current=1.0, overload_time=2,
                                                              reverse_delay=0))
    m = mon(b)
    b.motor_a.forward(60); b.motor_b.forward(100)
    sa.amps, sb.amps = 0.0, 1.3
    adv(400); m.check_once()
    adv(1100)
    assert [f.type for f in m.check_once()] == [FaultType.OPEN_LOAD]
    adv(1000)
    assert [f.type for f in m.check_once()] == [FaultType.OVERLOAD]
    b.close()


def test_sensor_error_once_and_policy():
    seen = []
    pol = FaultPolicy({FaultType.STALL: FaultAction.NONE}, latch=False)
    b, pins, sa, _ = make_board(sensors=True, a_options=dict(policy=pol, reverse_delay=0))
    b.motor_a.add_fault_handler(seen.append)
    m = mon(b)
    sa.fail = True
    assert [f.type for f in m.check_once()] == [FaultType.SENSOR_ERROR]
    assert m.check_once() == []
    sa.fail = False
    b.motor_a.forward(100); sa.amps = 1.9
    adv(400); m.check_once(); adv(600); m.check_once()
    assert seen[-1].type == FaultType.STALL and b.motor_a.is_running
    b.close()


def test_board_update_runs_monitor_at_interval():
    b, pins, sa, _ = make_board(sensors=True)
    got = []
    b.enable_monitor(interval=0.05, on_fault=got.append)
    sa.fail = True
    b.update()
    assert got and got[0].type == FaultType.SENSOR_ERROR
    b.close()


# ------------------------------------------------------------- chain
def test_chain_aliases_shared_pins_estop_and_overload():
    pins = MockPins()
    sensors = []
    boards = []
    for i, base in enumerate((2, 7, 14)):
        sa, sb = MockSensor(), MockSensor()
        sensors += [sa, sb]
        boards.append(MotorBoard("b%d" % i, a_en=base, a_ph=base + 1, b_en=base + 2, b_ph=base + 3,
                                 sleep_pin=26, fault_pin=19, pins=pins, a_sensor=sa, b_sensor=sb,
                                 sense_samples=1,
                                 motor_options=dict(stall_current=5, continuous_current=5, reverse_delay=0)))
    assert pins._refs[26] == 3
    chain = MotorChain(boards)
    chain.alias("left", "b0.a")
    for mo in chain:
        mo.forward(100)
    for s in sensors:
        s.amps = 1.2                      # 7.2 A total > 6 A chain limit
    adv(400); chain.check_faults()
    adv(1100)
    assert {f.type for f in chain.check_faults()} == {FaultType.CHAIN_OVERLOAD}
    chain.clear_faults()
    chain["left"].forward(20)
    chain.emergency_stop()
    assert all(not mo.is_running for mo in chain) and boards[0].is_asleep
    with pytest.raises(KeyError):
        chain["nope"]
    chain.close()
    assert 26 not in pins.pins


def test_chain_motor_wait_uses_chain_update():
    pins = MockPins()
    b, *_ = make_board("solo", pins=pins)
    chain = MotorChain([b])
    b.motor_a.forward(50, duration=0.05, wait=True)
    assert b.motor_a.state == MotorState.STOPPED
    chain.close()


# ------------------------------------------------------------- ADS1115
class FakeI2C:
    def __init__(self, raw):
        self.raw = raw
        self.writes = []

    def writeto_mem(self, addr, reg, data):
        self.writes.append((addr, reg, bytes(data)))

    def readfrom_mem(self, addr, reg, n):
        if reg == 1:
            return bytes([0x80, 0])
        return bytes([(self.raw >> 8) & 0xFF, self.raw & 0xFF])


def test_ads1115():
    i2c = FakeI2C(16384)
    adc = ADS1115(i2c, address=0x49)
    assert adc.config_word(2) == 0xE3E3
    assert adc.read_voltage(2) == pytest.approx(2.048)
    assert i2c.writes[0] == (0x49, 1, bytes([0xE3, 0xE3]))
    with pytest.raises(ConfigError):
        ADS1115(i2c, address=0x40)


def test_asyncio_run_monitor_task():
    import asyncio
    b, pins, sa, _ = make_board(sensors=True)
    got = []
    b.enable_monitor(interval=0.01, on_fault=got.append)

    async def main():
        task = asyncio.create_task(b.run_monitor(interval=0.005))
        b.motor_a.forward(60, duration=0.05)
        sa.fail = True
        await asyncio.sleep(0.12)
        task.cancel()

    asyncio.run(main())
    assert b.motor_a.state == MotorState.STOPPED          # timed stop handled by the task
    assert got and got[0].type == FaultType.SENSOR_ERROR
    b.close()


# ------------------------------------------------------------- four-motor mode
def make_four(pins=None, sensors=False, **kw):
    pins = pins or MockPins()
    sa = MockSensor() if sensors else None
    sb = MockSensor() if sensors else None
    b = MotorBoard("q", a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                   mode="independent", pins=pins, a_sensor=sa, b_sensor=sb, sense_samples=1, **kw)
    return b, pins, sa, sb


def test_four_motor_setup_asleep_and_stopped():
    b, pins, *_ = make_four()
    assert list(b.motors) == ["a1", "a2", "b1", "b2"]
    assert all(isinstance(m, pm.HalfBridgeMotor) for m in b)
    assert b.is_asleep
    assert all(P(pins)[p].duty == 1.0 for p in (12, 5, 13, 6))
    assert b["a2"].terminal == "J4 A2 (OUT2)"
    b.close()


def test_four_motor_inverted_drive():
    b, pins, *_ = make_four()
    b["b1"].forward(25)
    assert not b.is_asleep and P(pins)[13].duty == pytest.approx(0.75)
    b["b1"].stop()
    assert P(pins)[13].duty == 1.0
    with pytest.raises(ConfigError):
        b["b1"].reverse(10)
    with pytest.raises(ValueError):
        b["b1"].run(-10)
    with pytest.raises(ConfigError):
        b.motor_a
    b.close()


def test_four_motor_needs_sleep_pin_and_four_names():
    with pytest.raises(ConfigError):
        MotorBoard(a_en=12, a_ph=5, mode="independent", pins=MockPins())
    with pytest.raises(ConfigError):
        make_four(motor_names=("x", "y"))
    with pytest.raises(ConfigError):
        make_four(motor_options=dict(invert=True))


def test_four_motor_close_sleeps():
    b, pins, *_ = make_four()
    b["a1"].forward(50)
    s = P(pins)[26]
    b.close()
    assert s.value is False


def test_four_motor_timed_run():
    b, pins, *_ = make_four()
    b["a2"].forward(60, duration=1)
    adv(1100)
    b.update()
    assert b["a2"].state == MotorState.STOPPED and P(pins)[5].duty == 1.0
    b.close()


def test_four_motor_nfault_and_overload():
    b, pins, sa, sb = make_four(sensors=True)
    m = mon(b)
    b["a1"].forward(100)
    sa.amps, sb.amps = 2.5, 1.0
    assert b.driver_current("a") == pytest.approx(2.5, abs=0.01)
    m.check_once(); adv(1100)
    assert FaultType.BOARD_OVERLOAD in [f.type for f in m.check_once()]
    b["a1"].clear_fault()
    sa.amps = sb.amps = 0.0
    b["a1"].forward(50)
    P(pins)[19].level = False
    m.check_once(); adv(250)
    types = [f.type for f in m.check_once()]
    assert FaultType.DRIVER_FAULT in types and FaultType.STALL not in types
    assert FaultType.CURRENT_LIMIT not in types
    b.close()
