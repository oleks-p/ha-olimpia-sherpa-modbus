"""Config, reconfigure and options flows."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.olimpia_sherpa_modbus.const import (
    CONF_BAUDRATE,
    CONF_ENTITY_PREFIX,
    CONF_SERIAL_PORT,
    CONF_SLAVE,
    CONF_TRANSPORT,
    CONF_UNAVAILABLE_AFTER,
    DOMAIN,
)

SERIAL_FORM = {CONF_SERIAL_PORT: "/dev/ttyUSB0", CONF_BAUDRATE: "9600", CONF_SLAVE: 201,
               CONF_ENTITY_PREFIX: "sherpa"}
NETWORK_FORM = {CONF_HOST: "192.0.2.20", CONF_PORT: 4196, CONF_TRANSPORT: "rtu_over_tcp",
                CONF_SLAVE: 201, CONF_ENTITY_PREFIX: "sherpa"}


@pytest.fixture(autouse=True)
def serial_ports():
    with patch("custom_components.olimpia_sherpa_modbus.config_flow._list_serial_ports",
               return_value=["/dev/serial/by-id/usb-FTDI_X-if00-port0", "/dev/ttyUSB0"]):
        yield


@pytest.fixture(autouse=True)
def no_setup():
    """The flows are tested on their own; setting the entry up is test_init's job."""
    with patch("custom_components.olimpia_sherpa_modbus.async_setup_entry", return_value=True):
        yield


async def _start(hass, menu: str):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": menu})


async def test_serial_flow_creates_an_entry(hass, modbus_clients):
    result = await _start(hass, "serial")
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "serial"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SERIAL_FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SHERPA S2 BIG / SHERPA S2 14T"
    assert result["data"] == {**SERIAL_FORM, CONF_BAUDRATE: 9600, CONF_TRANSPORT: "serial"}
    assert result["result"].unique_id == "serial:/dev/ttyUSB0#201"
    # the identity check closed the port again
    assert modbus_clients and not modbus_clients[-1].connected


async def test_network_flow_creates_an_entry(hass, modbus_clients):
    result = await _start(hass, "network")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], NETWORK_FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "tcp:192.0.2.20:4196#201"
    assert modbus_clients[-1].kwargs["port"] == 4196


@pytest.mark.parametrize(
    ("break_it", "error"),
    [
        (lambda fake: setattr(fake, "offline", True), "cannot_connect"),
        (lambda fake: [fake.registers.pop(a) for a in (197, 198, 199)], "not_a_sherpa"),
        (lambda fake: fake.registers.__setitem__(199, 1061), "unsupported_model"),
    ],
)
async def test_identity_problems_are_reported(hass, modbus_clients, fake, break_it, error):
    break_it(fake)
    result = await _start(hass, "serial")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SERIAL_FORM)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_a_flow_recovers_once_the_link_answers(hass, modbus_clients, fake):
    fake.offline = True
    result = await _start(hass, "serial")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SERIAL_FORM)
    assert result["errors"] == {"base": "cannot_connect"}
    fake.offline = False
    result = await hass.config_entries.flow.async_configure(result["flow_id"], SERIAL_FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("prefix", ["", "Sherpa", "heat pump", "sherpa-1"])
async def test_prefix_must_be_a_slug(hass, modbus_clients, prefix):
    result = await _start(hass, "serial")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SERIAL_FORM, CONF_ENTITY_PREFIX: prefix})
    assert result["errors"] == {CONF_ENTITY_PREFIX: "invalid_prefix"}


async def test_same_unit_twice_aborts(hass, modbus_clients, config_entry):
    result = await _start(hass, "serial")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**SERIAL_FORM, CONF_ENTITY_PREFIX: "sherpa_two"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_prefix_in_use_by_another_unit(hass, modbus_clients, config_entry):
    result = await _start(hass, "network")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], NETWORK_FORM)
    assert result["errors"] == {CONF_ENTITY_PREFIX: "prefix_in_use"}


async def test_reconfigure_moves_the_unit_to_another_port(hass, modbus_clients, config_entry):
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERIAL_PORT: "/dev/rs485-host", CONF_BAUDRATE: "9600",
                            CONF_SLAVE: 201})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_SERIAL_PORT] == "/dev/rs485-host"
    assert config_entry.data[CONF_ENTITY_PREFIX] == "sherpa"     # never changes
    assert config_entry.unique_id == "serial:/dev/rs485-host#201"


async def test_reconfigure_reports_a_dead_link(hass, modbus_clients, config_entry, fake):
    fake.offline = True
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERIAL_PORT: "/dev/ttyUSB1", CONF_BAUDRATE: "9600",
                            CONF_SLAVE: 201})
    assert result["errors"] == {"base": "cannot_connect"}
    assert config_entry.data[CONF_SERIAL_PORT] == "/dev/ttyUSB0"


async def test_options_set_the_outage_tolerance(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UNAVAILABLE_AFTER: 300})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # writes stay off unless asked for
    assert config_entry.options == {CONF_UNAVAILABLE_AFTER: 300, "allow_writes": False,
                                    "mode_control": False}


async def test_options_can_allow_writes(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UNAVAILABLE_AFTER: 120, "allow_writes": True})
    assert config_entry.options["allow_writes"] is True


async def test_mode_control_needs_allow_writes(hass, config_entry):
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UNAVAILABLE_AFTER: 120, "mode_control": True})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "mode_control_needs_writes"}
    assert "mode_control" not in config_entry.options

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_UNAVAILABLE_AFTER: 120, "allow_writes": True, "mode_control": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options["mode_control"] is True
