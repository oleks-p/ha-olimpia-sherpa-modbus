"""The register probe's capture of the reference unit is internally consistent.

It pins the evidence the integration is built against. If a re-capture changes
it, these tests say what moved before any decoder test fails for an unclear
reason.
"""
from __future__ import annotations

import json
import pathlib

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
