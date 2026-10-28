"""The derived values: mode, fault codes, pump duty, the compressor estimate."""

from __future__ import annotations

import pytest

from custom_components.olimpia_sherpa_modbus import derive


# Every status value the reference unit has shown, and the mode each one means.
@pytest.mark.parametrize(("status", "mode"), [
    (0, "standby"), (1, "cooling"), (6, "domestic_hot_water"), (9, "anti_legionella"),
    (96, "standby"), (97, "cooling"), (98, "heating"), (102, "domestic_hot_water"),
])
def test_mode_covers_every_status_value_seen(status, mode):
    assert derive.mode(status) == mode


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


# -- the mode command (register 106) ----------------------------------------------

@pytest.mark.parametrize(("word", "mode", "selected"), [
    (0, "dhw_only", "off"), (1, "standby", "off"), (8, "heating", "heating"),
    (4, "cooling", "cooling"), (10, "heating", "heating"), (24, "heating", "heating"),
    (9, "standby", "off"),            # standby wins over a mode bit
    (5, "standby", "off"), (16, "dhw_only", "off"), (2, "dhw_only", "off"),
])
def test_commanded_mode_and_selection(word, mode, selected):
    assert derive.commanded_mode(word) == mode
    assert derive.selected_from_command(word) == selected


def test_no_command_is_unknown():
    assert derive.commanded_mode(None) is None
    assert derive.selected_from_command(None) is None


def test_command_word_round_trips_every_combination():
    import itertools

    seen = set()
    for mode, standby, eco, night in itertools.product(
            derive.COMMAND_MODES, (False, True), (False, True), (False, True)):
        word = derive.command_word(mode, standby=standby, eco=eco, night=night)
        assert not (word & 8 and word & 4), word             # never heating and cooling
        assert word not in seen
        seen.add(word)
        assert derive.commanded_mode(word) == ("standby" if standby else mode)
        assert derive.command_mode(word) == mode              # standby keeps the mode bit
        assert bool(word & 2) is eco and bool(word & 16) is night
    assert len(seen) == 24


def test_documented_words():
    assert derive.command_word("heating") == 8
    assert derive.command_word("heating", eco=True) == 10
    assert derive.command_word("heating", night=True) == 24
    assert derive.command_word("cooling") == 4
    assert derive.command_word("dhw_only") == 0
    assert derive.command_word("heating", standby=True) == 9
    assert derive.command_word("dhw_only", standby=True, eco=True) == 3
