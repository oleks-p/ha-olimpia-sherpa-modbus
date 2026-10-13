"""Opt-in writes: the write check, the gates, and the write path.

The fake unit answers FC6 the way a controller might -- accept, refuse,
acknowledge without applying ("ignore"), or apply and then put its own value
back ("revert") -- and the write check must tell all four apart, and always
leave the register as it found it.
"""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.olimpia_sherpa_modbus.const import CONF_ALLOW_WRITES, DOMAIN
from custom_components.olimpia_sherpa_modbus.registers import BY_KEY, FORBIDDEN_WRITES, WRITE_SPECS
from custom_components.olimpia_sherpa_modbus.writes import CHECKS

HEATING = BY_KEY["heating_setpoint"].address   # 208, reads 350 (35.0 degC)


@pytest.fixture
async def writable(hass, config_entry, modbus_clients, freezer):
    """The integration with writes allowed (no register verified yet)."""
    hass.config_entries.async_update_entry(config_entry, options={CONF_ALLOW_WRITES: True})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _check(hass, key: str, hold: int = 1) -> dict:
    return await hass.services.async_call(
        DOMAIN, "verify_write", {"register": key, "hold_seconds": hold},
        blocking=True, return_response=True)


# -- the write check -------------------------------------------------------------

async def test_a_passing_check_restores_the_value_and_adds_the_entity(hass, writable, fake):
    assert hass.states.get("number.sherpa_heating_setpoint") is None      # not yet verified
    result = await _check(hass, "heating_setpoint")
    assert result["result"] == "roundtrip_ok"
    assert result["original"] == 35.0 and result["restored"] == 35.0
    assert result["identify"] == 1134 and result["firmware"] == "0.57"
    # same value, then one step away, then back
    assert [v for a, v in fake.writes if a == HEATING] == [350, 355, 350]
    assert fake.registers[HEATING] == 350
    await hass.async_block_till_done()
    state = hass.states.get("number.sherpa_heating_setpoint")
    assert state.state == "35.0"
    assert state.attributes["min"] == 20.0 and state.attributes["step"] == 0.5


async def test_a_refused_write_is_reported_and_nothing_changes(hass, writable, fake):
    fake.write_mode[HEATING] = "refuse"
    result = await _check(hass, "heating_setpoint")
    assert result["result"] == "refused"
    assert fake.registers[HEATING] == 350 and fake.writes == []
    await hass.async_block_till_done()
    assert hass.states.get("number.sherpa_heating_setpoint") is None


async def test_an_acknowledged_but_ignored_write_is_not_trusted(hass, writable, fake):
    # What the manual suggests for ADDR220 = 0 (display only); the reference
    # unit applied writes anyway, but another firmware may not.
    fake.write_mode[HEATING] = "ignore"
    result = await _check(hass, "heating_setpoint")
    assert result["result"] == "ignored"
    assert fake.registers[HEATING] == 350


async def test_a_write_the_controller_undoes_is_caught(hass, writable, fake):
    fake.write_mode[HEATING] = "revert"
    result = await _check(hass, "heating_setpoint")
    assert result["result"] == "reverted"
    assert fake.registers[HEATING] == 350


async def test_the_neighbour_stays_inside_the_spec(hass, writable, fake):
    fake.registers[HEATING] = 550          # at the 55.0 maximum: step down, not up
    await _check(hass, "heating_setpoint")
    assert [v for a, v in fake.writes if a == HEATING] == [550, 545, 550]


async def test_a_value_outside_the_spec_is_not_touched(hass, writable, fake):
    fake.registers[HEATING] = 600          # 60.0, outside 20-55
    result = await _check(hass, "heating_setpoint")
    assert result["result"] == "unverifiable" and fake.writes == []


async def test_a_switch_check_toggles_and_restores(hass, writable, fake):
    address = BY_KEY["heating_curve_enabled"].address
    result = await _check(hass, "heating_curve_enabled")
    assert result["result"] == "roundtrip_ok"
    assert [v for a, v in fake.writes if a == address] == [1, 0, 1]
    await hass.async_block_till_done()
    assert hass.states.get("switch.sherpa_heating_curve_enabled").state == "on"


async def test_a_failed_restore_raises_a_repair(hass, writable, fake):
    _break_restore(fake)
    with pytest.raises(HomeAssistantError):
        await _check(hass, "heating_setpoint")
    assert ir.async_get(hass).async_get_issue(DOMAIN, "restore_failed_heating_setpoint")


def _break_restore(fake):
    """The link goes silent just when the original is due back."""
    real_write = fake.write

    def write_then_die(unit, address, value):
        if fake.writes and fake.writes[-1] == (HEATING, 355):
            return None
        return real_write(unit, address, value)

    fake.write = write_then_die
    return real_write


async def test_an_owed_restore_is_paid_at_the_next_setup(hass, writable, fake):
    real_write = _break_restore(fake)
    with pytest.raises(HomeAssistantError):
        await _check(hass, "heating_setpoint")
    assert fake.registers[HEATING] == 355
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "restore_failed_heating_setpoint")
    assert issue.is_persistent
    fake.write = real_write                       # the link is back
    assert await hass.config_entries.async_reload(writable.entry_id)
    await hass.async_block_till_done()
    assert fake.registers[HEATING] == 350
    assert fake.writes[-1] == (HEATING, 350)
    assert hass.data[CHECKS].pending(writable.entry_id) is None
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "restore_failed_heating_setpoint")


async def test_a_value_put_right_by_hand_is_left_alone(hass, writable, fake):
    real_write = _break_restore(fake)
    with pytest.raises(HomeAssistantError):
        await _check(hass, "heating_setpoint")
    fake.write = real_write
    fake.registers[HEATING] = 360                 # set on the panel meanwhile
    written = len(fake.writes)
    assert await hass.config_entries.async_reload(writable.entry_id)
    await hass.async_block_till_done()
    assert len(fake.writes) == written and fake.registers[HEATING] == 360
    assert hass.data[CHECKS].pending(writable.entry_id) is None
    assert not ir.async_get(hass).async_get_issue(DOMAIN, "restore_failed_heating_setpoint")


async def test_an_owed_restore_waits_while_writes_are_off(hass, writable, fake):
    real_write = _break_restore(fake)
    with pytest.raises(HomeAssistantError):
        await _check(hass, "heating_setpoint")
    fake.write = real_write
    hass.config_entries.async_update_entry(writable, options={CONF_ALLOW_WRITES: False})
    written = len(fake.writes)
    assert await hass.config_entries.async_reload(writable.entry_id)
    await hass.async_block_till_done()
    assert len(fake.writes) == written and fake.registers[HEATING] == 355
    assert hass.data[CHECKS].pending(writable.entry_id)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "restore_failed_heating_setpoint")


async def test_a_write_waits_for_a_running_check(hass, writable, fake, freezer):
    import asyncio
    from unittest.mock import patch

    await _verified(hass)
    holding, release = asyncio.Event(), asyncio.Event()

    async def hold(_seconds):
        holding.set()
        await release.wait()

    with patch("custom_components.olimpia_sherpa_modbus.writes._wait", hold):
        check = hass.async_create_task(_check(hass, "heating_setpoint"))
        await holding.wait()                      # the check holds 35.5 on the unit
        freezer.tick(11)
        write = hass.async_create_task(_set(hass, 37.5))
        await asyncio.sleep(0)
        assert fake.registers[HEATING] == 355     # the write has not gone out
        release.set()
        assert (await check)["result"] == "roundtrip_ok"
        await write
    # the check restored first; the write came after and stands
    assert [v for a, v in fake.writes if a == HEATING][-3:] == [355, 350, 375]
    assert fake.registers[HEATING] == 375


async def test_check_results_survive_a_reload(hass, writable, fake):
    await _check(hass, "heating_setpoint")
    assert await hass.config_entries.async_reload(writable.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.sherpa_heating_setpoint").state == "35.0"
    assert hass.data[CHECKS].for_entry(writable.entry_id)["heating_setpoint"]["result"] \
        == "roundtrip_ok"


async def test_a_firmware_change_invalidates_the_check(hass, writable, fake):
    await _check(hass, "heating_setpoint")
    fake.registers[197] = 58                # firmware 0.58 after an update
    assert await hass.config_entries.async_reload(writable.entry_id)
    await hass.async_block_till_done()
    assert not writable.runtime_data.coordinator.writes.writable("heating_setpoint")
    assert hass.states.get("number.sherpa_heating_setpoint").state == "unavailable"


# -- the gates -------------------------------------------------------------------

async def test_with_writes_off_there_is_no_check_and_no_writable_entity(
        hass, setup_integration, fake):
    with pytest.raises(ServiceValidationError):
        await _check(hass, "heating_setpoint")
    assert fake.writes == []
    registry = er.async_get(hass)
    assert not [e for e in er.async_entries_for_config_entry(registry, setup_integration.entry_id)
                if e.domain in ("number", "switch")]


async def test_turning_writes_off_removes_the_writable_entities(hass, writable, fake):
    await _check(hass, "heating_setpoint")
    await hass.async_block_till_done()
    assert hass.states.get("number.sherpa_heating_setpoint")
    hass.config_entries.async_update_entry(writable, options={CONF_ALLOW_WRITES: False})
    assert await hass.config_entries.async_reload(writable.entry_id)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get("number.sherpa_heating_setpoint") is None
    assert hass.states.get("sensor.sherpa_heating_setpoint").state == "35.0"   # the mirror stays


def test_no_forbidden_register_is_a_candidate():
    assert not {BY_KEY[k].address for k in WRITE_SPECS} & FORBIDDEN_WRITES
    for spec in WRITE_SPECS.values():
        assert spec.minimum < spec.maximum and spec.step > 0


async def test_only_candidates_can_be_checked(hass, writable):
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "verify_write", {"register": "legionella_mode"},
                                       blocking=True, return_response=True)


# -- the write path ----------------------------------------------------------------

async def _verified(hass, key="heating_setpoint"):
    await _check(hass, key)
    await hass.async_block_till_done()


async def _set(hass, value, entity="number.sherpa_heating_setpoint"):
    await hass.services.async_call("number", "set_value", {"entity_id": entity, "value": value},
                                   blocking=True)


async def test_a_write_reads_back_and_shows_at_once(hass, writable, fake, freezer):
    await _verified(hass)
    events = []
    hass.bus.async_listen(f"{DOMAIN}_parameter_written", events.append)
    freezer.tick(11)
    await _set(hass, 37.5)
    assert fake.registers[HEATING] == 375
    await hass.async_block_till_done()
    # both the number and its read-only mirror, without waiting for the 10-minute poll
    assert hass.states.get("number.sherpa_heating_setpoint").state == "37.5"
    assert hass.states.get("sensor.sherpa_heating_setpoint").state == "37.5"
    assert events and events[0].data["old"] == 35.0 and events[0].data["new"] == 37.5


async def test_an_unchanged_value_is_not_written(hass, writable, fake):
    await _verified(hass)
    before = len(fake.writes)
    await _set(hass, 35.0)
    assert len(fake.writes) == before      # no write, no wear


async def test_a_value_off_the_step_or_range_is_refused(hass, writable, fake):
    await _verified(hass)
    for bad in (37.3, 19.5, 56.0):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "number", "set_value",
                {"entity_id": "number.sherpa_heating_setpoint", "value": bad}, blocking=True)


async def test_writes_are_rate_limited(hass, writable, fake, freezer):
    await _verified(hass)
    freezer.tick(11)
    await _set(hass, 36.0)
    with pytest.raises(HomeAssistantError):
        await _set(hass, 36.5)             # the same register again within 10 s
    freezer.tick(11)
    await _set(hass, 36.5)
    assert fake.registers[HEATING] == 365


async def test_a_write_the_unit_does_not_apply_is_an_error(hass, writable, fake, freezer):
    await _verified(hass)
    fake.write_mode[HEATING] = "ignore"
    freezer.tick(11)
    with pytest.raises(HomeAssistantError):
        await _set(hass, 40.0)
    await hass.async_block_till_done()
    assert hass.states.get("number.sherpa_heating_setpoint").state == "35.0"   # the truth


async def test_a_switch_writes_zero_and_one(hass, writable, fake, freezer):
    address = BY_KEY["heating_curve_enabled"].address
    await _verified(hass, "heating_curve_enabled")
    freezer.tick(11)
    await hass.services.async_call("switch", "turn_off",
                                   {"entity_id": "switch.sherpa_heating_curve_enabled"},
                                   blocking=True)
    assert fake.registers[address] == 0
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.sherpa_heating_curve_enabled").state == "off"


async def test_writes_appear_in_diagnostics(hass, writable, fake, freezer):
    from custom_components.olimpia_sherpa_modbus.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    await _verified(hass)
    freezer.tick(11)
    await _set(hass, 36.0)
    diag = await async_get_config_entry_diagnostics(hass, writable)
    assert diag["writes"]["allowed"] is True
    assert diag["writes"]["writable"] == ["heating_setpoint"]
    assert diag["writes"]["recent_writes"][-1]["new"] == 36.0


async def test_polling_keeps_working_around_a_check(hass, writable, fake, freezer):
    await _check(hass, "heating_setpoint")
    freezer.tick(10)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sherpa_water_in").state == "25.8"
