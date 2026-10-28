"""The entity set: ids, units and classes, and values decoded right.

Long-term statistics are keyed by entity id and break if a unit or state class
changes; entities.json pins those, and test_registers holds the descriptions
to it.
"""

from __future__ import annotations

import pytest
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.olimpia_sherpa_modbus.const import DOMAIN
from custom_components.olimpia_sherpa_modbus.derive import MODE_OPTIONS


async def test_entity_ids_are_claimed_exactly(hass, setup_integration):
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, setup_integration.entry_id)
    assert entries
    # Each id is exactly <domain>.sherpa_<key>: no device-name prefix, no "_2".
    prefix = f"{setup_integration.entry_id}_"
    for entry in entries:
        key = entry.unique_id.removeprefix(prefix)
        assert entry.entity_id == f"{entry.domain}.sherpa_{key}"


@pytest.mark.parametrize(
    ("entity_id", "expected"),
    [
        ("sensor.sherpa_water_in", "25.8"),
        ("sensor.sherpa_water_out", "25.1"),
        ("sensor.sherpa_dhw_tank", "22.1"),
        ("sensor.sherpa_outdoor_air", "13.2"),
        ("sensor.sherpa_water_delta", "-0.7"),
        ("sensor.sherpa_cooling_setpoint", "15.0"),
        ("sensor.sherpa_cooling_eco_setpoint", "18.0"),
        ("sensor.sherpa_heating_setpoint", "35.0"),
        ("sensor.sherpa_heating_eco_setpoint", "30.0"),
        ("sensor.sherpa_dhw_setpoint", "50.0"),
        ("sensor.sherpa_legionella_setpoint", "65.0"),
        ("sensor.sherpa_dhw_hysteresis", "10.0"),
        ("sensor.sherpa_compressor_seconds", "132958"),
        ("sensor.sherpa_compressor_hours", "36.93"),
        ("sensor.sherpa_legionella_start_minutes", "60"),
        ("sensor.sherpa_legionella_start", "01:00"),
        ("sensor.sherpa_mode", "standby"),
        ("sensor.sherpa_error_code", "none"),
        ("sensor.sherpa_override_code", "none"),
        ("sensor.sherpa_pump_step", "1"),
        ("sensor.sherpa_pump_duty", "5"),
        ("sensor.sherpa_inputs", "895"),
        ("sensor.sherpa_identify_code", "1134"),
        ("sensor.sherpa_remote_controls", "display"),
        ("sensor.sherpa_dhw_source", "sensor"),
        ("sensor.sherpa_legionella_mode", "electric_heaters"),
        # register 8 = 895: bit 0 set (inverted: no flow), bit 7 clear (TA demand)
        ("binary_sensor.sherpa_in_flow", "off"),
        ("binary_sensor.sherpa_in_ta", "on"),
        ("binary_sensor.sherpa_power", "off"),
        ("binary_sensor.sherpa_error", "off"),
        ("binary_sensor.sherpa_mode_pending", "off"),
        ("binary_sensor.sherpa_out_pump", "off"),
        ("binary_sensor.sherpa_heating_curve_enabled", "on"),
    ],
)
async def test_values_decode_as_on_the_unit(hass, setup_integration, entity_id, expected):
    assert hass.states.get(entity_id).state == expected


async def test_compressor_running_is_unknown_until_two_counter_samples(hass, setup_integration):
    # One counter reading is not a rate. Unknown beats a guess.
    assert hass.states.get("binary_sensor.sherpa_compressor_running").state == "unknown"


async def test_mode_is_an_enum_with_translated_states(hass, setup_integration):
    state = hass.states.get("sensor.sherpa_mode")
    assert state.attributes["options"] == list(MODE_OPTIONS)
    assert state.attributes["friendly_name"] == "Sherpa Mode"


async def test_absent_probes_and_other_models_registers_get_no_entity(hass, setup_integration):
    # T5-T8 read -1/-501 on this unit; the DHW counters exist on Aquadue only.
    for key in ("dhw_compressor_temp", "dhw_condenser_temp", "dhw_evaporator_temp",
                "solar_temp", "dhw_compressor_seconds", "dhw_pump_seconds"):
        assert hass.states.get(f"sensor.sherpa_{key}") is None, key


async def test_a_probe_wired_up_later_appears(hass, setup_integration, fake, freezer):
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    fake.registers[7] = 452   # T8 solar probe now reads 45.2 degC
    freezer.tick(31)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("sensor.sherpa_solar_temp").state == "45.2"


async def test_raw_words_are_diagnostic_and_parameters_mostly_hidden(hass, setup_integration):
    registry = er.async_get(hass)
    assert registry.async_get("sensor.sherpa_status").entity_category is EntityCategory.DIAGNOSTIC
    curve = registry.async_get("sensor.sherpa_heating_curve_max_water")
    assert curve.entity_category is EntityCategory.DIAGNOSTIC and curve.disabled_by is not None
    assert registry.async_get("sensor.sherpa_water_in").entity_category is None


async def test_error_code_lists_active_codes_with_descriptions(hass, setup_integration, fake,
                                                               freezer):
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    fake.registers[100] = 64        # E07, as seen 11 times in October
    fake.registers[102] = 32        # OR06, defrost
    freezer.tick(11)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    error = hass.states.get("sensor.sherpa_error_code")
    assert error.state == "E07"
    assert error.attributes["descriptions"] == {"E07": "UE communication error"}
    assert hass.states.get("binary_sensor.sherpa_error").state == "on"
    assert hass.states.get("sensor.sherpa_override_code").state == "OR06"
    assert hass.states.get("binary_sensor.sherpa_defrost").state == "on"
    assert hass.states.get("binary_sensor.sherpa_warning").state == "on"


async def test_device_describes_the_unit(hass, setup_integration):
    device = dr.async_get(hass).async_get_device({(DOMAIN, setup_integration.entry_id)})
    assert device.manufacturer == "Olimpia Splendid"
    assert device.model == "SHERPA S2 BIG / SHERPA S2 14T"
    assert device.model_id == "1134" and device.sw_version == "0.57"
    assert device.name == "Sherpa"
