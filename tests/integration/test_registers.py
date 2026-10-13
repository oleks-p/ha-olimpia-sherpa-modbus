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
    assert manifest["version"] == "0.2.0"
    assert manifest["iot_class"] == "local_polling" and manifest["config_flow"] is True


def test_entities_manifest_is_current():
    """entities.json is the release's entity manifest, for tools that check dashboards."""
    import subprocess
    import sys

    result = subprocess.run([sys.executable, str(ROOT / "tools" / "export_entities.py"),
                             "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_every_write_candidate_can_be_checked_on_the_reference_unit():
    """Each candidate answered the sweep, and its value there sits on the spec --
    otherwise the write check would call it unverifiable before it started."""
    from custom_components.olimpia_sherpa_modbus.registers import WRITE_SPECS
    from custom_components.olimpia_sherpa_modbus.writes import decode, on_step

    registers = CAPTURE["sweep"]["registers"]
    for key, spec in WRITE_SPECS.items():
        reg = BY_KEY[key]
        assert reg.address in ANSWERING, key
        assert reg.kind is not Kind.U32, key          # FC6 writes one word
        value = decode(reg, registers[str(reg.address)]["raw"])
        if spec.platform == "switch":
            assert value in (0, 1), key
        else:
            assert on_step(spec, value), f"{key}: {value} outside {spec}"


@pytest.mark.parametrize("language", ["en", "uk"])
def test_writes_are_translated(language):
    from custom_components.olimpia_sherpa_modbus.registers import WRITE_SPECS

    strings = json.loads((PACKAGE / "translations" / f"{language}.json").read_text())
    for key, spec in WRITE_SPECS.items():
        assert strings["entity"][spec.platform][key]["name"], key
        assert strings["selector"]["write_register"]["options"][key], key
    service = strings["services"]["verify_write"]
    assert service["name"] and set(service["fields"]) == {"config_entry_id", "register",
                                                          "hold_seconds"}
    assert strings["options"]["step"]["init"]["data"]["allow_writes"]
    for key in ("writes_disabled", "not_writable", "not_a_candidate", "out_of_range",
                "rate_limited", "write_not_applied", "write_failed", "write_refused",
                "restore_failed", "choose_entry"):
        assert strings["exceptions"][key]["message"], key
    assert strings["issues"]["restore_failed"]["description"]


def test_the_service_offers_exactly_the_candidates():
    import yaml

    from custom_components.olimpia_sherpa_modbus.registers import WRITE_SPECS

    services = yaml.safe_load((PACKAGE / "services.yaml").read_text())
    options = services["verify_write"]["fields"]["register"]["selector"]["select"]["options"]
    assert options == sorted(WRITE_SPECS)


def test_translations_are_generated():
    import subprocess
    import sys

    result = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_translations.py"),
                             "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("board", ["sherpa.yaml", "sherpa_service.yaml"])
def test_dashboards_bind_only_entities_the_release_creates(board):
    import re

    manifest = json.loads((ROOT / "entities.json").read_text())
    provided = {f"{e['domain']}.sherpa_{e['key']}" for e in manifest["entities"]}
    text = (ROOT / "dashboards" / board).read_text()
    bound = set(re.findall(r"\b(?:sensor|binary_sensor|number|switch)\.sherpa_[a-z0-9_]+", text))
    assert bound and not bound - provided, sorted(bound - provided)
    if board == "sherpa.yaml":     # the everyday board never offers a control
        assert not {b for b in bound if b.startswith(("number.", "switch."))}


def test_the_live_check_tool_covers_every_candidate_once():
    import sys

    from custom_components.olimpia_sherpa_modbus.registers import WRITE_SPECS

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import verify_writes
    finally:
        sys.path.remove(str(ROOT / "tools"))
    assert sorted(verify_writes.ORDER) == sorted(WRITE_SPECS)
    assert len(set(verify_writes.ORDER)) == len(verify_writes.ORDER)
    assert verify_writes.ORDER[-1] == "heating_curve_enabled"    # the one that matters most, last
