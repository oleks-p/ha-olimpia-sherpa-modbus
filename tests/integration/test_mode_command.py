"""The admin write_mode_command action: register 106, for the P6 test.

Unlike a parameter write it is sent every time -- a rewrite is the keep-alive
that holds off E09 -- and a read-back that differs is reported, not raised:
with ADDR220 = 0 the unit may well ignore it, and that is what the test is for.
"""

from __future__ import annotations

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.olimpia_sherpa_modbus.const import CONF_ALLOW_WRITES, DOMAIN
from custom_components.olimpia_sherpa_modbus.registers import MODE_COMMAND

ADDRESS = MODE_COMMAND.address     # 106, reads 0 on the reference unit
HEATING, COOLING = 8, 4


@pytest.fixture
async def writable(hass, config_entry, modbus_clients, freezer):
    hass.config_entries.async_update_entry(config_entry, options={CONF_ALLOW_WRITES: True})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _command(hass, value: int) -> dict:
    return await hass.services.async_call(DOMAIN, "write_mode_command", {"value": value},
                                          blocking=True, return_response=True)


async def test_it_writes_106_and_reports_what_the_unit_does(hass, writable, fake):
    fake.registers[100] = 1 << 8                            # E09 standing
    result = await _command(hass, HEATING)
    assert fake.writes == [(ADDRESS, HEATING)]
    assert result["written"] == HEATING and result["before"] == 0
    assert result["read_back"] == HEATING
    assert result["status"] == fake.registers[12]
    assert result["outputs"] == fake.registers[105]
    assert result["alarm_1"] == 1 << 8 and result["alarm_2"] == 0
    assert result["inputs"] == fake.registers[8]
    assert result["remote_controls"] == 0


async def test_the_same_value_is_written_again(hass, writable, fake):
    # The keep-alive: 106 already holds the value, and must still be written --
    # also faster than the parameter writes' once per 10 s.
    for _ in range(3):
        await _command(hass, 0)
    assert fake.writes == [(ADDRESS, 0)] * 3


async def test_an_ignored_command_is_a_result_not_an_error(hass, writable, fake):
    fake.write_mode[ADDRESS] = "ignore"
    result = await _command(hass, HEATING)
    assert result["written"] == HEATING and result["read_back"] == 0


async def test_a_refused_command_is_an_error(hass, writable, fake):
    fake.write_mode[ADDRESS] = "refuse"
    with pytest.raises(HomeAssistantError):
        await _command(hass, HEATING)


async def test_heating_and_cooling_together_are_refused(hass, writable, fake):
    with pytest.raises(ServiceValidationError):
        await _command(hass, HEATING | COOLING)
    assert fake.writes == []


async def test_only_the_documented_bits(hass, writable, fake):
    with pytest.raises(vol.Invalid):
        await _command(hass, 32)
    assert fake.writes == []


async def test_it_needs_the_writes_option(hass, setup_integration, fake):
    with pytest.raises(ServiceValidationError):
        await _command(hass, HEATING)
    assert fake.writes == []


async def test_it_is_logged_and_announced(hass, writable, fake):
    events = []
    hass.bus.async_listen(f"{DOMAIN}_parameter_written", events.append)
    await _command(hass, HEATING)
    await hass.async_block_till_done()
    assert events[0].data["key"] == "mode_command" and events[0].data["address"] == ADDRESS
    assert writable.runtime_data.coordinator.writes.log[-1]["key"] == "mode_command"


async def test_106_is_polled_with_outputs(hass, writable, fake):
    # 105-106 is one run: the mode command costs no extra request.
    reads = [(a, c) for _, fc, a, c in fake.requests if fc == 3 and a <= ADDRESS < a + c]
    assert reads and set(reads) == {(105, 2)}
    assert writable.runtime_data.coordinator.data.values["mode_command"] == 0
