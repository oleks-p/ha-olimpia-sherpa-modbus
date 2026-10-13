"""The read-only climate entity, and the selection and target behind it."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.olimpia_sherpa_modbus import derive

ENTITY = "climate.sherpa_heat_pump"
STATUS, OUTPUTS, OVERRIDE = 12, 105, 102


async def _poll(hass, freezer, seconds: float = 10) -> None:
    freezer.tick(seconds)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


# -- the pure parts -----------------------------------------------------------

@pytest.mark.parametrize(("status", "last", "expected"), [
    (0, None, "off"), (2, None, "heating"), (1, None, "cooling"),
    (102, "off", "heating"),     # heating chosen in standby, straight into a DHW cycle
    (97, None, "cooling"),       # cooling, compressor pending
    (6, "cooling", "cooling"),   # a DHW cycle sets the heating bit; cooling stays chosen
    (6, "heating", "heating"),
    (9, "heating", "heating"),   # legionella leaves the cooling bit set
    (128 | 2, None, "heating"),  # night is not a mode
    (None, "heating", None),
])
def test_the_selected_mode(status, last, expected):
    assert derive.selected_mode(status, last) == expected


@pytest.mark.parametrize(("outdoor", "expected"), [
    (-10.0, 35.0), (-5.0, 35.0), (11.0, 30.5), (13.2, 29.9), (20.0, 28.0), (25.0, 28.0)])
def test_the_heating_curve_is_a_line_held_at_its_ends(outdoor, expected):
    # The reference unit's curve: -5 degC -> 35, 20 degC -> 28. 11.0 -> 30.5 was
    # worked out by hand on 2026-10-13 against the live readings.
    assert derive.curve(outdoor, -5.0, 35.0, 20.0, 28.0) == expected


def test_the_cooling_curve_runs_the_other_way():
    # 20 degC outside -> 18 water, 40 -> 15: warmer outside, colder water
    assert derive.curve(30.0, 20.0, 18.0, 40.0, 15.0) == 16.5
    assert derive.curve(10.0, 20.0, 18.0, 40.0, 15.0) == 18.0


def test_no_curve_without_its_inputs():
    assert derive.curve(None, -5.0, 35.0, 20.0, 28.0) is None
    assert derive.curve(10.0, 20.0, 35.0, 20.0, 28.0) is None    # two points at one place


def test_the_target_is_the_fixed_setpoint_with_the_curve_off():
    values = {"heating_curve_enabled": 0, "heating_setpoint": 35.0, "outdoor_air": 5.0}
    assert derive.water_target("heating", values) == (35.0, "heating_setpoint")
    assert derive.water_target("off", values) == (None, None)


# -- the entity -----------------------------------------------------------------

async def test_standby_is_off_and_offers_nothing_else(hass, setup_integration):
    state = hass.states.get(ENTITY)
    assert state.state == "off"
    assert state.attributes["hvac_modes"] == ["off"]
    assert state.attributes["hvac_action"] == "off"
    assert state.attributes["current_temperature"] == 25.1          # T2, water out
    assert state.attributes["supported_features"] == 0
    assert "temperature" not in state.attributes                    # nothing to set
    assert state.attributes["water_target"] is None
    assert state.attributes["remote_controls"] == 0


async def test_heating_shows_the_curve_target(hass, setup_integration, fake, freezer):
    fake.registers[STATUS] = 98                                      # heating, pending
    await _poll(hass, freezer)
    state = hass.states.get(ENTITY)
    assert state.state == "heat" and state.attributes["hvac_modes"] == ["heat"]
    assert state.attributes["hvac_action"] == "idle"                 # compressor not running
    # outdoor 13.2 on the heating curve -5 -> 35, 20 -> 28
    assert state.attributes["water_target"] == 29.9
    assert state.attributes["water_target_source"] == "heating_curve"
    assert hass.states.get("sensor.sherpa_water_target").state == "29.9"


async def test_a_dhw_cycle_does_not_change_the_selection(hass, setup_integration, fake,
                                                        freezer):
    fake.registers[STATUS] = 1                                       # cooling chosen
    await _poll(hass, freezer)
    fake.registers[STATUS] = 6                                       # DHW cycle: heating bit
    fake.registers[OUTPUTS] = 17
    await _poll(hass, freezer)
    state = hass.states.get(ENTITY)
    assert state.state == "cool"
    assert state.attributes["hvac_action"] == "idle"
    assert state.attributes["dhw_in_progress"] is True


async def test_defrost_and_night(hass, setup_integration, fake, freezer):
    fake.registers[STATUS] = 2 | 128
    fake.registers[OVERRIDE] = 32                                    # OR06: defrost
    await _poll(hass, freezer)
    state = hass.states.get(ENTITY)
    assert state.attributes["hvac_action"] == "defrosting"
    assert state.attributes["night"] is True


async def test_another_mode_cannot_be_set(hass, setup_integration, fake):
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("climate", "set_hvac_mode",
                                       {"entity_id": ENTITY, "hvac_mode": "heat"}, blocking=True)
    # the one it is in is accepted, and nothing is sent
    await hass.services.async_call("climate", "set_hvac_mode",
                                   {"entity_id": ENTITY, "hvac_mode": "off"}, blocking=True)
    assert fake.writes == []


async def test_a_running_compressor_is_heating(hass, setup_integration, fake, freezer):
    fake.registers[STATUS] = 2
    for _ in range(4):                       # the runtime counter gains 60 s a minute
        fake.registers[271] += 60
        for _ in range(6):
            await _poll(hass, freezer)
    assert hass.states.get("binary_sensor.sherpa_compressor_running").state == "on"
    assert hass.states.get(ENTITY).attributes["hvac_action"] == "heating"


async def test_the_curves_ride_along_for_the_cards(hass, setup_integration):
    attrs = hass.states.get(ENTITY).attributes
    assert attrs["heating_curve"] == {"enabled": True, "outdoor_at_max_water": -5.0,
                                      "max_water": 35.0, "outdoor_at_min_water": 20.0,
                                      "min_water": 28.0}
    assert attrs["cooling_curve"]["max_water"] == 18.0
