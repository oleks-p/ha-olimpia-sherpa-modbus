"""Values computed from the raw words: mode, fault codes, pump duty, runtime.

Pure functions, no Home Assistant. They replace the YAML templates of a modbus
setup and give the same answers, except the mode states, which are
translation keys.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from .registers import MODE_COMMAND_BITS

#: sensor.<prefix>_mode states. Translated in strings.json; the YAML templates'
#: free-text states map onto these one-to-one ("domestic hot water" ->
#: domestic_hot_water, "anti-legionella" -> anti_legionella).
MODE_OPTIONS: tuple[str, ...] = (
    "standby", "cooling", "heating", "domestic_hot_water", "anti_legionella",
)


def mode(status: int | None) -> str | None:
    """What the unit is doing, from status register 12.

    The DHW bits are tested first. During a DHW cycle the machine also sets the
    heating bit, because the circuit reverses into heating to make hot water;
    during legionella it leaves the cooling bit set, because that cycle never
    leaves cooling -- only EH1 fires. Tested in the other order, every DHW cycle
    would read as plain heating or cooling. The pending pattern (bits 5+6) is
    not a mode of its own: 97 is cooling, pending.
    """
    if status is None:
        return None
    if status & 0x04:
        return "domestic_hot_water"
    if status & 0x08:
        return "anti_legionella"
    if status & 0x01:
        return "cooling"
    if status & 0x02:
        return "heating"
    return "standby"


def bit(word: int | None, n: int) -> bool | None:
    return None if word is None else bool(word >> n & 1)


def inverted_bit(word: int | None, n: int) -> bool | None:
    """Register 8 is active-low: a 0 bit means the input is active."""
    return None if word is None else not word >> n & 1


def masked(word: int | None, mask: int, how: str) -> bool | None:
    if word is None:
        return None
    return (word & mask) == mask if how == "all" else bool(word & mask)


def active_codes(word: int | None, codes: Sequence[str]) -> list[str] | None:
    """Bit n of ``word`` set -> ``codes[n]``."""
    if word is None:
        return None
    return [code for n, code in enumerate(codes) if word >> n & 1]


def codes_text(*groups: list[str] | None) -> str | None:
    """'none', or the active codes joined -- the legacy error_code format."""
    if any(group is None for group in groups):
        return None
    found = [code for group in groups for code in group or []]
    return ", ".join(found) if found else "none"


def any_set(*words: int | None) -> bool | None:
    if any(word is None for word in words):
        return None
    return any(words)


def power(status: int | None, outputs: int | None) -> bool | None:
    """On when the unit reports any state, or the circulation pump runs."""
    if status is None and outputs is None:
        return None
    return bool(status) or bool((outputs or 0) & 1)


def pump_duty(step: int | None, table: Sequence[int | None]) -> int | None:
    """PWM duty for the current pump speed step (1 = 5 % = maximum speed).

    Unknown rather than 0 when the step is unknown: the legacy template
    reported 0 whenever the step register was unavailable, which wrote a false
    "pump off" into the statistics.
    """
    if step is None or not 1 <= step <= len(table):
        return None
    return table[step - 1]


def hours(seconds: int | None) -> float | None:
    return None if seconds is None else round(seconds / 3600, 2)


def water_delta(water_out: float | None, water_in: float | None) -> float | None:
    """Delivery minus return. Unknown if either probe is: the legacy template
    substituted 0 for a missing probe and charted the other one as the delta."""
    if water_out is None or water_in is None:
        return None
    return round(water_out - water_in, 1)


#: What the panel's modes menu has selected, as far as Modbus can tell (P5,
#: docs/p5_mode_research.md). ECO and "DHW disabled" are not visible at all.
SELECTED_OPTIONS: tuple[str, ...] = ("off", "heating", "cooling")


def selected_mode(status: int | None, last: str | None) -> str | None:
    """Heating, cooling or off as selected on the panel, from status register 12.

    Outside a DHW or legionella cycle, bit 1 is heating selected and bit 0
    cooling selected, while the compressor runs and while it idles; 0 is
    standby. Inside a cycle the bits describe the cycle instead (a DHW cycle
    sets the heating bit whatever is selected, see mode()), so the selection
    seen before the cycle stands. Only with none to keep -- straight out of
    standby, or after a restart mid-cycle -- are the bits taken as they are.
    """
    if status is None:
        return None
    if status & 0x0C and last in ("heating", "cooling"):
        return last
    if status & 0x02:
        return "heating"
    if status & 0x01:
        return "cooling"
    return "off"


# -- the mode command, register 106 (Olimpia RDE448) ------------------------------

_BIT = {name: 1 << bit for bit, name in MODE_COMMAND_BITS.items()}
#: What 106 can hold besides standby: DHW only is heating and cooling both clear.
COMMAND_MODES: tuple[str, ...] = ("dhw_only", "heating", "cooling")
#: The select's options: standby is a flag of its own (STB), kept beside the mode.
OPERATING_MODES: tuple[str, ...] = ("standby", *COMMAND_MODES)


def commanded_mode(word: int | None) -> str | None:
    """standby | dhw_only | heating | cooling, from 106. The standby bit wins:
    the unit is in standby whatever the other bits say."""
    if word is None:
        return None
    if word & _BIT["standby"]:
        return "standby"
    return command_mode(word)


def command_mode(word: int) -> str:
    """The mode bits alone, standby ignored: dhw_only | heating | cooling."""
    if word & _BIT["heating"]:
        return "heating"
    return "cooling" if word & _BIT["cooling"] else "dhw_only"


def command_word(mode: str, *, standby: bool = False, eco: bool = False,
                 night: bool = False) -> int:
    """106 for a mode (dhw_only | heating | cooling), plus the standby, ECO and
    night bits. Heating and cooling are never both set. Standby keeps the mode
    bit, so leaving it restores the mode."""
    word = 0 if mode == "dhw_only" else _BIT[mode]
    return (word | _BIT["standby"] * standby | _BIT["eco"] * eco | _BIT["night"] * night)


def word_valid(word: int) -> bool:
    """A word 106 may be given: only the documented bits, and never heating and
    cooling together (the unit's own rule, and nothing here ever builds one)."""
    both = _BIT["heating"] | _BIT["cooling"]
    return 0 <= word < 1 << len(MODE_COMMAND_BITS) and word & both != both


def selected_from_command(word: int | None) -> str | None:
    """off | heating | cooling, as the climate shows it: off when standby is set
    or neither heating nor cooling is (DHW only)."""
    mode = commanded_mode(word)
    return None if mode is None else mode if mode in ("heating", "cooling") else "off"


def hot_water_on(status: int | None, word: int | None, serial: bool) -> bool | None:
    """Is the unit out of standby, i.e. may it make hot water?

    With ADDR220 = 1, 106 says: the standby bit. Otherwise only the panel knows,
    and the status word shows it for one case: heating, cooling or a DHW cycle
    running means not in standby. Status 0 is standby and DHW only alike
    (P6, docs/p6_mode_command_test.md), so it reads unknown, not off.
    """
    if serial and word is not None:
        return not word & _BIT["standby"]
    if status is not None and status & 0x0F:
        return True
    return None


def curve(outdoor: float | None, outdoor_at_max: float | None, max_water: float | None,
          outdoor_at_min: float | None, min_water: float | None) -> float | None:
    """A climatic curve's water temperature at this outdoor temperature.

    The manual defines a curve by two points -- the outdoor temperature for the
    maximum water temperature, and for the minimum -- and the water follows the
    straight line between them, held at the end values beyond them.
    """
    points = (outdoor, outdoor_at_max, max_water, outdoor_at_min, min_water)
    if any(v is None for v in points) or outdoor_at_max == outdoor_at_min:
        return None
    lo, hi = sorted(((outdoor_at_max, max_water), (outdoor_at_min, min_water)))
    if outdoor <= lo[0]:
        return lo[1]
    if outdoor >= hi[0]:
        return hi[1]
    return round(lo[1] + (outdoor - lo[0]) * (hi[1] - lo[1]) / (hi[0] - lo[0]), 1)


def water_target(selected: str | None, values: dict) -> tuple[float | None, str | None]:
    """The water temperature the unit aims for, calculated -- the unit does not
    report it. The curve when it is on, else the fixed setpoint.

    Not included, because Modbus cannot see them: ECO (while the curves are
    off, ECO would switch to the ECO setpoint) and whatever ADDR369 "water
    setpoint correction" adds; both read as unknown rather than guessed.
    """
    if selected not in ("heating", "cooling"):
        return None, None
    if values.get(f"{selected}_curve_enabled"):
        return curve(values.get("outdoor_air"),
                     values.get(f"{selected}_curve_max_water_outdoor"),
                     values.get(f"{selected}_curve_max_water"),
                     values.get(f"{selected}_curve_min_water_outdoor"),
                     values.get(f"{selected}_curve_min_water")), f"{selected}_curve"
    return values.get(f"{selected}_setpoint"), f"{selected}_setpoint"


def clock_text(minutes: int | None) -> str | None:
    """Minutes since midnight -> 'HH:MM' (register 231, legionella start)."""
    if minutes is None:
        return None
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


class CompressorEstimator:
    """Is the compressor running? The unit has no bit that says so.

    The compressor counter (registers 270/271) advances one second per second
    while the compressor runs, and only then. So, as the legacy derivative
    sensor did: the counter's rate over a two-minute window, in seconds per
    minute, and "running" above 20. The status word is no substitute: in 57
    days of history ``0 < status < 96`` agreed with this in under half the
    samples -- status 1 mostly means "cooling selected, compressor idle".
    """

    WINDOW = 120.0
    THRESHOLD = 20.0

    def __init__(self) -> None:
        self._samples: deque[tuple[float, int]] = deque()

    def add(self, t: float, counter: int | None) -> None:
        """Record a fresh counter reading taken at monotonic time ``t``."""
        if counter is None:
            return
        if self._samples and counter < self._samples[-1][1]:
            self._samples.clear()  # the counter was reset from the panel
        self._samples.append((t, counter))
        while self._samples and self._samples[0][0] < t - self.WINDOW:
            self._samples.popleft()

    @property
    def rate(self) -> float | None:
        """Counter seconds per minute across the window; None until 2 samples."""
        if len(self._samples) < 2:
            return None
        (t0, v0), (t1, v1) = self._samples[0], self._samples[-1]
        if t1 <= t0:
            return None
        return float(round((v1 - v0) / (t1 - t0) * 60))

    @property
    def running(self) -> bool | None:
        rate = self.rate
        return None if rate is None else rate > self.THRESHOLD
