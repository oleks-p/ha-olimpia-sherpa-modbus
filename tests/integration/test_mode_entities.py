"""The mode-control entities: select, ECO and night switches, climate, hot water.

All show register 106 as the unit read it back, and send only while the
controller is active (ADDR220 = 1).
"""

from __future__ import annotations

import pytest
from homeassistant.components.water_heater import WaterHeaterEntityFeature as WH
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.olimpia_sherpa_modbus.const import CONF_ALLOW_WRITES
from custom_components.olimpia_sherpa_modbus.mode_control import Desired

SELECT, ECO, NIGHT = ("select.sherpa_operating_mode", "switch.sherpa_eco",
                      "switch.sherpa_night")
CLIMATE, WATER = "climate.sherpa_heat_pump", "water_heater.sherpa_hot_water"
STB, ECO_BIT, COOL, HEAT, NIGHT_BIT = 1, 2, 4, 8, 16


@pytest.fixture
def mode_writes(fake):
    return lambda: [v for a, v in fake.writes if a == 106]


@pytest.fixture
async def active(hass, config_entry, with_mode_control, mode_unit, advance):
    """Mode control on, ADDR220 = 1, 106 reads 0 (DHW only)."""
    mode_unit.registers[220] = 1
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await advance(10)
    mode_unit.writes.clear()                                    # the adopt-and-keep-alive at start
    return config_entry.runtime_data.coordinator


async def _call(hass, domain, service, entity, **data):
    await hass.services.async_call(domain, service, {"entity_id": entity, **data},
                                   blocking=True)
    await hass.async_block_till_done()


async def _select(hass, option):
    await _call(hass, "select", "select_option", SELECT, option=option)


# -- mode control off --------------------------------------------------------------

async def test_without_the_option_there_is_no_select_and_no_mode_switch(
        hass, setup_integration):
    for entity in (SELECT, ECO, NIGHT):
        assert hass.states.get(entity) is None
    state = hass.states.get(CLIMATE)
    assert state.attributes["mode_control"] == "off"
    assert state.attributes["hvac_modes"] == ["off"]            # exactly as before
    assert state.attributes["supported_features"] == 0
    assert state.attributes["operating_mode"] is None


async def test_the_water_heater_without_the_option_is_read_only(hass, setup_integration):
    state = hass.states.get(WATER)
    assert state.state == "unknown"                            # status 0: standby or DHW only, who knows
    assert state.attributes["current_temperature"] == 22.1      # T3, the DHW tank
    assert state.attributes["temperature"] == 50.0              # register 210
    assert state.attributes["supported_features"] == 0          # no target (not verified), no on/off
    assert (state.attributes["min_temp"], state.attributes["max_temp"]) == (30.0, 55.0)
    assert state.attributes["target_temp_step"] == 0.5


async def test_the_water_heater_does_not_know_standby_from_dhw_only_on_the_panel(
        hass, setup_integration, fake, advance):
    assert hass.states.get(WATER).state == "unknown"
    fake.registers[12] = 2
    await advance(10)
    assert hass.states.get(WATER).state == "heat_pump"
    fake.registers[12] = 0
    await advance(10)
    assert hass.states.get(WATER).state == "unknown"
    fake.registers[12] = 6                                      # a DHW cycle
    await advance(10)
    assert hass.states.get(WATER).state == "heat_pump"


async def test_turning_the_option_off_removes_the_entities(
        hass, config_entry, with_mode_control, mode_unit, advance):
    registry = er.async_get(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(SELECT) and registry.async_get(ECO) and registry.async_get(NIGHT)

    hass.config_entries.async_update_entry(config_entry, options={CONF_ALLOW_WRITES: True})
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert not (registry.async_get(SELECT) or registry.async_get(ECO) or registry.async_get(NIGHT))
    assert registry.async_get(CLIMATE) and registry.async_get(WATER)


# -- ADDR220 = 0 -------------------------------------------------------------------

async def test_at_220_0_the_controls_are_unavailable_and_the_climate_read_only(
        hass, config_entry, with_mode_control, mode_unit):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    for entity in (SELECT, ECO, NIGHT):
        assert hass.states.get(entity).state == "unavailable"
    climate = hass.states.get(CLIMATE)
    assert climate.attributes["mode_control"] == "inactive"
    assert climate.attributes["hvac_modes"] == ["off"]          # the panel's own mode only
    assert climate.attributes["supported_features"] == 0
    assert hass.states.get(WATER).attributes["supported_features"] & (WH.ON_OFF | WH.OPERATION_MODE) == 0

    mode = config_entry.runtime_data.coordinator.mode
    with pytest.raises(ServiceValidationError) as err:
        await mode.async_command(lambda d: d, None)
    assert err.value.translation_key == "mode_control_inactive"
    with pytest.raises(HomeAssistantError):                     # no such mode on offer
        await hass.services.async_call("climate", "set_hvac_mode", {
            "entity_id": CLIMATE, "hvac_mode": "cool"}, blocking=True)
    assert mode_unit.writes == []


# -- active: the select, the switches --------------------------------------------------

async def test_the_select_writes_and_shows_the_read_back(hass, active, fake, mode_writes):
    state = hass.states.get(SELECT)
    assert state.state == "dhw_only"
    assert state.attributes["options"] == ["standby", "dhw_only", "heating", "cooling"]
    await _select(hass, "heating")
    assert mode_writes() == [HEAT] and hass.states.get(SELECT).state == "heating"
    assert fake.registers[106] == HEAT
    await _select(hass, "cooling")
    assert mode_writes()[-1] == COOL                            # heating cleared, never both
    await _select(hass, "dhw_only")
    assert mode_writes()[-1] == 0 and hass.states.get(SELECT).state == "dhw_only"


async def test_eco_and_night_are_bits_of_the_word(hass, active, mode_writes):
    await _select(hass, "heating")
    await _call(hass, "switch", "turn_on", ECO)
    assert mode_writes()[-1] == HEAT | ECO_BIT == 10
    await _call(hass, "switch", "turn_on", NIGHT)
    assert mode_writes()[-1] == 26
    assert hass.states.get(ECO).state == "on" and hass.states.get(NIGHT).state == "on"
    await _call(hass, "switch", "turn_off", ECO)
    assert mode_writes()[-1] == 24 and hass.states.get(ECO).state == "off"
    await _select(hass, "cooling")                             # a mode change keeps night
    assert mode_writes()[-1] == COOL | NIGHT_BIT


async def test_standby_keeps_the_other_bits_and_leaving_it_restores_them(
        hass, active, fake, mode_writes, mode_unit):
    await _select(hass, "heating")
    await _call(hass, "switch", "turn_on", ECO)                 # heating + ECO = 10
    await _select(hass, "standby")
    assert mode_writes()[-1] == 11                              # STB set, the rest kept
    assert hass.states.get(SELECT).state == "standby"
    assert hass.states.get(ECO).state == "on"                   # still truthful
    assert fake.registers[12] == 0                              # the unit is in standby
    await _select(hass, "heating")
    assert mode_writes()[-1] == 10                              # STB cleared, ECO as before
    assert fake.registers[12] == 2


async def test_a_refused_select_leaves_the_entity_where_it_was(hass, active, fake):
    fake.write_mode[106] = "refuse"
    with pytest.raises(HomeAssistantError):
        await _select(hass, "heating")
    assert hass.states.get(SELECT).state == "dhw_only"
    assert active.mode.desired.word == 0


# -- active: the climate -----------------------------------------------------------------

async def test_the_climate_is_a_view_of_106_and_sets_off_heat_cool(
        hass, active, fake, mode_writes):
    state = hass.states.get(CLIMATE)
    assert state.attributes["mode_control"] == "active"
    assert state.attributes["hvac_modes"] == ["off", "heat", "cool"]
    assert state.state == "off" and state.attributes["operating_mode"] == "dhw_only"
    assert state.attributes["hvac_action"] == "idle"            # DHW only: the tank is served
    assert state.attributes["supported_features"] == 384        # TURN_ON | TURN_OFF

    await _call(hass, "climate", "set_hvac_mode", CLIMATE, hvac_mode="heat")
    state = hass.states.get(CLIMATE)
    assert mode_writes()[-1] == HEAT
    assert state.state == "heat" and state.attributes["operating_mode"] == "heating"
    await _call(hass, "climate", "set_hvac_mode", CLIMATE, hvac_mode="cool")
    assert mode_writes()[-1] == COOL and hass.states.get(CLIMATE).state == "cool"
    await _call(hass, "climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    assert mode_writes()[-1] == 0                               # heating and cooling both off
    state = hass.states.get(CLIMATE)
    assert state.state == "off" and state.attributes["operating_mode"] == "dhw_only"


async def test_climate_off_keeps_standby_eco_and_night_and_heat_clears_standby(
        hass, active, mode_writes):
    await _select(hass, "heating")
    await _call(hass, "switch", "turn_on", ECO)
    await _call(hass, "switch", "turn_on", NIGHT)               # 8 | 2 | 16 = 26
    await _call(hass, "climate", "set_hvac_mode", CLIMATE, hvac_mode="off")
    assert mode_writes()[-1] == ECO_BIT | NIGHT_BIT == 18
    await _select(hass, "standby")
    assert mode_writes()[-1] == 19                              # STB + ECO + night
    assert hass.states.get(CLIMATE).attributes["operating_mode"] == "standby"
    await _call(hass, "climate", "set_hvac_mode", CLIMATE, hvac_mode="heat")
    assert mode_writes()[-1] == HEAT | ECO_BIT | NIGHT_BIT      # asking for heat wakes the unit
    await _call(hass, "climate", "turn_off", CLIMATE)
    assert mode_writes()[-1] == 18
    await _call(hass, "climate", "turn_on", CLIMATE)
    assert mode_writes()[-1] == 26


async def test_climate_display_for_each_word(hass, active, fake):
    mode = active.mode
    for word, hvac, operating, action in (
            (STB, "off", "standby", "off"),
            (0, "off", "dhw_only", "idle"),
            (HEAT, "heat", "heating", "idle"),
            (COOL, "cool", "cooling", "idle"),
            (STB | HEAT, "off", "standby", "off"),              # STB wins over a mode bit
            (HEAT | NIGHT_BIT, "heat", "heating", "idle")):
        await mode.async_command(lambda _, w=word: Desired.from_word(w), None)
        await hass.async_block_till_done()
        state = hass.states.get(CLIMATE)
        assert (state.state, state.attributes["operating_mode"],
                state.attributes["hvac_action"]) == (hvac, operating, action), word


async def test_a_dhw_cycle_does_not_hide_heating_or_make_dhw_only_idle_wrongly(
        hass, active, fake, advance):
    await _select(hass, "heating")
    fake.mode_model.dhw_cycle = True                           # sets the heating bit anyway
    await advance(10)
    state = hass.states.get(CLIMATE)
    assert state.state == "heat" and state.attributes["hvac_action"] == "idle"
    assert hass.states.get("sensor.sherpa_water_target").state != "unknown"


# -- the water heater ------------------------------------------------------------------------

async def test_the_water_heater_turns_off_to_standby_and_on_to_the_previous_mode(
        hass, active, fake, mode_writes):
    state = hass.states.get(WATER)
    assert state.state == "heat_pump"                          # DHW only: hot water carries on
    assert state.attributes["supported_features"] & (WH.ON_OFF | WH.OPERATION_MODE)
    await _select(hass, "heating")
    await _call(hass, "switch", "turn_on", NIGHT)
    await _call(hass, "water_heater", "turn_off", WATER)
    assert mode_writes()[-1] == HEAT | NIGHT_BIT | STB == 25
    assert hass.states.get(WATER).state == "off"
    assert hass.states.get(NIGHT).state == "on"                # the switches stay truthful
    await _call(hass, "water_heater", "turn_on", WATER)
    assert mode_writes()[-1] == 24 and hass.states.get(WATER).state == "heat_pump"
    await _call(hass, "water_heater", "set_operation_mode", WATER, operation_mode="off")
    assert mode_writes()[-1] == 25
    await _call(hass, "water_heater", "set_operation_mode", WATER, operation_mode="heat_pump")
    assert mode_writes()[-1] == 24


async def test_the_water_heater_target_needs_a_verified_setpoint(hass, active, fake):
    state = hass.states.get(WATER)
    assert not state.attributes["supported_features"] & WH.TARGET_TEMPERATURE
    with pytest.raises(HomeAssistantError):
        await _call(hass, "water_heater", "set_temperature", WATER, temperature=52)

    active.writes.checks["dhw_setpoint"] = {
        "result": "roundtrip_ok", "identify": 1134, "firmware": "0.57"}
    active.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(WATER).attributes["supported_features"] & WH.TARGET_TEMPERATURE
    await _call(hass, "water_heater", "set_temperature", WATER, temperature=52)
    assert (210, 520) in fake.writes
    assert hass.states.get(WATER).attributes["temperature"] == 52.0
    with pytest.raises(ServiceValidationError):                # off the 0.5 step
        await _call(hass, "water_heater", "set_temperature", WATER, temperature=52.3)


