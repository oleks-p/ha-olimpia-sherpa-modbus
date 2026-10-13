"""Setup, unload and identity handling."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir

from custom_components.olimpia_sherpa_modbus.const import DOMAIN


async def test_setup_reads_the_unit_and_unload_releases_the_port(
        hass, setup_integration, modbus_clients):
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.sherpa_water_in").state == "25.8"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert modbus_clients[-1].closes >= 1 and not modbus_clients[-1].connected


async def test_device_and_setup_with_the_real_capture(hass, setup_integration):
    device = dr.async_get(hass).async_get_device({(DOMAIN, setup_integration.entry_id)})
    assert device is not None


async def test_unsupported_model_stops_setup_and_raises_a_repair(
        hass, config_entry, modbus_clients, fake):
    fake.registers[199] = 1026      # the original Sherpa: a different layout
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"unsupported_model_{config_entry.entry_id}")
    assert issue is not None and issue.translation_placeholders["code"] == "1026"


async def test_something_else_at_the_address_is_an_error(hass, config_entry, modbus_clients, fake):
    for address in (197, 198, 199):
        del fake.registers[address]
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_no_answer_at_setup_is_retried(hass, config_entry, modbus_clients, fake):
    fake.offline = True
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    # and the port was not left open
    assert all(not c.connected for c in modbus_clients)
