"""The admin read_registers action: raw words through the integration's bus."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.olimpia_sherpa_modbus.const import DOMAIN
from custom_components.olimpia_sherpa_modbus.raw_read import spans
from custom_components.olimpia_sherpa_modbus.registers import ANSWERING_RUNS, MAX_READ
from tests.integration.conftest import CAPTURE  # noqa: F401  (the fake serves it)


async def _read(hass, **data) -> dict:
    return await hass.services.async_call(DOMAIN, "read_registers", data,
                                          blocking=True, return_response=True)


async def test_a_snapshot_reads_every_answering_register(hass, setup_integration, fake):
    result = await _read(hass)
    expected = {a for start, end in ANSWERING_RUNS for a in range(start, end + 1)}
    assert {int(a) for a in result["registers"]} == expected
    assert result["registers"]["199"] == 1134 and result["registers"]["12"] == 0
    assert result["refused"] == [] and result["identify"] == 1134
    assert fake.writes == []                                # it only reads


async def test_one_range_is_read_as_asked(hass, setup_integration):
    result = await _read(hass, address=197, count=3)
    assert result["registers"] == {"197": 57, "198": 57, "199": 1134}


async def test_a_refused_range_is_reported_not_raised(hass, setup_integration):
    result = await _read(hass, address=201, count=5)      # 201-205 do not exist
    assert result["registers"] == {}
    assert result["refused"] == [{"address": 201, "count": 5, "exception": 2}]


async def test_a_dead_link_is_an_error(hass, setup_integration, fake):
    fake.stall(10)                                       # the bus goes quiet
    with pytest.raises(HomeAssistantError):
        await _read(hass, address=0, count=4)


async def test_it_needs_no_writes_option(hass, setup_integration):
    assert not setup_integration.runtime_data.coordinator.writes.allowed
    assert (await _read(hass, address=12))["registers"] == {"12": 0}


def test_long_runs_are_split_at_the_read_limit():
    assert spans(0, 300) == [(0, MAX_READ), (MAX_READ, MAX_READ), (2 * MAX_READ, 50)]
    assert all(count <= MAX_READ for _, count in spans(None, 1))
