"""Values computed from the raw words: mode, fault codes, pump duty, runtime.

Pure functions, no Home Assistant. They replace the legacy YAML templates, and
tests/legacy.py keeps what those templates computed: the tests replay 57 days
of the reference site's recorded history through both and require the same
answers (the mode states aside, which were renamed to translation keys).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

#: sensor.<prefix>_mode states. Translated in strings.json; the legacy
#: free-text states map onto these one-to-one (tests/legacy.py::MODE_KEYS).
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
