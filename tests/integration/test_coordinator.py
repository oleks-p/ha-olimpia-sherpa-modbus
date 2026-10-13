"""Polling over time: tiers, stall tolerance, the block fallback, glitch filtering."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.olimpia_sherpa_modbus.const import CONF_UNAVAILABLE_AFTER


async def _advance(hass, freezer, seconds: float) -> None:
    """Move time forward in 10 s polls, letting each one complete."""
    remaining = seconds
    while remaining > 0:
        step = min(10, remaining)
        freezer.tick(timedelta(seconds=step))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        remaining -= step


def _reads_since(fake, mark: int) -> set[int]:
    return {address for _unit, _fc, address, _count in fake.requests[mark:]}


async def test_tiers_poll_at_their_own_rates(hass, setup_integration, fake, freezer):
    mark = len(fake.requests)
    await _advance(hass, freezer, 10)
    assert _reads_since(fake, mark) == {8, 12, 100, 105, 388}   # control tier only

    mark = len(fake.requests)
    await _advance(hass, freezer, 20)                 # t = 30 s
    assert 0 in _reads_since(fake, mark)              # process tier (temperatures)
    mark = len(fake.requests)
    await _advance(hass, freezer, 30)                 # t = 60 s
    assert 270 in _reads_since(fake, mark)            # counter tier
    assert 206 not in _reads_since(fake, mark)        # setpoints: every 10 minutes


async def test_control_tier_is_five_requests(hass, setup_integration, fake, freezer):
    mark = len(fake.requests)
    await _advance(hass, freezer, 10)
    # 8 / 12 / 100-102 / 105 / 388: five runs, so five requests -- the unit
    # refuses any read that spans a gap.
    assert len(fake.requests) - mark == 5


async def test_slow_values_survive_fast_polls(hass, setup_integration, freezer):
    await _advance(hass, freezer, 60)
    assert hass.states.get("sensor.sherpa_dhw_setpoint").state == "50.0"
    assert hass.states.get("sensor.sherpa_identify_code").state == "1134"


async def test_a_stall_keeps_entities_then_an_outage_does_not(
        hass, setup_integration, fake, freezer):
    fake.stall(10_000)
    await _advance(hass, freezer, 60)       # a long stall, but under 120 s
    state = hass.states.get("sensor.sherpa_water_in")
    assert state.state == "25.8"            # last value held, still available

    await _advance(hass, freezer, 80)       # now 140 s without an answer
    assert hass.states.get("sensor.sherpa_water_in").state == "unavailable"

    fake.stall(0)
    await _advance(hass, freezer, 10)
    assert hass.states.get("sensor.sherpa_water_in").state == "25.8"
    assert hass.states.get("sensor.sherpa_read_failures").state != "0"


async def test_unavailable_after_is_an_option(hass, freezer, config_entry, modbus_clients, fake):
    hass.config_entries.async_update_entry(config_entry, options={CONF_UNAVAILABLE_AFTER: 30})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    fake.stall(10_000)
    await _advance(hass, freezer, 40)
    assert hass.states.get("sensor.sherpa_water_in").state == "unavailable"


async def test_a_refused_block_falls_back_to_single_reads(
        hass, setup_integration, fake, freezer):
    # A firmware without register 101 would refuse the whole 100-102 read.
    del fake.registers[101]
    await _advance(hass, freezer, 10)
    coordinator = setup_integration.runtime_data.coordinator
    assert coordinator.split_blocks == ["control 100..102"]
    assert hass.states.get("sensor.sherpa_alarm_1").state == "0"       # still read
    assert hass.states.get("sensor.sherpa_alarm_2").state == "unknown"  # the missing one
    assert hass.states.get("sensor.sherpa_override").state == "0"


async def test_an_all_zero_inputs_word_is_a_glitch(hass, setup_integration, fake, freezer):
    assert hass.states.get("binary_sensor.sherpa_in_ta").state == "on"
    fake.registers[8] = 0           # "every input active at once"
    await _advance(hass, freezer, 10)
    assert hass.states.get("sensor.sherpa_inputs").state == "0"         # raw word, as read
    assert hass.states.get("binary_sensor.sherpa_in_flow").state == "off"   # held
    assert hass.states.get("binary_sensor.sherpa_in_ta").state == "on"
    assert setup_integration.runtime_data.coordinator.inputs_glitches == 1

    fake.registers[8] = 894         # flow switch closes
    await _advance(hass, freezer, 10)
    assert hass.states.get("binary_sensor.sherpa_in_flow").state == "on"


async def test_compressor_running_follows_the_counter(hass, setup_integration, fake, freezer):
    def run_for(seconds: int) -> None:
        total = (fake.registers[270] << 16 | fake.registers[271]) + seconds
        fake.registers[270], fake.registers[271] = total >> 16, total & 0xFFFF

    for _ in range(3):              # compressor on: +60 s of counter per minute
        await _advance(hass, freezer, 50)
        run_for(60)
        await _advance(hass, freezer, 10)
    running = hass.states.get("binary_sensor.sherpa_compressor_running")
    assert running.state == "on"
    assert float(hass.states.get("sensor.sherpa_compressor_rate").state) >= 55

    await _advance(hass, freezer, 180)  # compressor off: the counter stands still
    assert hass.states.get("binary_sensor.sherpa_compressor_running").state == "off"
