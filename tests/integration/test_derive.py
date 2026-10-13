"""The derived values, replayed over 57 days of the reference site's history.

tests/legacy.py transcribes what the legacy YAML templates computed, and the
fixture tests prove those transcriptions reproduce every recorded state. Here
the integration's own decoders must agree with the recordings too: the cutover
must not change what any entity says, only where it comes from.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from custom_components.olimpia_sherpa_modbus import derive
from custom_components.olimpia_sherpa_modbus.registers import (
    ALARM_1_CODES,
    ALARM_2_CODES,
    DEFROST_BIT,
)
from tests import legacy

HISTORY = legacy.load_history()


def _int(value: str) -> int:
    return int(float(value))


def _on_off(flag: bool | None) -> str:
    return "on" if flag else "off"


def _error_code(a1: str, a2: str) -> str | None:
    return derive.codes_text(derive.active_codes(_int(a1), ALARM_1_CODES),
                             derive.active_codes(_int(a2), ALARM_2_CODES))


# legacy entity -> (the integration's decoder, rendered as the legacy state, inputs)
OURS: dict[str, tuple[Callable[..., str | None], tuple[str, ...]]] = {
    # Mode states were renamed to translation keys; MODE_KEYS maps old to new.
    "sensor.sherpa_mode": (lambda s: derive.mode(_int(s)), ("sensor.sherpa_status",)),
    "sensor.sherpa_error_code": (_error_code, ("sensor.sherpa_alarm_1", "sensor.sherpa_alarm_2")),
    "binary_sensor.sherpa_mode_pending": (
        lambda s: _on_off(derive.masked(_int(s), 0x60, "all")), ("sensor.sherpa_status",)),
    "binary_sensor.sherpa_mode_dhw": (
        lambda s: _on_off(derive.masked(_int(s), 0x0C, "any")), ("sensor.sherpa_status",)),
    "binary_sensor.sherpa_power": (
        lambda s, o: _on_off(derive.power(_int(s), _int(o))),
        ("sensor.sherpa_status", "sensor.sherpa_outputs")),
    "binary_sensor.sherpa_error": (
        lambda a1, a2: _on_off(derive.any_set(_int(a1), _int(a2))),
        ("sensor.sherpa_alarm_1", "sensor.sherpa_alarm_2")),
    "binary_sensor.sherpa_warning": (lambda o: _on_off(_int(o) > 0), ("sensor.sherpa_override",)),
    "binary_sensor.sherpa_defrost": (
        lambda o: _on_off(derive.bit(_int(o), DEFROST_BIT)), ("sensor.sherpa_override",)),
}


@pytest.mark.parametrize("target", sorted(OURS))
def test_decoders_reproduce_the_recorded_history(target):
    decoder, inputs = OURS[target]
    expected = legacy.MODE_KEYS if target == "sensor.sherpa_mode" else {}
    results = list(legacy.replay(HISTORY, target, decoder, inputs))
    mismatches = [(t, args, recorded, decoded) for t, args, recorded, decoded in results
                  if expected.get(recorded, recorded) != decoded]
    assert len(results) >= 10
    assert mismatches == []


def test_mode_covers_every_status_value_seen():
    for value in (0, 1, 6, 9, 96, 97, 98, 102):
        assert derive.mode(value) == legacy.MODE_KEYS[legacy.mode(value)]


def test_compressor_estimator_matches_the_legacy_sensor():
    """At least 99.5 % of one-minute samples over 57 days.

    The recorder keeps only changes, so the 60 s counter polls are synthesised by
    holding each recorded value; the legacy threshold sensor is read just after
    each poll, when it re-rendered.
    """
    counter = legacy.StepSeries(HISTORY["sensor.sherpa_compressor_seconds"])
    recorded = legacy.StepSeries(HISTORY["binary_sensor.sherpa_compressor_running"])
    rows = HISTORY["sensor.sherpa_compressor_seconds"]
    estimator = derive.CompressorEstimator()
    agree = total = 0
    t = rows[0][0]
    while t < rows[-1][0]:
        raw = counter.at(t)
        estimator.add(t, int(raw) if raw and raw.isdigit() else None)
        legacy_state, ours = recorded.at(t + 1), estimator.running
        if legacy_state in ("on", "off") and ours is not None:
            total += 1
            agree += ours == (legacy_state == "on")
        t += 60
    assert total > 70_000
    assert agree / total >= 0.995


def test_estimator_edges():
    estimator = derive.CompressorEstimator()
    assert estimator.running is None                 # nothing yet
    estimator.add(0, 1000)
    assert estimator.running is None                 # one sample is not a rate
    estimator.add(60, 1060)
    assert estimator.rate == 60 and estimator.running is True
    estimator.add(120, 50)                           # reset from the panel
    assert estimator.running is None
    estimator.add(180, 50)
    assert estimator.running is False


@pytest.mark.parametrize(
    ("step", "expected"), [(1, 5), (4, 50), (8, 70), (0, None), (9, None), (None, None)])
def test_pump_duty_is_unknown_without_a_valid_step(step, expected):
    assert derive.pump_duty(step, (5, 20, 30, 50, 60, 70, 70, 70)) == expected


def test_water_delta_needs_both_probes():
    assert derive.water_delta(25.1, 25.8) == -0.7
    assert derive.water_delta(None, 25.8) is None


@pytest.mark.parametrize(("minutes", "text"), [(60, "01:00"), (0, "00:00"), (1439, "23:59"),
                                               (None, None)])
def test_clock_text(minutes, text):
    assert derive.clock_text(minutes) == text
