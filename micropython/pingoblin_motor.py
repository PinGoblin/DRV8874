# pingoblin_motor for MicroPython - PinGoblin Board A (2 x DRV8874) motor library
# MIT licence. Copy this one file to the board (or precompile with mpy-cross).
#
# Works on ESP32 and Raspberry Pi Pico (RP2040/RP2350) with MicroPython 1.20+.
# The same names as the Raspberry Pi library: MotorBoard, Motor, MotorChain,
# forward(), reverse(), run(), start(), stop()/brake(), coast(), speed_pc, current.
#
# No threads. Timed runs, ramps and fault checks happen in update(). Call it in
# one of three ways:
#   * run the monitor as an asyncio task:  asyncio.create_task(board.run_monitor())
#   * use the blocking helpers:            board.pause(2)  /  motor.forward(50, 2, wait=True)
#   * call board.update() from your own main loop every 10-50 ms
import time

try:
    import asyncio
except ImportError:  # older MicroPython
    try:
        import uasyncio as asyncio
    except ImportError:
        asyncio = None

__version__ = "0.1.0"

# ---------------------------------------------------------------- timing
_clock_offset = [0]   # test hook (CPython only)

if hasattr(time, "ticks_ms"):
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    sleep_ms = time.sleep_ms
else:  # CPython: lets the test suite run off-target
    def ticks_ms():
        return int(time.monotonic() * 1000) + _clock_offset[0]

    def ticks_diff(a, b):
        return a - b

    def sleep_ms(ms):
        time.sleep(ms / 1000)


def _advance_clock(ms):
    """Test hook: move the CPython clock forward."""
    _clock_offset[0] += int(ms)


ISENSE_V_PER_A = 0.675     # 1.5 kOhm x 450 uA/A (DRV8874 IPROPI)
WAKE_MS = 2                # DRV8874 wake-up from sleep is about 1 ms

# ---------------------------------------------------------------- constants


class Direction:
    FORWARD = "forward"
    REVERSE = "reverse"


class MotorState:
    STOPPED = "stopped"     # braked
    COASTING = "coasting"
    RUNNING = "running"
    FAULT = "fault"         # latched fault; call clear_fault()


class ControlMode:
    PH_EN = "ph_en"         # JP1 pads 1-2 (default): EN = speed PWM, PH = direction
    PWM = "pwm"             # JP1 pads 2-3: IN1 / IN2


class FaultType:
    STALL = "stall"
    CURRENT_LIMIT = "current_limit"
    DRIVER_FAULT = "driver_fault"
    OPEN_LOAD = "open_load"
    OVERLOAD = "overload"
    BOARD_OVERLOAD = "board_overload"
    CHAIN_OVERLOAD = "chain_overload"
    SENSOR_ERROR = "sensor_error"


class FaultAction:
    NONE = "none"
    BRAKE = "brake"
    COAST = "coast"
    SLEEP = "sleep"


DEFAULT_ACTIONS = {
    FaultType.STALL: FaultAction.BRAKE,
    FaultType.CURRENT_LIMIT: FaultAction.NONE,
    FaultType.DRIVER_FAULT: FaultAction.SLEEP,
    FaultType.OPEN_LOAD: FaultAction.BRAKE,
    FaultType.OVERLOAD: FaultAction.BRAKE,
    FaultType.BOARD_OVERLOAD: FaultAction.BRAKE,
    FaultType.CHAIN_OVERLOAD: FaultAction.BRAKE,
    FaultType.SENSOR_ERROR: FaultAction.NONE,
}
LATCHING = (FaultType.STALL, FaultType.DRIVER_FAULT, FaultType.OPEN_LOAD, FaultType.OVERLOAD)

# ---------------------------------------------------------------- faults and errors


class MotorError(Exception):
    pass


class ConfigError(MotorError):
    pass


class SensorError(MotorError):
    pass


class MotorFaultError(MotorError):
    def __init__(self, fault):
        MotorError.__init__(self, "motor has a latched fault: %s. Call clear_fault() first." % fault)
        self.fault = fault


class Fault:
    """One detected fault. ``timestamp`` is in ticks_ms."""

    def __init__(self, type, message, board=None, motor=None, value=None, timestamp=None):
        self.type = type
        self.message = message
        self.board = board
        self.motor = motor
        self.value = value
        self.timestamp = ticks_ms() if timestamp is None else timestamp

    def __str__(self):
        where = ".".join([p for p in (self.board, self.motor) if p]) or "system"
        return "[%s] %s: %s" % (self.type, where, self.message)

    __repr__ = __str__


class FaultPolicy:
    """Per-motor fault response, e.g. FaultPolicy({FaultType.STALL: FaultAction.COAST}, latch=False)."""

    def __init__(self, actions=None, latch=True):
        self.actions = actions or {}
        self.latch = latch

    def action_for(self, fault_type):
        return self.actions.get(fault_type, DEFAULT_ACTIONS[fault_type])

    def latches(self, fault_type):
        return self.latch and fault_type in LATCHING

# ---------------------------------------------------------------- pins


class PinFactory:
    """Creates pins and shares them by number (for shared nSLEEP / nFAULT lines)."""

    def __init__(self):
        self._pins = {}
        self._kinds = {}
        self._refs = {}

    def _get(self, pin, kind, make):
        if pin in self._pins:
            if self._kinds[pin] != kind:
                raise ConfigError("pin %s already used as %s" % (pin, self._kinds[pin]))
            self._refs[pin] += 1
            return self._pins[pin]
        obj = make()
        self._pins[pin] = obj
        self._kinds[pin] = kind
        self._refs[pin] = 1
        return obj

    def output(self, pin, initial=False):
        return self._get(pin, "output", lambda: self._make_output(pin, initial))

    def pwm(self, pin, freq):
        return self._get(pin, "pwm", lambda: self._make_pwm(pin, freq))

    def input(self, pin):
        return self._get(pin, "input", lambda: self._make_input(pin))

    def release(self, pin):
        if pin is None or pin not in self._pins:
            return
        self._refs[pin] -= 1
        if self._refs[pin] <= 0:
            self._pins.pop(pin).close()
            del self._kinds[pin]
            del self._refs[pin]

    def _make_output(self, pin, initial):
        raise NotImplementedError

    def _make_pwm(self, pin, freq):
        raise NotImplementedError

    def _make_input(self, pin):
        raise NotImplementedError


class _MOut:
    def __init__(self, pin, initial):
        import machine
        self._p = machine.Pin(pin, machine.Pin.OUT, value=1 if initial else 0)

    def set(self, v):
        self._p.value(1 if v else 0)

    def get(self):
        return bool(self._p.value())

    def close(self):
        pass


class _MPwm:
    def __init__(self, pin, freq):
        import machine
        self._p = machine.PWM(machine.Pin(pin))
        self._p.freq(int(freq))
        self._p.duty_u16(0)
        self._d = 0.0

    def set_duty(self, d):
        d = 0.0 if d < 0 else (1.0 if d > 1 else d)
        self._d = d
        self._p.duty_u16(int(d * 65535))

    def get_duty(self):
        return self._d

    def close(self):
        self._p.duty_u16(0)
        self._p.deinit()


class _MIn:
    def __init__(self, pin):
        import machine
        self._p = machine.Pin(pin, machine.Pin.IN)   # Board A has its own pull-up on nFAULT

    def read(self):
        return bool(self._p.value())

    def close(self):
        pass


class MachinePins(PinFactory):
    """Real hardware through the ``machine`` module."""

    def _make_output(self, pin, initial):
        return _MOut(pin, initial)

    def _make_pwm(self, pin, freq):
        return _MPwm(pin, freq)

    def _make_input(self, pin):
        return _MIn(pin)


class _Mock:
    def __init__(self, pin):
        self.pin = pin
        self.value = False
        self.duty = 0.0
        self.level = True       # inputs idle high (nFAULT pulled up)

    def set(self, v):
        self.value = bool(v)

    def get(self):
        return self.value

    def set_duty(self, d):
        self.duty = 0.0 if d < 0 else (1.0 if d > 1 else d)

    def get_duty(self):
        return self.duty

    def read(self):
        return self.level

    def close(self):
        pass


class MockPins(PinFactory):
    """No hardware: for testing. Inspect ``pins.pins[n]``."""

    @property
    def pins(self):
        return self._pins

    def _make_output(self, pin, initial):
        m = _Mock(pin)
        m.value = bool(initial)
        return m

    def _make_pwm(self, pin, freq):
        m = _Mock(pin)
        m.freq = freq
        return m

    def _make_input(self, pin):
        return _Mock(pin)

# ---------------------------------------------------------------- current sensing

_PGA = {6.144: 0, 4.096: 1, 2.048: 2, 1.024: 3, 0.512: 4, 0.256: 5}
_RATES = {8: 0, 16: 1, 32: 2, 64: 3, 128: 4, 250: 5, 475: 6, 860: 7}


class ADS1115:
    """PinGoblin ADS1115 board (or any ADS1115) on a ``machine.I2C`` bus.

    Each conversion averages over about 1.2 ms (860 samples/s), so a reading
    is roughly ``PWM duty x motor current``.
    """

    def __init__(self, i2c, address=0x48, full_scale=4.096, data_rate=860):
        if address not in (0x48, 0x49, 0x4A, 0x4B):
            raise ConfigError("invalid ADS1115 address 0x%02X" % address)
        if full_scale not in _PGA:
            raise ConfigError("full_scale must be one of %s" % sorted(_PGA))
        if data_rate not in _RATES:
            raise ConfigError("data_rate must be one of %s" % sorted(_RATES))
        self.i2c = i2c
        self.address = address
        self.full_scale = full_scale
        self.data_rate = data_rate
        self._wait_ms = 1000 // data_rate + 1

    def config_word(self, channel):
        if channel not in (0, 1, 2, 3):
            raise ConfigError("ADS1115 channel must be 0-3")
        return ((1 << 15) | ((4 | channel) << 12) | (_PGA[self.full_scale] << 9)
                | (1 << 8) | (_RATES[self.data_rate] << 5) | 3)

    def read_voltage(self, channel):
        cfg = self.config_word(channel)
        try:
            self.i2c.writeto_mem(self.address, 1, bytes([cfg >> 8, cfg & 0xFF]))
            sleep_ms(self._wait_ms)
            for _ in range(10):
                if self.i2c.readfrom_mem(self.address, 1, 2)[0] & 0x80:
                    break
                sleep_ms(1)
            b = self.i2c.readfrom_mem(self.address, 0, 2)
        except OSError as exc:
            raise SensorError("ADS1115 0x%02X read failed: %s" % (self.address, exc))
        raw = (b[0] << 8) | b[1]
        if raw & 0x8000:
            raw -= 65536
        return raw * self.full_scale / 32768


class ADS1115Channel:
    def __init__(self, adc, channel):
        adc.config_word(channel)
        self.adc = adc
        self.channel = channel

    def read_voltage(self):
        return self.adc.read_voltage(self.channel)


class ADCChannel:
    """The microcontroller's own ADC (ESP32: ADC1 pins 32-39; Pico: GP26-28).

    The built-in ADC samples instantly, so with PWM each reading is either
    the full motor current or zero. Averaging many samples (``samples`` on
    the board, default 16 for ADCChannel) gives the duty-weighted mean.
    ``vref`` is used only where ``read_uv()`` isn't available (Pico).
    """

    def __init__(self, pin, vref=3.3):
        import machine
        self._adc = machine.ADC(machine.Pin(pin))
        if hasattr(self._adc, "atten") and hasattr(machine.ADC, "ATTN_11DB"):
            self._adc.atten(machine.ADC.ATTN_11DB)     # ESP32: 0-~3.1 V range
        self._uv = hasattr(self._adc, "read_uv")
        self.vref = vref

    def read_voltage(self):
        try:
            if self._uv:
                return self._adc.read_uv() / 1000000
            return self._adc.read_u16() * self.vref / 65535
        except OSError as exc:
            raise SensorError("ADC read failed: %s" % exc)


class MockSensor:
    """Test sensor: ``amps`` = current at the ISENSE pin; ``fail`` = raise."""

    def __init__(self, amps=0.0):
        self.amps = amps
        self.fail = False

    def read_voltage(self):
        if self.fail:
            raise SensorError("mock sensor failure")
        return self.amps * ISENSE_V_PER_A


class MotorCurrentSensor:
    def __init__(self, source, samples=4, v_per_a=ISENSE_V_PER_A):
        self.source = source
        self.samples = samples if samples > 0 else 1
        self.v_per_a = v_per_a

    def read_isense_amps(self):
        total = 0.0
        for _ in range(self.samples):
            total += self.source.read_voltage()
        a = total / self.samples / self.v_per_a
        return a if a > 0 else 0.0

# ---------------------------------------------------------------- motor


def _check_speed(v):
    v = float(v)
    if v < 0 or v > 100:
        raise ValueError("speed_pc must be 0-100, got %s" % v)
    return v


class Motor:
    """One motor channel. Create through MotorBoard.

    Options (seconds / amps): invert, min_speed_pc, ramp_time, reverse_delay,
    stall_current (default 80 % of the board limit), stall_time, start_grace,
    open_load_current, open_load_time, continuous_current, overload_time, policy.
    """

    def __init__(self, name, board, en_pin, ph_pin, mode, pins, sensor=None, invert=False,
                 pwm_freq=20000, min_speed_pc=0, ramp_time=0.0, reverse_delay=0.1,
                 stall_current=None, stall_time=0.5, start_grace=0.3, open_load_current=0.03,
                 open_load_time=1.0, continuous_current=1.5, overload_time=5.0, policy=None):
        if min_speed_pc < 0 or min_speed_pc >= 100:
            raise ConfigError("min_speed_pc must be 0-99")
        if ramp_time < 0 or reverse_delay < 0:
            raise ConfigError("ramp_time and reverse_delay must be >= 0")
        self.name = name
        self.board = board
        self.mode = mode
        self.sensor = sensor
        self.invert = invert
        self.min_speed_pc = float(min_speed_pc)
        self.ramp_time = float(ramp_time)
        self.reverse_delay = float(reverse_delay)
        self.stall_current = stall_current if stall_current is not None else 0.8 * board.current_limit
        self.stall_time = stall_time
        self.start_grace = start_grace
        self.open_load_current = open_load_current
        self.open_load_time = open_load_time
        self.continuous_current = continuous_current
        self.overload_time = overload_time
        self.policy = policy or FaultPolicy()
        self._pins = pins
        self._en_pin = en_pin
        self._ph_pin = ph_pin
        self._en = pins.pwm(en_pin, pwm_freq)
        self._ph = pins.output(ph_pin, False) if mode == ControlMode.PH_EN else pins.pwm(ph_pin, pwm_freq)
        self._state = MotorState.STOPPED
        self._direction = None
        self._speed_pc = 0.0
        self._duty = 0.0
        self._since = ticks_ms()
        self._stop_at = None
        self._ramp = None            # (from_duty, to_duty, start_ticks, ms)
        self._fault = None
        self._handlers = []
        self.last_current = None
        self.last_isense_amps = None
        self._apply_brake()

    # ---- properties
    @property
    def full_name(self):
        return "%s.%s" % (self.board.name, self.name)

    @property
    def state(self):
        return self._state

    @property
    def direction(self):
        return self._direction

    @property
    def is_running(self):
        return self._state == MotorState.RUNNING

    @property
    def duty(self):
        return self._duty

    @property
    def running_since(self):
        return self._since

    @property
    def fault(self):
        return self._fault

    @property
    def has_sensor(self):
        return self.sensor is not None

    @property
    def busy(self):
        """True while a timed run or a ramp is still in progress."""
        return self._stop_at is not None or self._ramp is not None

    @property
    def speed_pc(self):
        return self._speed_pc

    @speed_pc.setter
    def speed_pc(self, value):
        value = _check_speed(value)
        self._speed_pc = value
        if self.is_running:
            if value == 0:
                self.stop()
            else:
                self._since = ticks_ms()
                self._ramp_to(self._speed_to_duty(value))

    @property
    def current(self):
        """Motor amps (reads the sensor), or None without one."""
        return self.read_current() if self.sensor is not None else None

    # ---- commands
    def forward(self, speed_pc=100, duration=None, wait=False):
        self._run(Direction.FORWARD, speed_pc, duration, wait)

    def reverse(self, speed_pc=100, duration=None, wait=False):
        self._run(Direction.REVERSE, speed_pc, duration, wait)

    def run(self, speed_pc, duration=None, wait=False):
        """Signed speed: +50 forward, -50 reverse, 0 stop."""
        if speed_pc == 0:
            self.stop()
        else:
            self._run(Direction.FORWARD if speed_pc > 0 else Direction.REVERSE,
                      abs(speed_pc), duration, wait)

    def start(self, duration=None, wait=False):
        self._run(self._direction or Direction.FORWARD, self._speed_pc or 100, duration, wait)

    def stop(self):
        """Brake (outputs low): stops quickly."""
        self._stop_at = None
        self._ramp = None
        self._apply_brake()
        if self._state != MotorState.FAULT:
            self._state = MotorState.STOPPED

    brake = stop

    def coast(self):
        """Spin down freely. In PH/EN mode only if no other motor on the nSLEEP line runs;
        otherwise brakes and returns False."""
        self._stop_at = None
        self._ramp = None
        if self.mode == ControlMode.PWM:
            self._apply_coast()
            ok = True
        else:
            self._apply_brake()
            ok = self.board._coast_request(self)
        if self._state != MotorState.FAULT:
            self._state = MotorState.COASTING if ok else MotorState.STOPPED
        return ok

    def wait(self, timeout=None):
        """Block until a timed run or ramp finishes, keeping update() running.
        Returns False on timeout."""
        t0 = ticks_ms()
        owner = self.board._owner()
        while self.busy:
            owner.update()
            if timeout is not None and ticks_diff(ticks_ms(), t0) >= timeout * 1000:
                return False
            sleep_ms(5)
        return True

    def read_current(self):
        if self.sensor is None:
            raise ConfigError("%s has no current sensor" % self.full_name)
        isense = self.sensor.read_isense_amps()
        amps = isense / self._duty if self._duty >= 0.1 else isense
        self.last_isense_amps = isense
        self.last_current = amps
        return amps

    def add_fault_handler(self, handler):
        self._handlers.append(handler)

    def clear_fault(self):
        self._fault = None
        if self._state == MotorState.FAULT:
            self._state = MotorState.STOPPED

    def close(self):
        try:
            self.stop()
        finally:
            self._pins.release(self._en_pin)
            self._pins.release(self._ph_pin)

    def __repr__(self):
        return "<Motor %s %s %s %d%%>" % (self.full_name, self._state, self._direction or "-", int(self._speed_pc))

    # ---- internals
    def _report_fault(self, fault):
        action = self.policy.action_for(fault.type)
        if action == FaultAction.BRAKE:
            self.stop()
        elif action == FaultAction.COAST:
            self.coast()
        elif action == FaultAction.SLEEP:
            self.stop()
            if self.board._sleep is not None:
                self.board.sleep()
        if self.policy.latches(fault.type):
            self._fault = fault
            self._state = MotorState.FAULT
        for h in self._handlers:
            try:
                h(fault)
            except Exception as exc:  # a bad handler must not stop fault handling
                print("pingoblin_motor: fault handler error:", exc)

    def _speed_to_duty(self, speed_pc):
        if speed_pc <= 0:
            return 0.0
        return max(speed_pc, self.min_speed_pc) / 100

    def _run(self, direction, speed_pc, duration, wait):
        speed_pc = _check_speed(speed_pc)
        if duration is not None and duration <= 0:
            raise ValueError("duration must be > 0")
        if self._fault is not None:
            raise MotorFaultError(self._fault)
        self._stop_at = None
        if speed_pc == 0:
            self._speed_pc = 0.0
            self.stop()
            return
        self.board._ensure_awake()
        reversing = self.is_running and self._direction != direction and self._duty > 0
        if reversing:
            self._ramp = None
            self._apply_brake()
            if self.reverse_delay:
                sleep_ms(int(self.reverse_delay * 1000))
        self._direction = direction
        self._speed_pc = speed_pc
        self._state = MotorState.RUNNING
        self._since = ticks_ms()
        self._ramp_to(self._speed_to_duty(speed_pc))
        if duration is not None:
            self._stop_at = (self._since, int(duration * 1000))
            if wait:
                self.wait()

    def _ramp_to(self, target):
        if self.ramp_time <= 0 or abs(target - self._duty) < 1e-6:
            self._ramp = None
            self._apply_drive(target)
            return
        ms = int(abs(target - self._duty) * self.ramp_time * 1000)
        self._ramp = (self._duty, target, ticks_ms(), ms if ms > 0 else 1)
        self._apply_drive(self._duty)          # set direction pins now

    def _tick(self, now):
        if self._ramp is not None:
            a, b, t0, ms = self._ramp
            f = ticks_diff(now, t0) / ms
            if f >= 1:
                self._ramp = None
                self._apply_drive(b)
            else:
                self._apply_drive(a + (b - a) * f)
        if self._stop_at is not None:
            t0, ms = self._stop_at
            if ticks_diff(now, t0) >= ms:
                self._stop_at = None
                if self.is_running:
                    self._ramp = None
                    self._apply_brake()
                    self._state = MotorState.STOPPED

    def _apply_drive(self, duty):
        duty = 0.0 if duty < 0 else (1.0 if duty > 1 else duty)
        self._duty = duty
        fwd = (self._direction == Direction.FORWARD) != self.invert
        if self.mode == ControlMode.PH_EN:
            self._ph.set(not fwd)               # forward = PH low
            self._en.set_duty(duty)
        elif fwd:                               # PWM mode, slow decay: IN1 = 1-duty, IN2 = 1
            self._ph.set_duty(1.0)
            self._en.set_duty(1.0 - duty)
        else:
            self._en.set_duty(1.0)
            self._ph.set_duty(1.0 - duty)

    def _apply_brake(self):
        self._duty = 0.0
        if self.mode == ControlMode.PH_EN:
            self._en.set_duty(0.0)
        else:
            self._en.set_duty(1.0)
            self._ph.set_duty(1.0)

    def _apply_coast(self):
        self._duty = 0.0
        self._en.set_duty(0.0)
        if self.mode == ControlMode.PWM:
            self._ph.set_duty(0.0)

# ---------------------------------------------------------------- board

_sleep_groups = {}


class MotorBoard:
    """One Board A. Pins are GPIO numbers.

    mode: "ph_en" (default, JP1 1-2) or "pwm" (JP1 2-3).
    logic_voltage: VLOGIC; sets the current limit (2.0 A at 3.3 V, 3.0 A at 5 V).
    Current sensing: pass ``adc`` (ADS1115) with a_sense_channel / b_sense_channel,
    or ``a_sensor`` / ``b_sensor`` (e.g. ADCChannel(34) for the ESP32's own ADC).
    """

    def __init__(self, name="board", a_en=None, a_ph=None, b_en=None, b_ph=None,
                 sleep_pin=None, fault_pin=None, mode="ph_en", logic_voltage=3.3,
                 adc=None, a_sense_channel=None, b_sense_channel=None,
                 a_sensor=None, b_sensor=None, sense_samples=None, pins=None,
                 pwm_freq=20000, motor_names=("a", "b"), motor_options=None,
                 a_options=None, b_options=None, fuse_rating=3.0):
        if a_en is None or a_ph is None:
            raise ConfigError("a_en and a_ph are required")
        if mode not in (ControlMode.PH_EN, ControlMode.PWM):
            raise ConfigError("mode must be 'ph_en' or 'pwm'")
        if logic_voltage < 3.0 or logic_voltage > 5.5:
            raise ConfigError("logic_voltage must be 3.0-5.5 V")
        if (b_en is None) != (b_ph is None):
            raise ConfigError("give both b_en and b_ph, or neither")
        used = [p for p in (a_en, a_ph, b_en, b_ph) if p is not None]
        if len(set(used)) != len(used):
            raise ConfigError("motor control pins must all be different")
        if sleep_pin in used or fault_pin in used:
            raise ConfigError("sleep/fault pins must not reuse a motor pin")
        if "." in name or len(motor_names) != 2 or motor_names[0] == motor_names[1] \
                or "." in motor_names[0] or "." in motor_names[1]:
            raise ConfigError("names must be unique and must not contain '.'")
        self.name = name
        self.mode = mode
        self.logic_voltage = logic_voltage
        self.fuse_rating = fuse_rating
        self.pins = pins or MachinePins()
        self._sleep_pin = sleep_pin
        self._fault_pin = fault_pin
        self._sleep = self.pins.output(sleep_pin, True) if sleep_pin is not None else None
        self._fault = self.pins.input(fault_pin) if fault_pin is not None else None
        if sleep_pin is not None:
            _sleep_groups.setdefault((id(self.pins), sleep_pin), []).append(self)
        self._chain = None
        self.monitor = None
        self.motors = {}
        specs = [(motor_names[0], a_en, a_ph, a_sense_channel, a_sensor, a_options)]
        if b_en is not None:
            specs.append((motor_names[1], b_en, b_ph, b_sense_channel, b_sensor, b_options))
        self._order = []
        for mname, en, ph, ch, src, opts in specs:
            kw = dict(motor_options or {})
            kw.update(opts or {})
            if src is None and adc is not None and ch is not None:
                src = ADS1115Channel(adc, ch)
            sensor = None
            if src is not None:
                n = sense_samples or (16 if isinstance(src, ADCChannel) else 4)
                sensor = MotorCurrentSensor(src, n)
            self.motors[mname] = Motor(mname, self, en, ph, mode, self.pins, sensor=sensor,
                                       pwm_freq=pwm_freq, **kw)
            self._order.append(mname)

    # ---- properties
    @property
    def current_limit(self):
        return self.logic_voltage * 0.4 / ISENSE_V_PER_A

    @property
    def motor_a(self):
        return self.motors[self._order[0]]

    @property
    def motor_b(self):
        return self.motors[self._order[1]] if len(self._order) > 1 else None

    @property
    def is_asleep(self):
        return self._sleep is not None and not self._sleep.get()

    @property
    def fault_active(self):
        """True while nFAULT is low; None if fault_pin isn't wired."""
        return None if self._fault is None else (not self._fault.read())

    @property
    def total_current(self):
        vals = [m.last_isense_amps for m in self.motors.values() if m.has_sensor]
        if not vals or None in vals:
            return None
        return sum(vals)

    def __getitem__(self, name):
        return self.motors[name]

    def __iter__(self):
        return iter([self.motors[n] for n in self._order])

    # ---- commands
    def sleep(self):
        if self._sleep is None:
            raise ConfigError("%s: no sleep_pin configured" % self.name)
        for b in self._sleep_group():
            for m in b.motors.values():
                m.stop()
        self._sleep.set(False)

    def wake(self):
        if self._sleep is not None and not self._sleep.get():
            self._sleep.set(True)
            sleep_ms(WAKE_MS)

    def stop_all(self):
        for m in self.motors.values():
            m.stop()

    def coast_all(self):
        self.stop_all()
        if self.mode == ControlMode.PWM:
            for m in self.motors.values():
                m.coast()
        elif self._sleep is not None:
            self.sleep()
            for m in self.motors.values():
                if m.fault is None:
                    m._state = MotorState.COASTING

    def enable_monitor(self, interval=0.05, on_fault=None):
        """Turn on fault checking inside update(). Returns the FaultMonitor."""
        if self.monitor is None:
            self.monitor = FaultMonitor([self], interval)
        if on_fault:
            self.monitor.add_fault_handler(on_fault)
        return self.monitor

    def update(self):
        """Advance ramps and timed runs, and run fault checks. Call often (10-50 ms)."""
        now = ticks_ms()
        for m in self.motors.values():
            m._tick(now)
        if self.monitor is not None:
            self.monitor.poll(now)

    def pause(self, seconds):
        """Blocking sleep that keeps update() running."""
        _pause(self, seconds)

    async def run_monitor(self, interval=0.02):
        """asyncio task: ``asyncio.create_task(board.run_monitor())``."""
        if self.monitor is None:
            self.enable_monitor()
        while True:
            self.update()
            await asyncio.sleep(interval)

    def close(self):
        for m in self.motors.values():
            m.close()
        if self._sleep_pin is not None:
            grp = _sleep_groups.get((id(self.pins), self._sleep_pin), [])
            if self in grp:
                grp.remove(self)
        self.pins.release(self._sleep_pin)
        self.pins.release(self._fault_pin)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self):
        return "<MotorBoard %s %s motors=%s>" % (self.name, self.mode, self._order)

    # ---- internals
    def _owner(self):
        return self._chain if self._chain is not None else self

    def _sleep_group(self):
        if self._sleep_pin is None:
            return [self]
        return list(_sleep_groups.get((id(self.pins), self._sleep_pin), [self]))

    def _ensure_awake(self):
        self.wake()

    def _coast_request(self, motor):
        if self._sleep is None:
            return False
        for b in self._sleep_group():
            for m in b.motors.values():
                if m is not motor and m.is_running:
                    return False
        self._sleep.set(False)
        return True

    def _report_board_fault(self, fault):
        for m in self.motors.values():
            m._report_fault(Fault(fault.type, fault.message, self.name, m.name, fault.value, fault.timestamp))


def _pause(owner, seconds):
    t0 = ticks_ms()
    ms = int(seconds * 1000)
    while ticks_diff(ticks_ms(), t0) < ms:
        owner.update()
        sleep_ms(5)

# ---------------------------------------------------------------- chain


class MotorChain:
    """Several daisy-chained boards as one system; motors as "board.motor" or aliases."""

    def __init__(self, boards=(), chain_current_limit=6.0, monitor=True, interval=0.05):
        self.boards = {}
        self._aliases = {}
        self.chain_current_limit = chain_current_limit
        self.monitor = FaultMonitor([], interval, chain_current_limit) if monitor else None
        for b in boards:
            self.add_board(b)

    def add_board(self, board):
        if board.name in self.boards:
            raise ConfigError("duplicate board name '%s'" % board.name)
        board.monitor = None          # the chain monitor takes over
        board._chain = self
        self.boards[board.name] = board
        if self.monitor is not None:
            self.monitor.boards.append(board)
        return board

    def alias(self, alias, target):
        if "." in alias:
            raise ConfigError("aliases must not contain '.'")
        m = self.motor(target)
        self._aliases[alias] = m
        return m

    def motor(self, name):
        if name in self._aliases:
            return self._aliases[name]
        parts = name.split(".", 1)
        try:
            return self.boards[parts[0]].motors[parts[1]]
        except (KeyError, IndexError):
            raise KeyError("no motor '%s' (use 'board.motor' or an alias)" % name)

    __getitem__ = motor

    @property
    def motors(self):
        out = []
        for b in self.boards.values():
            out.extend(list(b))
        return out

    def __iter__(self):
        return iter(self.motors)

    @property
    def faults(self):
        return list(self.monitor.faults) if self.monitor else []

    @property
    def active_faults(self):
        return [m.fault for m in self.motors if m.fault is not None]

    @property
    def total_current(self):
        vals = [b.total_current for b in self.boards.values()]
        if not vals or None in vals:
            return None
        return sum(vals)

    def add_fault_handler(self, handler):
        if self.monitor is None:
            raise ConfigError("chain was created with monitor=False")
        self.monitor.add_fault_handler(handler)

    def stop_all(self):
        for m in self.motors:
            m.stop()

    def coast_all(self):
        for b in self.boards.values():
            b.coast_all()

    def emergency_stop(self):
        self.stop_all()
        for b in self.boards.values():
            if b._sleep is not None:
                b.sleep()

    def clear_faults(self):
        for m in self.motors:
            m.clear_fault()

    def update(self):
        now = ticks_ms()
        for m in self.motors:
            m._tick(now)
        if self.monitor is not None:
            self.monitor.poll(now)

    def check_faults(self):
        """Run one fault check now (ignores the interval)."""
        return self.monitor.check_once() if self.monitor else []

    def pause(self, seconds):
        _pause(self, seconds)

    async def run_monitor(self, interval=0.02):
        while True:
            self.update()
            await asyncio.sleep(interval)

    def close(self):
        for b in self.boards.values():
            b.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

# ---------------------------------------------------------------- fault monitor

DRIVER_FAULT_DEBOUNCE_MS = 200
OVERLOAD_DEBOUNCE_MS = 1000
CURRENT_LIMIT_REPEAT_MS = 5000
OPEN_LOAD_MIN_DUTY = 0.2


class _Track:
    def __init__(self):
        self.stall = None
        self.open = None
        self.over = None
        self.limit = None
        self.sensor_failed = False


class FaultMonitor:
    """Detects STALL, CURRENT_LIMIT, DRIVER_FAULT, OPEN_LOAD, OVERLOAD,
    BOARD_OVERLOAD, CHAIN_OVERLOAD and SENSOR_ERROR. Runs inside update()."""

    def __init__(self, boards, interval=0.05, chain_current_limit=None, clock=None):
        self.boards = list(boards)
        self.interval_ms = int(interval * 1000)
        self.chain_current_limit = chain_current_limit
        self.clock = clock or ticks_ms
        self.faults = []
        self.max_history = 50
        self._handlers = []
        self._tracks = {}
        self._drv = {}
        self._bover = {}
        self._chain_since = None
        self._last = None

    def add_fault_handler(self, handler):
        self._handlers.append(handler)

    def poll(self, now=None):
        """check_once() if at least ``interval`` has passed since the last check."""
        now = self.clock() if now is None else now
        if self._last is None or ticks_diff(now, self._last) >= self.interval_ms:
            self._last = now
            return self.check_once(now)
        return []

    def check_once(self, now=None):
        now = self.clock() if now is None else now
        found = []
        total = 0.0
        known = True
        for b in self.boards:
            t, k = self._check_board(b, now, found)
            total += t
            known = known and k
        lim = self.chain_current_limit
        if lim is not None and known and self.boards:
            if total > lim:
                if self._chain_since is None:
                    self._chain_since = now
                elif ticks_diff(now, self._chain_since) >= OVERLOAD_DEBOUNCE_MS:
                    msg = "daisy chain draws %.2f A, above the %.1f A chain limit" % (total, lim)
                    for b in self.boards:
                        for m in b.motors.values():
                            if m.is_running:
                                self._emit(Fault(FaultType.CHAIN_OVERLOAD, msg, b.name, m.name, total, now),
                                           m, found)
                    self._chain_since = None
            else:
                self._chain_since = None
        return found

    def _check_board(self, board, now, found):
        key = id(board)
        if board.is_asleep:
            for m in board.motors.values():
                self._tracks[id(m)] = _Track()
            self._drv[key] = None
            return 0.0, True
        nfault = board.fault_active
        driving = [m for m in board.motors.values() if m.is_running and m.duty > 0]

        if nfault and not driving:
            since = self._drv.get(key)
            if since is None:
                self._drv[key] = now
            elif ticks_diff(now, since) >= DRIVER_FAULT_DEBOUNCE_MS:
                f = Fault(FaultType.DRIVER_FAULT, "nFAULT low with no motor driven: driver shut down "
                          "(output short, overcurrent or over-temperature)", board.name, None, None, now)
                self._record(f, found)
                board._report_board_fault(f)
                self._drv[key] = None
        else:
            self._drv[key] = None

        total = 0.0
        known = True
        for m in board.motors.values():
            tr = self._tracks.get(id(m))
            if tr is None:
                tr = self._tracks[id(m)] = _Track()
            amps = None
            if m.has_sensor:
                try:
                    amps = m.read_current()
                    tr.sensor_failed = False
                    total += m.last_isense_amps or 0.0
                except SensorError as exc:
                    known = False
                    if not tr.sensor_failed:
                        tr.sensor_failed = True
                        self._emit(Fault(FaultType.SENSOR_ERROR, str(exc), board.name, m.name, None, now),
                                   m, found)
            else:
                known = False

            if not (m.is_running and m.duty > 0):
                tr.stall = tr.open = tr.over = None
                continue
            in_grace = ticks_diff(now, m.running_since) < m.start_grace * 1000

            if nfault and (tr.limit is None or ticks_diff(now, tr.limit) >= CURRENT_LIMIT_REPEAT_MS):
                tr.limit = now
                self._emit(Fault(FaultType.CURRENT_LIMIT, "driver current-limiting", board.name, m.name,
                                 amps, now), m, found)

            stalled = (amps >= m.stall_current) if amps is not None else bool(nfault)
            if stalled and not in_grace:
                if tr.stall is None:
                    tr.stall = now
                elif ticks_diff(now, tr.stall) >= m.stall_time * 1000:
                    if amps is not None:
                        detail = "%.2f A for %.1f s" % (amps, m.stall_time)
                    else:
                        detail = "driver current-limiting for %.1f s" % m.stall_time
                        if len(driving) > 1:
                            detail += " (both motors running; cannot tell which one, stopping both)"
                    self._emit(Fault(FaultType.STALL, "motor stalled: " + detail, board.name, m.name, amps, now),
                               m, found)
                    tr.stall = None
                    continue
            else:
                tr.stall = None

            if amps is None:
                continue

            if not in_grace and m.duty >= OPEN_LOAD_MIN_DUTY and amps < m.open_load_current:
                if tr.open is None:
                    tr.open = now
                elif ticks_diff(now, tr.open) >= m.open_load_time * 1000:
                    self._emit(Fault(FaultType.OPEN_LOAD,
                                     "no motor current (%d mA): motor disconnected, broken wire, "
                                     "motor supply off or board fuse tripped" % int(amps * 1000),
                                     board.name, m.name, amps, now), m, found)
                    tr.open = None
                    continue
            else:
                tr.open = None

            if amps > m.continuous_current:
                if tr.over is None:
                    tr.over = now
                elif ticks_diff(now, tr.over) >= m.overload_time * 1000:
                    self._emit(Fault(FaultType.OVERLOAD, "%.2f A above the %.1f A continuous rating for %d s"
                                     % (amps, m.continuous_current, int(m.overload_time)),
                                     board.name, m.name, amps, now), m, found)
                    tr.over = None
            else:
                tr.over = None

        if known and total > board.fuse_rating:
            since = self._bover.get(key)
            if since is None:
                self._bover[key] = now
            elif ticks_diff(now, since) >= OVERLOAD_DEBOUNCE_MS:
                msg = "board draws %.2f A, above the %.1f A fuse rating" % (total, board.fuse_rating)
                for m in board.motors.values():
                    if m.is_running:
                        self._emit(Fault(FaultType.BOARD_OVERLOAD, msg, board.name, m.name, total, now), m, found)
                self._bover[key] = None
        else:
            self._bover[key] = None
        return total, known

    def _record(self, fault, found):
        found.append(fault)
        self.faults.append(fault)
        if len(self.faults) > self.max_history:
            self.faults.pop(0)
        for h in self._handlers:
            try:
                h(fault)
            except Exception as exc:
                print("pingoblin_motor: fault handler error:", exc)

    def _emit(self, fault, motor, found):
        self._record(fault, found)
        motor._report_fault(fault)
