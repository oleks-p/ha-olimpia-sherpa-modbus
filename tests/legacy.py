"""What the legacy YAML templates computed, and a replay over recorded history.

Each function mirrors a Jinja template from the reference site's
``packages/sherpa.yaml`` / ``packages/plant.yaml`` (transcribed verbatim into
``fixtures/legacy_entities.json``). Jinja's ``| int(d)`` is ``to_int(value, d)``.
The integration's decoders must agree with these wherever they replace a legacy
entity, or dashboards, automations and long-term statistics change meaning at
the cutover.
"""
from __future__ import annotations

import bisect
import json
import pathlib
from collections.abc import Callable

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SENTINELS = ("unknown", "unavailable")


def to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def mode(status) -> str:
    # DHW bits first: the machine also sets heating (DHW) or cooling (legionella).
    s = to_int(status)
    if s & 4:
        return "domestic hot water"
    if s & 8:
        return "anti-legionella"
    if s & 1:
        return "cooling"
    if s & 2:
        return "heating"
    return "standby"


# sensor.sherpa_mode moves from free text to an enum sensor with translated
# states (decided 2026-10-13). Keys are snake_case throughout, HA's convention,
# so the two values with spaces or a hyphen change; the rest carry over.
MODE_KEYS = {
    "standby": "standby",
    "cooling": "cooling",
    "heating": "heating",
    "domestic hot water": "domestic_hot_water",
    "anti-legionella": "anti_legionella",
}


def error_code(alarm_1, alarm_2) -> str:
    a1, a2 = to_int(alarm_1), to_int(alarm_2)
    found = [f"E{i + 1:02d}" for i in range(9) if a1 >> i & 1]
    found += [f"E{20 + i}" for i in range(8) if a2 >> i & 1]
    return ", ".join(found) if found else "none"


def on_off(flag: bool) -> str:
    return "on" if flag else "off"


# legacy entity -> (decoder, the entities it reads)
TEMPLATES: dict[str, tuple[Callable[..., str], tuple[str, ...]]] = {
    "sensor.sherpa_mode": (mode, ("sensor.sherpa_status",)),
    "sensor.sherpa_error_code": (error_code, ("sensor.sherpa_alarm_1", "sensor.sherpa_alarm_2")),
    "binary_sensor.sherpa_mode_pending": (
        lambda s: on_off(to_int(s) & 96 == 96), ("sensor.sherpa_status",)),
    "binary_sensor.sherpa_mode_dhw": (
        lambda s: on_off(to_int(s) & 12 > 0), ("sensor.sherpa_status",)),
    "binary_sensor.sherpa_power": (
        lambda s, o: on_off(to_int(s) > 0 or to_int(o) & 1 > 0),
        ("sensor.sherpa_status", "sensor.sherpa_outputs")),
    "binary_sensor.sherpa_error": (
        lambda a1, a2: on_off(to_int(a1) > 0 or to_int(a2) > 0),
        ("sensor.sherpa_alarm_1", "sensor.sherpa_alarm_2")),
    "binary_sensor.sherpa_warning": (
        lambda o: on_off(to_int(o) > 0), ("sensor.sherpa_override",)),
    "binary_sensor.sherpa_defrost": (
        lambda o: on_off(to_int(o) & 32 > 0), ("sensor.sherpa_override",)),
}


def load_history(site: str = "uahs01") -> dict[str, list[list]]:
    return json.loads((FIXTURES / f"history_{site}.json").read_text())["entities"]


def load_legacy() -> dict:
    return json.loads((FIXTURES / "legacy_entities.json").read_text())


class StepSeries:
    """A recorded state that holds until the next record."""

    def __init__(self, rows: list[list]):
        self.times = [row[0] for row in rows]
        self.states = [row[1] for row in rows]

    def at(self, t: float):
        i = bisect.bisect_right(self.times, t)
        return self.states[i - 1] if i else None


def replay(history: dict[str, list[list]], target: str, decoder: Callable[..., str],
           inputs: tuple[str, ...], settle_s: float = 0.5):
    """Yield (t, inputs, recorded, decoded) for every recorded state of ``target``.

    Inputs are sampled ``settle_s`` after the target changed. A template
    re-renders a few milliseconds after its source, so the source's new value
    is in place by then. Records where anything is unavailable are skipped.
    """
    sources = [StepSeries(history[name]) for name in inputs]
    for t, recorded in history[target]:
        if recorded in SENTINELS:
            continue
        args = [source.at(t + settle_s) for source in sources]
        if any(a is None or a in SENTINELS for a in args):
            continue
        yield t, args, recorded, decoder(*args)
