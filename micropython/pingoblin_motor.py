"""`pingoblin_motor` for MicroPython: the PinGoblin Board A (2 × DRV8874) motor library in one file.

Runs on ESP32 and Raspberry Pi Pico / Pico 2 with MicroPython 1.20 or later, and has the
same class and method names as the Raspberry Pi library: `MotorBoard`, `Motor`,
`MotorChain`, `forward()`, `reverse()`, `run()`, `start()`, `stop()` / `brake()`,
`coast()`, `speed_pc` and `current`.

There are no threads. Timed runs, ramps and fault checks happen in `update()`, which
must be called in one of three ways:

- as an asyncio task: `asyncio.create_task(board.run_monitor())`;
- through the blocking helpers: `board.pause(2)` or `motor.forward(50, 2, wait=True)`;
- from your own main loop, every 10–50 ms.

The source is about 63 KB, much of it docstrings. Precompile it with `mpy-cross` and
copy the `.mpy` to the board: `.mpy` files leave the docstrings out and skip on-board
compilation, which can run out of RAM on an ESP32 without PSRAM.

Example:
    ```python
    from pingoblin_motor import MotorBoard

    board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39)
    board.enable_monitor(on_fault=print)
    board.motor_a.forward(60, duration=2, wait=True)
    ```

MIT licence. Documentation: https://pingoblin.github.io/DRV8874/
"""

import time

try:
    import asyncio
except ImportError:  # older MicroPython
    try:
        import uasyncio as asyncio
    except ImportError:
        asyncio = None

__version__ = "0.1.0"
"""Library version."""

# ---------------------------------------------------------------- timing
_clock_offset = [0]   # test hook (CPython only)
"""Test hook: milliseconds added to the CPython clock shim."""

if hasattr(time, "ticks_ms"):
    ticks_ms = time.ticks_ms
    ticks_diff = time.ticks_diff
    sleep_ms = time.sleep_ms
else:  # CPython: lets the test suite run off-target
    def ticks_ms():
        """Milliseconds from a free-running clock. On MicroPython this is `time.ticks_ms`."""
        return int(time.monotonic() * 1000) + _clock_offset[0]

    def ticks_diff(a, b):
        """Milliseconds from tick `b` to tick `a`. On MicroPython this is `time.ticks_diff` (handles wrap-around)."""
        return a - b

    def sleep_ms(ms):
        """Sleep for `ms` milliseconds. On MicroPython this is `time.sleep_ms`."""
        time.sleep(ms / 1000)


def _advance_clock(ms):
    """Move the CPython clock shim forward (testing only; no effect on MicroPython).

    Args:
        ms: Milliseconds to add.
    """
    _clock_offset[0] += int(ms)


VREF_V = 1.24 * (1 + 10 / 15)   # on-board TLV431 reference: ITRIP about 3 A, fixed
ISENSE_V_PER_A = 0.675     # 1.5 kOhm x 450 uA/A (DRV8874 IPROPI)
"""Board A ISENSE gain: 0.675 V per amp (1.5 kΩ × 450 µA/A)."""
WAKE_MS = 2                # DRV8874 wake-up from sleep is about 1 ms
"""Milliseconds to wait after waking the drivers (the DRV8874 needs about 1 ms)."""

# ---------------------------------------------------------------- constants


class Direction:
    """Direction of rotation (string constants).

    Attributes:
        FORWARD: `"forward"`: PH high, OUT1 positive (TI's convention).
        REVERSE: `"reverse"`: PH low, OUT2 positive.
    """

    FORWARD = "forward"
    REVERSE = "reverse"


class MotorState:
    """What a motor is doing (string constants).

    Attributes:
        STOPPED: `"stopped"`: braked; both outputs low.
        COASTING: `"coasting"`: outputs open; spins down freely.
        RUNNING: `"running"`: driven.
        FAULT: `"fault"`: a latched fault. Call `clear_fault()`.
    """

    STOPPED = "stopped"     # braked
    COASTING = "coasting"
    RUNNING = "running"
    FAULT = "fault"         # latched fault; call clear_fault()


class ControlMode:
    """Control mode set by the PMODE jumper JP1 (string constants).

    Attributes:
        PH_EN: `"ph_en"`: default (JP1 pads 1–2). EN = speed PWM, PH = direction.
        PWM: `"pwm"`: JP1 pads 2–3. IN1 / IN2; allows per-motor coast.
    """

    PH_EN = "ph_en"         # JP1 pads 1-2 (default): EN = speed PWM, PH = direction
    PWM = "pwm"             # JP1 pads 2-3: IN1 / IN2


class FaultType:
    """Every fault the library can detect (string constants).

    | Constant | Detected when | Needs sensor |
    |---|---|---|
    | `STALL` | Current at or above `stall_current` for `stall_time` while driven, or nFAULT low for `stall_time` without a sensor | No |
    | `CURRENT_LIMIT` | nFAULT low while driven (warning, at most every 5 s) | No |
    | `DRIVER_FAULT` | nFAULT low for 0.2 s with no motor driven: short, overcurrent or over-temperature | No |
    | `OPEN_LOAD` | Under `open_load_current` for `open_load_time` while driven at 20 % or more | Yes |
    | `OVERLOAD` | Above `continuous_current` for `overload_time` | Yes |
    | `BOARD_OVERLOAD` | Board supply current above `fuse_rating` (3 A) for 1 s | Yes |
    | `CHAIN_OVERLOAD` | Chain supply current above the chain limit (6 A) for 1 s | Yes |
    | `SENSOR_ERROR` | The current sensor could not be read | Yes |
    """

    STALL = "stall"
    CURRENT_LIMIT = "current_limit"
    DRIVER_FAULT = "driver_fault"
    OPEN_LOAD = "open_load"
    OVERLOAD = "overload"
    BOARD_OVERLOAD = "board_overload"
    CHAIN_OVERLOAD = "chain_overload"
    SENSOR_ERROR = "sensor_error"


class FaultAction:
    """What to do to a motor when a fault is detected (string constants).

    Attributes:
        NONE: Record and report only.
        BRAKE: Brake the motor.
        COAST: Coast if possible, otherwise brake.
        SLEEP: Sleep the board (all motors coast). Brakes if there is no sleep pin.
    """

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
"""Default `FaultAction` for each `FaultType`."""
LATCHING = (FaultType.STALL, FaultType.DRIVER_FAULT, FaultType.OPEN_LOAD, FaultType.OVERLOAD)
"""Fault types that latch until `clear_fault()`."""

# ---------------------------------------------------------------- faults and errors


class MotorError(Exception):
    """Base class for every exception raised by the library."""

    pass


class ConfigError(MotorError):
    """Invalid configuration: pins, modes, names or limits."""

    pass


class SensorError(MotorError):
    """The current sensor could not be read."""

    pass


class MotorFaultError(MotorError):
    """Raised when you command a motor that has a latched fault. Call `clear_fault()` first.

    Attributes:
        fault (Fault): The latched fault.
    """

    def __init__(self, fault):
        """
        Args:
            fault: The latched `Fault`.
        """
        super().__init__("motor has a latched fault: %s. Call clear_fault() first." % fault)
        self.fault = fault


class Fault:
    """A record of one detected fault. `str(fault)` gives a one-line summary.

    Attributes:
        type (str): A `FaultType` constant.
        message (str): Description, including the likely cause.
        board (str | None): Board name, or `None` for a chain-wide fault.
        motor (str | None): Motor name, or `None` for a board-wide fault.
        value (float | None): The measured value that triggered it (A), if any.
        timestamp (int): `ticks_ms()` when it was detected.
    """

    def __init__(self, type, message, board=None, motor=None, value=None, timestamp=None):
        """
        Args:
            type: A `FaultType` constant.
            message: Description.
            board: Board name.
            motor: Motor name.
            value: Measured value (A).
            timestamp: `ticks_ms()` value. Default: now.
        """
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
    """Per-motor fault response.

    Example:
        ```python
        policy = FaultPolicy({FaultType.STALL: FaultAction.COAST}, latch=False)
        board = MotorBoard(a_en=25, a_ph=26, a_options=dict(policy=policy))
        ```
    """

    def __init__(self, actions=None, latch=True):
        """
        Args:
            actions: Dict mapping `FaultType` constants to `FaultAction` constants. Missing
                types use `DEFAULT_ACTIONS`.
            latch: Whether `STALL`, `DRIVER_FAULT`, `OPEN_LOAD` and `OVERLOAD` latch.
        """
        self.actions = actions or {}
        self.latch = latch

    def action_for(self, fault_type):
        """Return the action for a fault type.

        Args:
            fault_type: A `FaultType` constant.

        Returns:
            A `FaultAction` constant.
        """
        return self.actions.get(fault_type, DEFAULT_ACTIONS[fault_type])

    def latches(self, fault_type):
        """Return whether a fault of this type latches the motor.

        Args:
            fault_type: A `FaultType` constant.

        Returns:
            `True` if the motor must be cleared with `clear_fault()`.
        """
        return self.latch and fault_type in LATCHING

# ---------------------------------------------------------------- pins


class PinFactory:
    """Creates pins and shares them by GPIO number, so boards can share one nSLEEP line.

    A shared pin is closed when the last user releases it. Subclasses implement
    `_make_output()`, `_make_pwm()` and `_make_input()`.
    """

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
        """Get a digital output, creating it on first use.

        Args:
            pin: GPIO number.
            initial: Level when first created.

        Returns:
            An object with `set(value)` and `get()`.

        Raises:
            ConfigError: The pin is already used as another kind.
        """
        return self._get(pin, "output", lambda: self._make_output(pin, initial))

    def pwm(self, pin, freq):
        """Get a PWM output, creating it on first use (duty 0).

        Args:
            pin: GPIO number.
            freq: PWM frequency (Hz).

        Returns:
            An object with `set_duty(0..1)` and `get_duty()`.

        Raises:
            ConfigError: The pin is already used as another kind.
        """
        return self._get(pin, "pwm", lambda: self._make_pwm(pin, freq))

    def input(self, pin):
        """Get a digital input, creating it on first use (no internal pull).

        Args:
            pin: GPIO number.

        Returns:
            An object with `read()`.

        Raises:
            ConfigError: The pin is already used as an output.
        """
        return self._get(pin, "input", lambda: self._make_input(pin))

    def release(self, pin):
        """Drop one reference to a pin, and close it when no one uses it.

        Args:
            pin: GPIO number, or `None` (ignored).
        """
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
    """Real hardware through the `machine` module: `Pin`, and `PWM` with `duty_u16()`."""

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
    """Hardware-free pins for tests. Inspect `pins.pins[n]`.

    Each pin object has `value` (outputs), `duty` (PWM), `freq` (PWM) and `level` (inputs;
    starts high like nFAULT's pull-up).
    """

    @property
    def pins(self):
        """The pins created so far, by GPIO number."""
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
    """PinGoblin ADS1115 board (or any ADS1115) on a `machine.I2C` bus.

    Each conversion averages over about 1.2 ms (860 samples/s), so with PWM a reading is
    roughly *duty × motor current*.

    Example:
        ```python
        from machine import I2C, Pin
        adc = ADS1115(I2C(0, sda=Pin(21), scl=Pin(22), freq=400000), address=0x48)
        ```
    """

    def __init__(self, i2c, address=0x48, full_scale=4.096, data_rate=860):
        """
        Args:
            i2c: A `machine.I2C` (or any object with `writeto_mem()` and `readfrom_mem()`).
            address: 0x48, 0x49, 0x4A or 0x4B.
            full_scale: Input range (V). 4.096 covers ISENSE at 5 V logic.
            data_rate: Samples per second.

        Raises:
            ConfigError: Invalid address, range or rate.
        """
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
        """Build the config-register value for a single-shot read.

        Args:
            channel: Input 0–3 (AINx against GND).

        Returns:
            The 16-bit config register value.

        Raises:
            ConfigError: Channel out of range.
        """
        if channel not in (0, 1, 2, 3):
            raise ConfigError("ADS1115 channel must be 0-3")
        return ((1 << 15) | ((4 | channel) << 12) | (_PGA[self.full_scale] << 9)
                | (1 << 8) | (_RATES[self.data_rate] << 5) | 3)

    def read_voltage(self, channel):
        """Start a conversion, wait for it and return the voltage.

        Args:
            channel: Input 0–3.

        Returns:
            The input voltage (V).

        Raises:
            SensorError: The I²C transfer failed.
        """
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
    """One ADS1115 input wired to an ISENSE pin."""

    def __init__(self, adc, channel):
        """
        Args:
            adc: The `ADS1115`.
            channel: Input 0–3.

        Raises:
            ConfigError: Channel out of range.
        """
        adc.config_word(channel)
        self.adc = adc
        self.channel = channel

    def read_voltage(self):
        """Read this channel.

        Returns:
            The ISENSE voltage (V).

        Raises:
            SensorError: The I²C transfer failed.
        """
        return self.adc.read_voltage(self.channel)


class ADCChannel:
    """The microcontroller's own ADC on an ISENSE pin (ESP32: ADC1 pins 32–39; Pico: GP26-28).

    The built-in ADC samples instantly, so with PWM each sample is either the full motor
    current or zero. Boards average 16 samples per reading by default for this sensor.
    On the ESP32 the input range is set to about 0–3.1 V (11 dB attenuation).
    """

    def __init__(self, pin, vref=3.3):
        """
        Args:
            pin: ADC-capable GPIO.
            vref: ADC reference (V), used only where `read_uv()` isn't available (Pico).
        """
        import machine
        self._adc = machine.ADC(machine.Pin(pin))
        if hasattr(self._adc, "atten") and hasattr(machine.ADC, "ATTN_11DB"):
            self._adc.atten(machine.ADC.ATTN_11DB)     # ESP32: 0-~3.1 V range
        self._uv = hasattr(self._adc, "read_uv")
        self.vref = vref

    def read_voltage(self):
        """Take one sample.

        Returns:
            The ISENSE voltage (V).

        Raises:
            SensorError: The ADC read failed.
        """
        try:
            if self._uv:
                return self._adc.read_uv() / 1000000
            return self._adc.read_u16() * self.vref / 65535
        except OSError as exc:
            raise SensorError("ADC read failed: %s" % exc)


class MockSensor:
    """Mock current sensor for tests.

    Attributes:
        amps (float): Current at the ISENSE pin (A): the duty-weighted average.
        fail (bool): Set `True` to make reads raise `SensorError`.
    """

    def __init__(self, amps=0.0):
        """
        Args:
            amps: Initial ISENSE current (A).
        """
        self.amps = amps
        self.fail = False

    def read_voltage(self):
        """Return `amps × 0.675`.

        Returns:
            The simulated ISENSE voltage (V).

        Raises:
            SensorError: `fail` is set.
        """
        if self.fail:
            raise SensorError("mock sensor failure")
        return self.amps * ISENSE_V_PER_A


class MotorCurrentSensor:
    """Converts ISENSE readings to amps, averaging several samples."""

    def __init__(self, source, samples=4, v_per_a=ISENSE_V_PER_A):
        """
        Args:
            source: Any object with `read_voltage()` (`ADS1115Channel`, `ADCChannel`, `MockSensor`).
            samples: Samples averaged per reading.
            v_per_a: ISENSE gain (V/A): 0.675 on Board A.
        """
        self.source = source
        self.samples = samples if samples > 0 else 1
        self.v_per_a = v_per_a

    def read_isense_amps(self):
        """Return the average ISENSE current: the supply-side current for this motor.

        Returns:
            Amps, never negative.

        Raises:
            SensorError: A sample failed.
        """
        total = 0.0
        for _ in range(self.samples):
            total += self.source.read_voltage()
        a = total / self.samples / self.v_per_a
        return a if a > 0 else 0.0

# ---------------------------------------------------------------- motor


def _check_speed(v):
    """Validate a speed.

    Args:
        v: Speed (%).

    Returns:
        The speed as a float.

    Raises:
        ValueError: Outside 0–100.
    """
    v = float(v)
    if v < 0 or v > 100:
        raise ValueError("speed_pc must be 0-100, got %s" % v)
    return v


class Motor:
    """One motor channel. Create motors through `MotorBoard`, not directly.

    Pass options to both motors with `motor_options=`, or to one with `a_options=` /
    `b_options=`. Speeds are percentages, 0–100; `run()` takes a signed speed.
    """

    def __init__(self, name, board, en_pin, ph_pin, mode, pins, sensor=None, invert=False,
                 pwm_freq=20000, min_speed_pc=0, ramp_time=0.0, reverse_delay=0.1,
                 stall_current=None, stall_time=0.5, start_grace=0.3, open_load_current=0.03,
                 open_load_time=1.0, continuous_current=1.5, overload_time=5.0, policy=None):
        """
        Args:
            name: Motor name within its board.
            board: The owning `MotorBoard`.
            en_pin: GPIO for EN (PH/EN mode) or IN1 (PWM mode).
            ph_pin: GPIO for PH (PH/EN mode) or IN2 (PWM mode).
            mode: The board's `ControlMode` constant.
            pins: The `PinFactory`.
            sensor: Optional `MotorCurrentSensor`.
            invert: Swap forward and reverse.
            pwm_freq: PWM frequency (Hz).
            min_speed_pc: Non-zero speeds below this are raised to it. 0 disables.
            ramp_time: Seconds to ramp from 0 to 100 %. 0 = instant. Ramps advance in `update()`.
            reverse_delay: Seconds of braking before a direction change while running.
            stall_current: Motor current (A) treated as a stall. Default: 80 % of the board limit.
            stall_time: Seconds the stall condition must last.
            start_grace: Seconds after a start or speed change during which stall and open-load
                checks are skipped.
            open_load_current: Current (A) below which a driven motor counts as disconnected.
            open_load_time: Seconds the open-load condition must last.
            continuous_current: Current (A) the motor may carry continuously.
            overload_time: Seconds above `continuous_current` before an overload fault.
            policy: `FaultPolicy` for this motor.

        Raises:
            ConfigError: An option is out of range.
        """
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
        """The name including the board, for example `"front.a"`."""
        return "%s.%s" % (self.board.name, self.name)

    @property
    def state(self):
        """The current `MotorState` constant."""
        return self._state

    @property
    def direction(self):
        """Direction of the last run command, kept after a stop for `start()`. `None` if never run."""
        return self._direction

    @property
    def is_running(self):
        """`True` while the motor is driven."""
        return self._state == MotorState.RUNNING

    @property
    def duty(self):
        """PWM duty currently applied, 0–1."""
        return self._duty

    @property
    def running_since(self):
        """`ticks_ms()` of the last start or speed change."""
        return self._since

    @property
    def fault(self):
        """The latched `Fault`, or `None`."""
        return self._fault

    @property
    def has_sensor(self):
        """`True` if the motor has a current sensor."""
        return self.sensor is not None

    @property
    def busy(self):
        """`True` while a timed run or a ramp is still in progress (both advance in `update()`)."""
        return self._stop_at is not None or self._ramp is not None

    @property
    def speed_pc(self):
        """Commanded speed, 0–100 %.

        Setting it while running changes the speed (ramped if `ramp_time` is set); 0 stops.
        While stopped it stores the speed for `start()`.

        Raises:
            ValueError: Outside 0–100.
        """
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
        """Motor current (A), read now and corrected for PWM duty, or `None` without a sensor."""
        return self.read_current() if self.sensor is not None else None

    # ---- commands
    def forward(self, speed_pc=100, duration=None, wait=False):
        """Run forward.

        Args:
            speed_pc: Speed, 0–100 %. 0 stops the motor.
            duration: Seconds to run before braking, or `None` to run until told otherwise.
                The stop happens inside `update()`.
            wait: With `duration`, block until the run ends (calls `update()` while waiting).

        Raises:
            ValueError: Speed outside 0–100, or `duration` not positive.
            MotorFaultError: The motor has a latched fault.
        """
        self._run(Direction.FORWARD, speed_pc, duration, wait)

    def reverse(self, speed_pc=100, duration=None, wait=False):
        """Run in reverse.

        Args:
            speed_pc: Speed, 0–100 %. 0 stops the motor.
            duration: Seconds to run before braking, or `None` to run until told otherwise.
                The stop happens inside `update()`.
            wait: With `duration`, block until the run ends (calls `update()` while waiting).

        Raises:
            ValueError: Speed outside 0–100, or `duration` not positive.
            MotorFaultError: The motor has a latched fault.
        """
        self._run(Direction.REVERSE, speed_pc, duration, wait)

    def run(self, speed_pc, duration=None, wait=False):
        """Run with a signed speed.

        Args:
            speed_pc: -100 to 100. Positive is forward, negative is reverse, 0 stops.
            duration: Seconds to run before braking, or `None`.
            wait: With `duration`, block until the run ends.

        Raises:
            ValueError: Speed out of range, or `duration` not positive.
            MotorFaultError: The motor has a latched fault.
        """
        if speed_pc == 0:
            self.stop()
        else:
            self._run(Direction.FORWARD if speed_pc > 0 else Direction.REVERSE,
                      abs(speed_pc), duration, wait)

    def start(self, duration=None, wait=False):
        """Resume the last direction and speed (forward at 100 % if never run).

        Args:
            duration: Seconds to run before braking, or `None`.
            wait: With `duration`, block until the run ends.

        Raises:
            MotorFaultError: The motor has a latched fault.
        """
        self._run(self._direction or Direction.FORWARD, self._speed_pc or 100, duration, wait)

    def stop(self):
        """Brake (both outputs low): stops quickly. Cancels any timed run or ramp. `brake()` is an alias."""
        self._stop_at = None
        self._ramp = None
        self._apply_brake()
        if self._state != MotorState.FAULT:
            self._state = MotorState.STOPPED

    brake = stop
    """Alias of `stop()`."""

    def coast(self):
        """Let the motor spin down freely.

        In PWM mode this is per motor. In PH/EN mode it sleeps the nSLEEP line, so it happens
        only when every other motor on that line is idle; otherwise the motor brakes.

        Returns:
            `True` if coasting, `False` if it had to brake instead.
        """
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
        """Block until a timed run or ramp finishes, calling `update()` on the board (or its chain) meanwhile.

        Args:
            timeout: Maximum seconds, or `None`.

        Returns:
            `False` if the timeout expired first.
        """
        t0 = ticks_ms()
        owner = self.board._owner()
        while self.busy:
            owner.update()
            if timeout is not None and ticks_diff(ticks_ms(), t0) >= timeout * 1000:
                return False
            sleep_ms(5)
        return True

    def read_current(self):
        """Read the sensor now and return the estimated motor current.

        Updates `last_current` and `last_isense_amps`. Below 10 % duty the raw reading is returned.

        Returns:
            Motor current (A).

        Raises:
            ConfigError: No sensor.
            SensorError: The reading failed.
        """
        if self.sensor is None:
            raise ConfigError("%s has no current sensor" % self.full_name)
        isense = self.sensor.read_isense_amps()
        amps = isense / self._duty if self._duty >= 0.1 else isense
        self.last_isense_amps = isense
        self.last_current = amps
        return amps

    def add_fault_handler(self, handler):
        """Call `handler(fault)` whenever a fault is reported for this motor.

        Handlers run inside `update()`. Exceptions are printed and ignored.

        Args:
            handler: A callable taking one `Fault`.
        """
        self._handlers.append(handler)

    def clear_fault(self):
        """Clear a latched fault so the motor can run again. It stays stopped."""
        self._fault = None
        if self._state == MotorState.FAULT:
            self._state = MotorState.STOPPED

    def close(self):
        """Brake and release the motor's pins."""
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
            self._ph.set(fwd)                   # forward = PH high (OUT1 positive)
            self._en.set_duty(duty)
        elif fwd:                               # PWM mode, slow decay: IN1 = 1, IN2 = 1-duty
            self._en.set_duty(1.0)
            self._ph.set_duty(1.0 - duty)
        else:
            self._ph.set_duty(1.0)
            self._en.set_duty(1.0 - duty)

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
_fault_users = {}


class MotorBoard:
    """One Board A dual DC motor driver. Pins are GPIO numbers.

    Several boards can share one `sleep_pin` (one e-stop line). Each board needs its
    **own** `fault_pin`: a `fault_pin` already used by another open board is rejected.

    Example:
        ```python
        board = MotorBoard(a_en=25, a_ph=26, b_en=27, b_ph=33, sleep_pin=32, fault_pin=39,
                           a_sensor=ADCChannel(34), b_sensor=ADCChannel(35))
        board.enable_monitor(on_fault=print)
        board.motor_a.forward(60)
        board.pause(2)
        board.stop_all()
        ```
    """

    def __init__(self, name="board", a_en=None, a_ph=None, b_en=None, b_ph=None,
                 sleep_pin=None, fault_pin=None, mode="ph_en", logic_voltage=3.3,
                 adc=None, a_sense_channel=None, b_sense_channel=None,
                 a_sensor=None, b_sensor=None, sense_samples=None, pins=None,
                 pwm_freq=20000, motor_names=("a", "b"), motor_options=None,
                 a_options=None, b_options=None, fuse_rating=3.0):
        """
        Args:
            name: Board name, used in `"board.motor"` addresses. Must not contain `.`.
            a_en: GPIO for A_EN (J3 pin 3).
            a_ph: GPIO for A_PH (J3 pin 4).
            b_en: GPIO for B_EN (J3 pin 5), or `None` for a single motor.
            b_ph: GPIO for B_PH (J3 pin 6), or `None`.
            sleep_pin: GPIO for nSLEEP (J3 pin 9), or `None`. The board pulls nSLEEP high, so the
                drivers are awake without it. Several boards may share it.
            fault_pin: GPIO for nFAULT (J3 pin 10), or `None`. Needed for stall detection without a
                sensor. Must be a different GPIO for each board.
            mode: `"ph_en"` (JP1 pads 1–2, default) or `"pwm"` (JP1 pads 2–3).
            logic_voltage: VLOGIC (V), 3.0–5.5. Checked for range only: the current limit is fixed
                at about 3 A.
            adc: An `ADS1115` for current sensing.
            a_sense_channel: ADS1115 input wired to A_ISENSE.
            b_sense_channel: ADS1115 input wired to B_ISENSE.
            a_sensor: Any sensor with `read_voltage()` for motor A, such as `ADCChannel(34)`.
            b_sensor: The same for motor B.
            sense_samples: Samples per reading. Default: 16 for `ADCChannel`, otherwise 4.
            pins: `PinFactory`. Default: `MachinePins()`.
            pwm_freq: PWM frequency (Hz). Default 20 kHz.
            motor_names: Names for motors A and B.
            motor_options: Keyword arguments for both `Motor`s.
            a_options: Keyword arguments for motor A only.
            b_options: Keyword arguments for motor B only.
            fuse_rating: Board fuse hold current (A), for `BOARD_OVERLOAD`.

        Raises:
            ConfigError: Invalid mode, voltage, names or pins, or a `fault_pin` already used by
                another open board.
        """
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
        pins = pins or MachinePins()
        if fault_pin is not None and (id(pins), fault_pin) in _fault_users:
            raise ConfigError("fault_pin %s is already used by board '%s': give each board its own "
                              "nFAULT line" % (fault_pin, _fault_users[(id(pins), fault_pin)].name))
        self.name = name
        self.mode = mode
        self.logic_voltage = logic_voltage
        self.fuse_rating = fuse_rating
        self.pins = pins
        self._sleep_pin = sleep_pin
        self._fault_pin = fault_pin
        self._sleep = self.pins.output(sleep_pin, True) if sleep_pin is not None else None
        self._fault = self.pins.input(fault_pin) if fault_pin is not None else None
        if sleep_pin is not None:
            _sleep_groups.setdefault((id(self.pins), sleep_pin), []).append(self)
        if fault_pin is not None:
            _fault_users[(id(self.pins), fault_pin)] = self
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
        """Driver current limit per motor (A): about 3 A, fixed on the board (VREF ≈ 2.07 V / 0.675 V/A)."""
        return VREF_V / ISENSE_V_PER_A

    @property
    def motor_a(self):
        """The first `Motor` (J4)."""
        return self.motors[self._order[0]]

    @property
    def motor_b(self):
        """The second `Motor` (J5), or `None`."""
        return self.motors[self._order[1]] if len(self._order) > 1 else None

    @property
    def is_asleep(self):
        """`True` while nSLEEP is driven low."""
        return self._sleep is not None and not self._sleep.get()

    @property
    def fault_active(self):
        """`True` while nFAULT is low; `None` if `fault_pin` isn't wired."""
        return None if self._fault is None else (not self._fault.read())

    @property
    def total_current(self):
        """Sum of the motors' last supply-side readings (A), or `None` unless every motor has been read."""
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
        """Stop every motor on this nSLEEP line, then pull nSLEEP low (motors coast).

        Raises:
            ConfigError: No `sleep_pin`.
        """
        if self._sleep is None:
            raise ConfigError("%s: no sleep_pin configured" % self.name)
        for b in self._sleep_group():
            for m in b.motors.values():
                m.stop()
        self._sleep.set(False)

    def wake(self):
        """Drive nSLEEP high and wait 2 ms. Run commands wake the board automatically."""
        if self._sleep is not None and not self._sleep.get():
            self._sleep.set(True)
            sleep_ms(WAKE_MS)

    def stop_all(self):
        """Brake every motor on this board."""
        for m in self.motors.values():
            m.stop()

    def coast_all(self):
        """Coast every motor (sleeps the board in PH/EN mode; brakes without a sleep pin)."""
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
        """Turn on fault checking inside `update()`.

        Args:
            interval: Minimum seconds between fault checks.
            on_fault: Optional `handler(fault)`.

        Returns:
            The `FaultMonitor`.
        """
        if self.monitor is None:
            self.monitor = FaultMonitor([self], interval)
        if on_fault:
            self.monitor.add_fault_handler(on_fault)
        return self.monitor

    def update(self):
        """Advance ramps and timed runs, and run fault checks if enabled. Call every 10–50 ms."""
        now = ticks_ms()
        for m in self.motors.values():
            m._tick(now)
        if self.monitor is not None:
            self.monitor.poll(now)

    def pause(self, seconds):
        """Blocking sleep that keeps calling `update()`.

        Args:
            seconds: How long to pause.
        """
        _pause(self, seconds)

    async def run_monitor(self, interval=0.02):
        """Coroutine that calls `update()` forever. Run it as an asyncio task.

        Enables the fault monitor if it isn't already.

        Args:
            interval: Seconds between updates.

        Example:
            ```python
            asyncio.create_task(board.run_monitor())
            ```
        """
        if self.monitor is None:
            self.enable_monitor()
        while True:
            self.update()
            await asyncio.sleep(interval)

    def close(self):
        """Brake every motor and release every pin."""
        for m in self.motors.values():
            m.close()
        if self._sleep_pin is not None:
            grp = _sleep_groups.get((id(self.pins), self._sleep_pin), [])
            if self in grp:
                grp.remove(self)
        if _fault_users.get((id(self.pins), self._fault_pin)) is self:
            del _fault_users[(id(self.pins), self._fault_pin)]
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
    """Blocking pause that keeps calling `owner.update()`.

    Args:
        owner: A `MotorBoard` or `MotorChain`.
        seconds: How long to pause.
    """
    t0 = ticks_ms()
    ms = int(seconds * 1000)
    while ticks_diff(ticks_ms(), t0) < ms:
        owner.update()
        sleep_ms(5)

# ---------------------------------------------------------------- chain


class MotorChain:
    """Several daisy-chained boards as one system, with one fault monitor.

    Motors are addressed as `"board.motor"` or by an alias. `chain[name]` looks one up.
    """

    def __init__(self, boards=(), chain_current_limit=6.0, monitor=True, interval=0.05):
        """
        Args:
            boards: Boards to add. Names must be unique.
            chain_current_limit: Total supply current allowed through the chain (A).
            monitor: Create the chain's fault monitor.
            interval: Minimum seconds between fault checks.

        Raises:
            ConfigError: Duplicate board names.
        """
        self.boards = {}
        self._aliases = {}
        self.chain_current_limit = chain_current_limit
        self.monitor = FaultMonitor([], interval, chain_current_limit) if monitor else None
        for b in boards:
            self.add_board(b)

    def add_board(self, board):
        """Add a board. Its own monitor is replaced by the chain's.

        Args:
            board: The `MotorBoard`.

        Returns:
            The board.

        Raises:
            ConfigError: Duplicate board name.
        """
        if board.name in self.boards:
            raise ConfigError("duplicate board name '%s'" % board.name)
        board.monitor = None          # the chain monitor takes over
        board._chain = self
        self.boards[board.name] = board
        if self.monitor is not None:
            self.monitor.boards.append(board)
        return board

    def alias(self, alias, target):
        """Give a motor a friendly name.

        Args:
            alias: The new name (no `.`).
            target: `"board.motor"` or an existing alias.

        Returns:
            The `Motor`.

        Raises:
            ConfigError: The alias contains `.`.
            KeyError: No such motor.
        """
        if "." in alias:
            raise ConfigError("aliases must not contain '.'")
        m = self.motor(target)
        self._aliases[alias] = m
        return m

    def motor(self, name):
        """Look up a motor by alias or `"board.motor"`.

        Args:
            name: The alias or address.

        Returns:
            The `Motor`.

        Raises:
            KeyError: No such motor.
        """
        if name in self._aliases:
            return self._aliases[name]
        parts = name.split(".", 1)
        try:
            return self.boards[parts[0]].motors[parts[1]]
        except (KeyError, IndexError):
            raise KeyError("no motor '%s' (use 'board.motor' or an alias)" % name)

    __getitem__ = motor
    """`chain[name]` is the same as `chain.motor(name)`."""

    @property
    def motors(self):
        """Every motor on every board."""
        out = []
        for b in self.boards.values():
            out.extend(list(b))
        return out

    def __iter__(self):
        return iter(self.motors)

    @property
    def faults(self):
        """Fault history, oldest first (up to 50)."""
        return list(self.monitor.faults) if self.monitor else []

    @property
    def active_faults(self):
        """Latched faults currently blocking motors."""
        return [m.fault for m in self.motors if m.fault is not None]

    @property
    def total_current(self):
        """Total supply-side current (A) from the last readings, or `None`."""
        vals = [b.total_current for b in self.boards.values()]
        if not vals or None in vals:
            return None
        return sum(vals)

    def add_fault_handler(self, handler):
        """Call `handler(fault)` for every fault on any board.

        Args:
            handler: A callable taking one `Fault`.

        Raises:
            ConfigError: The chain was created with `monitor=False`.
        """
        if self.monitor is None:
            raise ConfigError("chain was created with monitor=False")
        self.monitor.add_fault_handler(handler)

    def stop_all(self):
        """Brake every motor."""
        for m in self.motors:
            m.stop()

    def coast_all(self):
        """Coast every motor."""
        for b in self.boards.values():
            b.coast_all()

    def emergency_stop(self):
        """Brake every motor, then sleep every board with a sleep pin."""
        self.stop_all()
        for b in self.boards.values():
            if b._sleep is not None:
                b.sleep()

    def clear_faults(self):
        """Clear the latched fault on every motor."""
        for m in self.motors:
            m.clear_fault()

    def update(self):
        """Advance every motor's ramps and timed runs, and run fault checks. Call every 10–50 ms."""
        now = ticks_ms()
        for m in self.motors:
            m._tick(now)
        if self.monitor is not None:
            self.monitor.poll(now)

    def check_faults(self):
        """Run one fault check now, ignoring the interval.

        Returns:
            The faults found.
        """
        return self.monitor.check_once() if self.monitor else []

    def pause(self, seconds):
        """Blocking sleep that keeps calling `update()`.

        Args:
            seconds: How long to pause.
        """
        _pause(self, seconds)

    async def run_monitor(self, interval=0.02):
        """Coroutine that calls `update()` forever. Run it as an asyncio task.

        Args:
            interval: Seconds between updates.
        """
        while True:
            self.update()
            await asyncio.sleep(interval)

    def close(self):
        """Close every board."""
        for b in self.boards.values():
            b.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

# ---------------------------------------------------------------- fault monitor

DRIVER_FAULT_DEBOUNCE_MS = 200
"""Milliseconds nFAULT must stay low, with no motor driven, before `DRIVER_FAULT`."""
OVERLOAD_DEBOUNCE_MS = 1000
"""Milliseconds over the limit before `BOARD_OVERLOAD` / `CHAIN_OVERLOAD`."""
CURRENT_LIMIT_REPEAT_MS = 5000
"""Minimum milliseconds between repeated `CURRENT_LIMIT` warnings."""
OPEN_LOAD_MIN_DUTY = 0.2
"""Open-load checks run only at or above this duty (0–1)."""


class _Track:
    def __init__(self):
        self.stall = None
        self.open = None
        self.over = None
        self.limit = None
        self.sensor_failed = False


class FaultMonitor:
    """Detects every `FaultType`. Runs inside `update()`; you rarely create one yourself.

    Without a current sensor, a stall is inferred from nFAULT staying low for `stall_time`.
    If both motors on a board are running, both are stopped.

    Attributes:
        faults (list): Fault history, oldest first.
        max_history (int): History length (default 50).
    """

    def __init__(self, boards, interval=0.05, chain_current_limit=None, clock=None):
        """
        Args:
            boards: Boards to watch.
            interval: Minimum seconds between checks in `poll()`.
            chain_current_limit: Amps for `CHAIN_OVERLOAD`, or `None` to disable.
            clock: Function returning milliseconds (for tests). Default `ticks_ms`.
        """
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
        """Call `handler(fault)` for every fault detected.

        Args:
            handler: A callable taking one `Fault`.
        """
        self._handlers.append(handler)

    def poll(self, now=None):
        """Run `check_once()` if at least `interval` has passed since the last check.

        Args:
            now: Current `ticks_ms()`, or `None` to read the clock.

        Returns:
            The faults found, or an empty list if it wasn't time to check.
        """
        now = self.clock() if now is None else now
        if self._last is None or ticks_diff(now, self._last) >= self.interval_ms:
            self._last = now
            return self.check_once(now)
        return []

    def check_once(self, now=None):
        """Check every board once.

        Args:
            now: Current `ticks_ms()`, or `None` to read the clock.

        Returns:
            The faults found in this pass.
        """
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
