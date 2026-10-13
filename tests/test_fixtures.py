"""The legacy-site fixtures are internally consistent.

These pin the evidence the integration is built against. If a re-capture
changes them, these tests say what moved before any decoder test fails for an
unclear reason.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from tests import legacy

LEGACY = legacy.load_legacy()
ENTITIES = LEGACY["entities"]
HISTORY = legacy.load_history()


def test_entity_ids_are_prefix_plus_key():
    for entity_id, record in ENTITIES.items():
        assert entity_id == f"{record['domain']}.sherpa_{record['key']}"


def test_every_legacy_entity_is_traced_to_its_yaml():
    assert all(record["definition"] for record in ENTITIES.values())
    # The hand-written package's hub is rejected as a duplicate of the
    # generated one, so the two registers only it reads are unavailable.
    rejected = sorted(e for e, r in ENTITIES.items() if r["hub_loaded"] is False)
    assert rejected == ["sensor.sherpa_identify_code", "sensor.sherpa_pump_step"]


def test_statistics_metadata_matches_the_entities():
    with_stats = {e: r for e, r in ENTITIES.items() if r["statistics"]}
    assert len(with_stats) == 20
    for entity_id, record in with_stats.items():
        stats = record["statistics"]
        assert stats["unit"] == record["unit"], entity_id
        if stats["has_sum"]:
            assert record["state_class"] == "total_increasing", entity_id
        else:
            assert stats["has_mean"] and record["state_class"] == "measurement", entity_id


def test_compressor_running_has_history_but_no_registry_entry():
    # The threshold platform takes no unique_id. At the cutover nothing has to
    # be removed from the registry for the integration to claim this entity id.
    record = ENTITIES["binary_sensor.sherpa_compressor_running"]
    assert record["kind"] == "threshold" and record["in_registry"] is False
    assert record["history"]["records"] > 1000


def test_history_series_are_time_ordered():
    for entity_id, rows in HISTORY.items():
        times = [row[0] for row in rows]
        assert times == sorted(times), entity_id


@pytest.mark.parametrize("target", sorted(legacy.TEMPLATES))
def test_legacy_templates_replay_exactly(target):
    decoder, inputs = legacy.TEMPLATES[target]
    results = list(legacy.replay(HISTORY, target, decoder, inputs))
    mismatches = [(t, args, rec, dec) for t, args, rec, dec in results if rec != dec]
    assert len(results) >= 10
    assert mismatches == []


def test_status_values_seen_on_the_reference_unit():
    # 97/98/102 are the pending pattern (96) on top of cooling / heating /
    # heating+DHW; 9 is the legionella cycle, which leaves the cooling bit set.
    seen = {int(state) for _, state in HISTORY["sensor.sherpa_status"]
            if state not in legacy.SENTINELS}
    assert seen == {0, 1, 6, 9, 96, 97, 98, 102}


# -- the register probe's capture of the reference unit (2026-10-13) --------

CAPTURE = json.loads((pathlib.Path(__file__).parent / "fixtures"
                      / "sherpa_s2_big_14t_fw057.json").read_text())


def test_capture_is_the_reference_unit():
    ident = CAPTURE["identity"]
    assert (ident["identify_code"], ident["idu_model"], ident["odu_model"]) == (1134, 2, 14)
    assert ident["fw_197"] == ident["fw_198"] == 57
    assert CAPTURE["sanitized"] is True and CAPTURE["link"]["path"] == "/dev/ttyUSB0"


def test_capture_sweep_is_complete_and_clean():
    regs = CAPTURE["sweep"]["registers"]
    assert len(regs) == 1000 and CAPTURE["sweep"]["stalls"] == []
    assert {v["status"] for v in regs.values()} == {"OK", "EXCEPTION"}
    assert {v["code"] for v in regs.values() if v["status"] == "EXCEPTION"} == {2}


def test_capture_agrees_with_the_legacy_entities():
    # Same instant, two paths: the probe's raw words decode to what HA showed.
    regs = CAPTURE["sweep"]["registers"]
    raw = {int(a): v["raw"] for a, v in regs.items() if v["status"] == "OK"}
    assert raw[206] / 10 == float(ENTITIES["sensor.sherpa_cooling_setpoint"]["state_at_capture"])
    assert raw[210] / 10 == float(ENTITIES["sensor.sherpa_dhw_setpoint"]["state_at_capture"])
    assert (raw[270] << 16 | raw[271]) == int(
        ENTITIES["sensor.sherpa_compressor_seconds"]["state_at_capture"])
    assert raw[231] == int(ENTITIES["sensor.sherpa_legionella_start_minutes"]["state_at_capture"])


def test_register_200_stands_alone():
    # 201-205 do not exist, so a block planner must read 200 by itself -- and the
    # mode-command register is not hiding there.
    regs = CAPTURE["sweep"]["registers"]
    assert regs["200"]["status"] == "OK"
    assert all(regs[str(a)]["status"] == "EXCEPTION" for a in range(201, 206))


def test_capture_block_rules():
    # Measured 2026-10-13 09:22 UTC: every answering run reads whole in one
    # request, up to the longest (217-281, 65 registers); nothing may span a gap.
    rules = CAPTURE["rules"]["summary"]
    assert rules["answering_runs"] == 21 and rules["whole_run_reads"] == 17
    assert rules["all_runs_readable"] is True and rules["unreadable_runs"] == []
    assert rules["safe_read_count"] == rules["ladder_tested_up_to"] == 65
    assert rules["read_across_exception_gap"] == "EXCEPTION"
    assert rules["u32_half_readable"] is True and rules["fc4"] == "unsupported"
    assert rules["block_values_match_sweep"] is True
    assert CAPTURE["sweep_source"]["file"] == "sherpa_observed_20261013-090910.json"


# hassfest's rule for translation keys (script/hassfest/translations.py).
RE_TRANSLATION_KEY = re.compile(r"^(?!.+[_-]{2})(?![_-])[a-z0-9-_]+(?<![_-])$")


def test_every_legacy_mode_has_a_valid_translated_key():
    seen = set(ENTITIES["sensor.sherpa_mode"]["history"]["states"])
    assert seen <= set(legacy.MODE_KEYS)          # nothing in 57 days left unmapped
    assert {legacy.mode(s) for s in range(256)} <= set(legacy.MODE_KEYS)
    for key in legacy.MODE_KEYS.values():
        assert RE_TRANSLATION_KEY.match(key), key
        assert re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", key), f"{key} is not snake_case"
    changed = {old for old, new in legacy.MODE_KEYS.items() if old != new}
    assert changed == {"domestic hot water", "anti-legionella"}
