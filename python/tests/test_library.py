import time

import pytest

from pingoblin_motor import (ADS1115, ConfigError, Direction, FaultAction, FaultMonitor, FaultPolicy, HalfBridgeMotor,
                             FaultType, MockBackend, MockCurrentSensor, MotorBoard, MotorChain,
                             MotorFaultError, MotorState)


class Clock:
    """Real monotonic time plus a manual offset, so motor start times line up."""

    def __init__(self):
        self.offset = 0.0

    def __call__(self):
        return time.monotonic() + self.offset

    def advance(self, s):
        self.offset += s


def make_board(name="b1", backend=None, sensors=False, mode="ph_en", **kw):
    backend = backend or MockBackend()
    sa = MockCurrentSensor() if sensors else None
    sb = MockCurrentSensor() if sensors else None
    kw.setdefault("motor_options", dict(reverse_delay=0))
    board = MotorBoard(name, a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                       mode=mode, backend=backend, a_sensor=sa, b_sensor=sb, sense_samples=1, **kw)
    return board, backend, sa, sb


def pins(backend):
    return backend.pins


# ---------------------------------------------------------------- basic control
def test_forward_reverse_ph_en():
    board, be, *_ = make_board()
    a = board.motor_a
    a.forward(50)
    assert pins(be)[5].value is True and pins(be)[12].duty == 0.5
    assert a.state is MotorState.RUNNING and a.direction is Direction.FORWARD
    a.reverse(75)
    assert pins(be)[5].value is False and pins(be)[12].duty == 0.75
    a.stop()
    assert pins(be)[12].duty == 0 and a.state is MotorState.STOPPED
    board.close()


def test_run_signed_and_invert():
    board, be, *_ = make_board(a_options=dict(invert=True))
    board.motor_a.run(-40)
    assert pins(be)[5].value is True           # inverted: reverse drives PH high
    assert board.motor_a.direction is Direction.REVERSE
    board.motor_a.run(0)
    assert board.motor_a.state is MotorState.STOPPED
    board.close()


def test_speed_validation_and_min_speed():
    board, be, *_ = make_board(a_options=dict(min_speed_pc=20))
    with pytest.raises(ValueError):
        board.motor_a.forward(120)
    board.motor_a.forward(5)
    assert pins(be)[12].duty == pytest.approx(0.20)
    board.close()


def test_speed_setter_and_start_resume():
    board, be, *_ = make_board()
    a = board.motor_a
    a.reverse(30)
    a.speed_pc = 60
    assert pins(be)[12].duty == pytest.approx(0.6)
    a.stop()
    a.start()
    assert a.direction is Direction.REVERSE and pins(be)[12].duty == pytest.approx(0.6)
    board.close()


def test_duration_stops_motor():
    board, be, *_ = make_board()
    a = board.motor_a
    t0 = time.monotonic()
    a.forward(80, duration=0.15, wait=True)
    assert time.monotonic() - t0 >= 0.14
    assert a.state is MotorState.STOPPED and pins(be)[12].duty == 0
    board.close()


def test_new_command_cancels_duration():
    board, be, *_ = make_board()
    a = board.motor_a
    a.forward(50, duration=0.1)
    a.forward(60)              # no duration: runs until told otherwise
    time.sleep(0.2)
    assert a.is_running
    board.close()


def test_ramp():
    board, be, *_ = make_board(a_options=dict(ramp_time=0.2))
    a = board.motor_a
    a.forward(100)
    time.sleep(0.05)
    assert 0 < pins(be)[12].duty < 1.0
    time.sleep(0.3)
    assert pins(be)[12].duty == pytest.approx(1.0)
    board.close()


def test_pwm_mode_slow_decay():
    board, be, *_ = make_board(mode="pwm")
    a = board.motor_a
    a.forward(30)             # IN1 = 1, IN2 = 1 - duty (OUT1 positive)
    assert pins(be)[12].duty == 1.0 and pins(be)[5].duty == pytest.approx(0.7)
    a.reverse(30)             # IN1 = 1 - duty, IN2 = 1 (OUT2 positive)
    assert pins(be)[12].duty == pytest.approx(0.7) and pins(be)[5].duty == 1.0
    a.stop()                  # brake = both high
    assert pins(be)[12].duty == 1.0 and pins(be)[5].duty == 1.0
    assert a.coast() is True  # coast = both low
    assert pins(be)[12].duty == 0 and pins(be)[5].duty == 0
    board.close()


def test_coast_ph_en_uses_sleep_only_when_other_motor_idle():
    board, be, *_ = make_board()
    a, b = board.motor_a, board.motor_b
    a.forward(50)
    b.forward(50)
    assert a.coast() is False          # b still running: brake instead
    assert a.state is MotorState.STOPPED and not board.is_asleep
    b.stop()
    a.forward(50)
    assert a.coast() is True
    assert board.is_asleep and a.state is MotorState.COASTING
    a.forward(40)                      # wakes the board automatically
    assert not board.is_asleep
    board.close()


def test_current_limit_from_logic_voltage():
    b33, *_ = make_board()
    b5, *_ = make_board(name="b5", logic_voltage=5.0)
    assert b33.current_limit == pytest.approx(1.956, abs=0.01)
    assert b5.current_limit == pytest.approx(2.963, abs=0.01)
    b33.close(); b5.close()


def test_config_errors():
    with pytest.raises(ConfigError):
        MotorBoard(a_en=12, a_ph=12, backend=MockBackend())
    with pytest.raises(ConfigError):
        MotorBoard(a_en=12, a_ph=5, mode="bogus", backend=MockBackend())
    with pytest.raises(ConfigError):
        MotorBoard("bad.name", a_en=12, a_ph=5, backend=MockBackend())


# ---------------------------------------------------------------- current
def test_current_reading_duty_corrected():
    board, be, sa, sb = make_board(sensors=True)
    a = board.motor_a
    assert board.motor_a.current == 0
    a.forward(50)
    sa.amps = 0.4                       # ISENSE average at 50 % duty
    assert a.current == pytest.approx(0.8)
    assert a.last_isense_amps == pytest.approx(0.4)
    board.close()


def test_no_sensor_current_is_none():
    board, *_ = make_board()
    assert board.motor_a.current is None
    board.close()


# ---------------------------------------------------------------- faults
def monitor_for(*boards, chain_limit=None):
    clk = Clock()
    return FaultMonitor(boards, chain_current_limit=chain_limit, clock=clk), clk


def test_stall_with_sensor_brakes_and_latches():
    board, be, sa, sb = make_board(sensors=True)
    mon, clk = monitor_for(board)
    a = board.motor_a
    a.forward(100)
    sa.amps = 1.9                       # above 80 % of the 1.96 A limit
    clk.advance(0.4)                    # past start_grace
    assert mon.check_once() == []
    clk.advance(0.6)                    # stall_time elapsed
    faults = mon.check_once()
    assert [f.type for f in faults] == [FaultType.STALL]
    assert a.state is MotorState.FAULT and pins(be)[12].duty == 0
    with pytest.raises(MotorFaultError):
        a.forward(50)
    a.clear_fault()
    a.forward(50)
    assert a.is_running
    board.close()


def test_stall_ignored_during_start_grace():
    board, be, sa, _ = make_board(sensors=True)
    mon, clk = monitor_for(board)
    board.motor_a.forward(100)
    sa.amps = 1.9
    mon.check_once()
    clk.advance(0.2)
    assert mon.check_once() == []       # still in the 0.3 s grace
    board.close()


def test_stall_without_sensor_from_nfault():
    board, be, *_ = make_board()
    mon, clk = monitor_for(board)
    board.motor_a.forward(100)
    pins(be)[19].level = False          # nFAULT low: current limiting
    clk.advance(0.4)
    types = [f.type for f in mon.check_once()]
    assert FaultType.CURRENT_LIMIT in types
    clk.advance(0.6)
    assert [f.type for f in mon.check_once()] == [FaultType.STALL]
    assert board.motor_a.state is MotorState.FAULT
    board.close()


def test_stall_without_sensor_both_running_stops_both():
    board, be, *_ = make_board()
    mon, clk = monitor_for(board)
    board.motor_a.forward(100)
    board.motor_b.forward(100)
    pins(be)[19].level = False
    clk.advance(0.4); mon.check_once()
    clk.advance(0.6)
    stalls = [f for f in mon.check_once() if f.type is FaultType.STALL]
    assert {f.motor for f in stalls} == {"a", "b"}
    assert "cannot tell which" in stalls[0].message
    board.close()


def test_driver_fault_sleeps_board():
    board, be, *_ = make_board()
    mon, clk = monitor_for(board)
    pins(be)[19].level = False          # nFAULT low with nothing running
    mon.check_once()
    clk.advance(0.25)
    faults = mon.check_once()
    assert faults[0].type is FaultType.DRIVER_FAULT
    assert board.is_asleep
    assert board.motor_a.state is MotorState.FAULT
    board.close()


def test_open_load():
    board, be, sa, _ = make_board(sensors=True)
    mon, clk = monitor_for(board)
    board.motor_a.forward(60)
    sa.amps = 0.0
    clk.advance(0.4); mon.check_once()
    clk.advance(1.1)
    assert [f.type for f in mon.check_once()] == [FaultType.OPEN_LOAD]
    board.close()


def test_overload():
    board, be, sa, _ = make_board(sensors=True, a_options=dict(continuous_current=1.0, overload_time=2.0))
    mon, clk = monitor_for(board)
    board.motor_a.forward(100)
    sa.amps = 1.3                       # below stall (1.56 A) but above 1.0 A rating
    clk.advance(0.4); mon.check_once()
    clk.advance(2.1)
    assert [f.type for f in mon.check_once()] == [FaultType.OVERLOAD]
    board.close()


def test_board_overload():
    board, be, sa, sb = make_board(sensors=True, logic_voltage=5.0,
                                   motor_options=dict(reverse_delay=0, continuous_current=3.0,
                                                      stall_current=5.0))
    mon, clk = monitor_for(board)
    board.motor_a.forward(100); board.motor_b.forward(100)
    sa.amps = sb.amps = 1.7             # 3.4 A total > 3 A fuse
    clk.advance(0.4); mon.check_once()
    clk.advance(1.1)
    assert {f.type for f in mon.check_once()} == {FaultType.BOARD_OVERLOAD}
    board.close()


def test_sensor_error_reported_once():
    board, be, sa, _ = make_board(sensors=True)
    mon, clk = monitor_for(board)
    sa.fail = True
    assert [f.type for f in mon.check_once()] == [FaultType.SENSOR_ERROR]
    assert mon.check_once() == []
    board.close()


def test_policy_override_and_handler():
    seen = []
    board, be, sa, _ = make_board(sensors=True,
                                  a_options=dict(policy=FaultPolicy({FaultType.STALL: FaultAction.NONE}, latch=False)))
    board.motor_a.add_fault_handler(seen.append)
    mon, clk = monitor_for(board)
    board.motor_a.forward(100)
    sa.amps = 1.9
    clk.advance(0.4); mon.check_once(); clk.advance(0.6); mon.check_once()
    assert seen and seen[0].type is FaultType.STALL
    assert board.motor_a.is_running     # policy NONE: keeps running
    board.close()


# ---------------------------------------------------------------- daisy chain
def test_chain_shared_pins_alias_and_estop():
    be = MockBackend()
    front, *_ = make_board("front", backend=be)
    rear = MotorBoard("rear", a_en=20, a_ph=21, b_en=22, b_ph=23, sleep_pin=26, fault_pin=19,
                      backend=be, motor_options=dict(reverse_delay=0))
    assert be._refs[26] == 2            # shared nSLEEP
    chain = MotorChain([front, rear], monitor=False)
    chain.alias("left", "front.a")
    chain["left"].forward(50)
    chain["rear.b"].reverse(30)
    assert chain.motor("rear.b").is_running
    chain.emergency_stop()
    assert all(not m.is_running for m in chain)
    assert front.is_asleep and rear.is_asleep
    with pytest.raises(KeyError):
        chain["nope.a"]
    chain.close()
    assert 26 not in be.pins


def test_chain_coast_blocked_by_motor_on_other_board_sharing_sleep():
    be = MockBackend()
    front, *_ = make_board("front", backend=be)
    rear = MotorBoard("rear", a_en=20, a_ph=21, sleep_pin=26, backend=be, motor_options=dict(reverse_delay=0))
    front.motor_a.forward(50)
    rear.motor_a.forward(50)
    assert front.motor_a.coast() is False   # rear shares nSLEEP and is running
    front.close(); rear.close()


def test_chain_overload():
    be = MockBackend()
    boards, sensors = [], []
    for i, base in enumerate((2, 7, 14)):
        sa, sb = MockCurrentSensor(), MockCurrentSensor()
        b = MotorBoard(f"b{i}", a_en=base, a_ph=base + 1, b_en=base + 2, b_ph=base + 3, backend=be,
                       a_sensor=sa, b_sensor=sb, sense_samples=1,
                       motor_options=dict(stall_current=5, continuous_current=5, reverse_delay=0))
        boards.append(b); sensors += [sa, sb]
    clk = Clock()
    chain = MotorChain(boards, monitor=False)
    chain._monitor.clock = clk
    for m in chain:
        m.forward(100)
    for s in sensors:
        s.amps = 1.2                    # 7.2 A total > 6 A; each board 2.4 A < 3 A
    clk.advance(0.4); chain.check_faults()
    clk.advance(1.1)
    assert {f.type for f in chain.check_faults()} == {FaultType.CHAIN_OVERLOAD}
    assert chain.total_current == pytest.approx(7.2)
    chain.close()


def test_monitor_thread_runs():
    board, be, sa, _ = make_board(sensors=True)
    got = []
    mon = board.start_monitor(interval=0.01, on_fault=got.append)
    sa.fail = True
    time.sleep(0.1)
    board.close()
    assert got and got[0].type is FaultType.SENSOR_ERROR


# ---------------------------------------------------------------- ADS1115
class FakeBus:
    def __init__(self, raw):
        self.raw, self.writes = raw, []

    def write_i2c_block_data(self, addr, reg, data):
        self.writes.append((addr, reg, data))

    def read_i2c_block_data(self, addr, reg, n):
        if reg == 0x01:
            return [0x80, 0x00]          # conversion done
        return [(self.raw >> 8) & 0xFF, self.raw & 0xFF]


def test_ads1115_config_and_conversion():
    bus = FakeBus(raw=16384)             # half of +4.096 V full scale
    adc = ADS1115(bus, address=0x49)
    assert adc.config_word(2) == 0xE3E3  # OS | AIN2 | 4.096 V | single | 860 SPS | comp off
    assert adc.read_voltage(2) == pytest.approx(2.048)
    assert bus.writes[0] == (0x49, 0x01, [0xE3, 0xE3])
    bus.raw = 0xFFFF                     # -1 LSB
    assert adc.read_voltage(0) < 0
    with pytest.raises(ConfigError):
        ADS1115(bus, address=0x50)


def test_driver_fault_without_sleep_pin_brakes():
    be = MockBackend()
    board = MotorBoard(a_en=12, a_ph=5, fault_pin=19, backend=be)
    mon, clk = monitor_for(board)
    be.pins[19].level = False
    mon.check_once(); clk.advance(0.25)
    assert mon.check_once()[0].type is FaultType.DRIVER_FAULT
    assert board.motor_a.state is MotorState.FAULT
    board.close()


# ---------------------------------------------------------------- four-motor mode
def make_four(backend=None, sensors=False, **kw):
    backend = backend or MockBackend()
    sa = MockCurrentSensor() if sensors else None
    sb = MockCurrentSensor() if sensors else None
    board = MotorBoard("q", a_en=12, a_ph=5, b_en=13, b_ph=6, sleep_pin=26, fault_pin=19,
                       mode="independent", backend=backend, a_sensor=sa, b_sensor=sb,
                       sense_samples=1, **kw)
    return board, backend, sa, sb


def test_four_motor_creates_four_half_bridge_motors_asleep_and_stopped():
    board, be, *_ = make_four()
    assert list(board.motors) == ["a1", "a2", "b1", "b2"]
    assert all(isinstance(m, HalfBridgeMotor) for m in board)
    assert board.is_asleep                       # stays asleep until the first run
    for pin in (12, 5, 13, 6):
        assert be.pins[pin].duty == 1.0          # input high = motor off
    assert board["a1"].terminal == "J4 A1 (OUT1)" and board["b2"].terminal == "J5 B2 (OUT2)"
    board.close()


def test_four_motor_drive_is_inverted_and_wakes_board():
    board, be, *_ = make_four()
    board["a1"].forward(30)
    assert not board.is_asleep
    assert be.pins[12].duty == pytest.approx(0.7)   # low 30 % of the time
    assert board["a1"].duty == pytest.approx(0.3)
    board["a2"].run(100)
    assert be.pins[5].duty == 0.0
    board["a1"].stop()
    assert be.pins[12].duty == 1.0 and board["a1"].state is MotorState.STOPPED
    assert be.pins[5].duty == 0.0                   # a2 unaffected
    board.close()


def test_four_motor_one_direction_only():
    board, *_ = make_four()
    with pytest.raises(ConfigError):
        board["b1"].reverse(50)
    with pytest.raises(ValueError):
        board["b1"].run(-20)
    with pytest.raises(ConfigError):
        board.motor_a
    with pytest.raises(ConfigError):
        board["a1"].read_current()
    board.close()


def test_four_motor_config_errors():
    with pytest.raises(ConfigError):
        MotorBoard(a_en=12, a_ph=5, mode="independent", backend=MockBackend())   # no sleep pin
    with pytest.raises(ConfigError):
        make_four(motor_names=("x", "y"))
    with pytest.raises(ConfigError):
        make_four(motor_options=dict(invert=True))


def test_four_motor_custom_names_and_single_driver():
    be = MockBackend()
    board = MotorBoard(a_en=12, a_ph=5, sleep_pin=26, mode="independent", backend=be,
                       motor_names=("pump", "fan", "x", "y"))
    assert list(board.motors) == ["pump", "fan"]
    board["fan"].forward(50)
    assert be.pins[5].duty == 0.5
    board.close()


def test_four_motor_close_sleeps_before_release():
    board, be, *_ = make_four()
    board["b2"].forward(80)
    sleep_pin = be.pins[26]
    board.close()
    assert sleep_pin.value is False


def test_four_motor_coast_only_when_others_idle():
    board, be, *_ = make_four()
    board["a1"].forward(50)
    board["a2"].forward(50)
    assert board["a1"].coast() is False            # a2 still running: brake
    assert be.pins[12].duty == 1.0
    board["a2"].stop()
    assert board["a2"].coast() is True and board.is_asleep
    board.close()


def test_four_motor_driver_current_and_board_overload():
    clock = Clock()
    board, be, sa, sb = make_four(sensors=True)
    mon = FaultMonitor([board], clock=clock)
    board["a1"].forward(100)
    board["b1"].forward(100)
    sa.amps, sb.amps = 1.0, 0.5
    assert board.driver_current("a") == pytest.approx(1.0)
    with pytest.raises(ConfigError):
        board.driver_current("c")
    mon.check_once()
    assert board.total_current == pytest.approx(1.5)
    sa.amps, sb.amps = 2.5, 1.0
    mon.check_once()
    clock.advance(1.1)
    found = mon.check_once()
    assert any(f.type is FaultType.BOARD_OVERLOAD for f in found)
    board.close()


def test_four_motor_nfault_is_driver_fault_while_running():
    clock = Clock()
    board, be, *_ = make_four()
    mon = FaultMonitor([board], clock=clock)
    board["a1"].forward(60)
    be.pins[19].level = False                      # nFAULT low while driven
    mon.check_once()
    clock.advance(0.3)
    found = mon.check_once()
    types = {f.type for f in found}
    assert FaultType.DRIVER_FAULT in types
    assert FaultType.STALL not in types and FaultType.CURRENT_LIMIT not in types
    assert board["a1"].state is MotorState.FAULT
    board.close()
