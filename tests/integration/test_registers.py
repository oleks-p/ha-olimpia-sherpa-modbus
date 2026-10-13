"""The register map, the block plan and the translations, against the evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.olimpia_sherpa_modbus.binary_sensor import BINARY_SENSORS
from custom_components.olimpia_sherpa_modbus.block_planner import plan_blocks, split
from custom_components.olimpia_sherpa_modbus.derive import MODE_OPTIONS
from custom_components.olimpia_sherpa_modbus.registers import (
    ANSWERING_RUNS,
    BY_KEY,
    ENUMS,
    FORBIDDEN_WRITES,
    MAX_READ,
    REGISTERS,
    Kind,
    Tier,
)
from custom_components.olimpia_sherpa_modbus.sensor import SENSORS

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "custom_components" / "olimpia_sherpa_modbus"
CAPTURE = json.loads((ROOT / "tests/fixtures/sherpa_s2_big_14t_fw057.json").read_text())
ANSWERING = {int(a) for a, v in CAPTURE["sweep"]["registers"].items() if v["status"] == "OK"}


def test_keys_are_unique_and_addresses_do_not_overlap():
    assert len(BY_KEY) == len(REGISTERS)
    owner: dict[int, str] = {}
    for reg in REGISTERS:
        for address in range(reg.address, reg.end + 1):
            assert address not in owner, f"{reg.key} overlaps {owner[address]}"
            owner[address] = reg.key


def test_every_register_answers_on_the_reference_unit():
    for reg in REGISTERS:
        for address in range(reg.address, reg.end + 1):
            assert address in ANSWERING, f"{reg.key} at {address} did not answer in the sweep"


def test_answering_runs_match_the_capture():
    assert [list(r) for r in ANSWERING_RUNS] == CAPTURE["sweep"]["summary"]["ranges"]["OK"]


def test_the_plan_stays_inside_runs_and_never_splits_a_counter():
    blocks = plan_blocks(REGISTERS)
    seen: dict[tuple[Tier, str], int] = {}
    for block in blocks:
        assert block.count <= MAX_READ
        assert any(first <= block.address and block.end <= last for first, last in ANSWERING_RUNS)
        for reg in block.registers:
            assert block.address <= reg.address and reg.end <= block.end
            assert reg.tier is block.tier
            seen[(reg.tier, reg.key)] = seen.get((reg.tier, reg.key), 0) + 1
    assert all(count == 1 for count in seen.values())
    assert len(seen) == len(REGISTERS)


def test_the_plan_is_small():
    blocks = plan_blocks(REGISTERS)
    per_tier = {tier: sum(1 for b in blocks if b.tier is tier) for tier in Tier}
    assert per_tier[Tier.CONTROL] == 5
    assert per_tier[Tier.PROCESS] == 1      # 0-7 in one read
    assert per_tier[Tier.SETPOINT] <= 5     # 206-212 + 217-249 + 341 + 369 + 380-387


def test_split_reads_each_register_alone():
    # As planned for the reference unit: no Aquadue-only DHW counters at 276/278.
    reference = [r for r in REGISTERS if r.feature is None]
    block = next(b for b in plan_blocks(reference) if b.registers[0].key == "compressor_seconds")
    singles = split(block)
    assert [(s.address, s.count) for s in singles] == [(270, 2), (272, 2), (274, 2)]


def test_counters_are_high_word_first_u32():
    for key in ("compressor_seconds", "pump_seconds", "filter_seconds"):
        assert BY_KEY[key].kind is Kind.U32


def test_registers_that_must_never_be_written():
    # 229 = 0 raised E08 (no K5 fitted); 220 hands the panel to the serial port;
    # 247 / 401 would cut communication; 370 / 371 are the model configuration.
    assert {229, 220, 247, 401, 370, 371} <= FORBIDDEN_WRITES
    assert not FORBIDDEN_WRITES & {206, 207, 208, 209, 210}   # P4 write candidates


@pytest.mark.parametrize("language", ["en", "uk"])
def test_every_entity_is_translated(language):
    strings = json.loads((PACKAGE / "translations" / f"{language}.json").read_text())
    for domain, descriptions in (("sensor", SENSORS), ("binary_sensor", BINARY_SENSORS)):
        names = strings["entity"][domain]
        for description in descriptions:
            assert names.get(description.key, {}).get("name"), f"{language}: {description.key}"
            for option in getattr(description, "options", None) or ():
                assert option in names[description.key]["state"], f"{description.key}.{option}"
    assert set(strings["entity"]["sensor"]["mode"]["state"]) == set(MODE_OPTIONS)


def test_translations_share_one_structure():
    def shape(node):
        return {k: shape(v) for k, v in node.items()} if isinstance(node, dict) else None

    strings = json.loads((PACKAGE / "strings.json").read_text())
    english = json.loads((PACKAGE / "translations" / "en.json").read_text())
    ukrainian = json.loads((PACKAGE / "translations" / "uk.json").read_text())
    assert strings == english
    assert shape(ukrainian) == shape(english)


def test_enum_values_are_snake_case_keys():
    import re

    for table in (*ENUMS.values(), dict(enumerate(MODE_OPTIONS))):
        for key in table.values():
            assert re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", key), key


def test_manifest_and_version():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    assert manifest["domain"] == "olimpia_sherpa_modbus"
    assert manifest["version"] == "0.1.0"
    assert manifest["iot_class"] == "local_polling" and manifest["config_flow"] is True
