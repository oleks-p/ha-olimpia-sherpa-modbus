"""Diagnostics: enough to reproduce a decoding problem without the hardware."""

from __future__ import annotations

from custom_components.olimpia_sherpa_modbus.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_carry_raw_words_and_redact_the_port(hass, setup_integration):
    diag = await async_get_config_entry_diagnostics(hass, setup_integration)
    assert diag["entry"]["data"]["serial_port"] == "**REDACTED**"
    assert diag["model"]["identify"] == 1134 and diag["model"]["register_map"] == "sherpa-s2-r3"
    assert diag["raw_registers"]["0+8"][:4] == [258, 251, 221, 132]
    assert diag["values"]["water_in"] == 25.8
    assert diag["link"]["consecutive_failures"] == 0
    assert any(line.startswith("control 8..8") for line in diag["block_plan"])
