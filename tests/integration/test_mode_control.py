"""Mode control: the desired word, its keep-alive, the hand-over and the repair issues.

Against the FakeSherpa with its mode model (106, ADDR220 and E09 as P6 found
them) and the frozen clock the fixtures use, so 255 s of E09 budget costs no
time. The guard in conftest fails any test in which ADDR220 is ever written.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.olimpia_sherpa_modbus.const import (
    CONF_ALLOW_WRITES,
    CONF_MODE_CONTROL,
    CONF_UNAVAILABLE_AFTER,
    DOMAIN,
    E09_DETECT,
    E09_PERIOD,
)
from custom_components.olimpia_sherpa_modbus.mode_control import STORE_KEY, Desired

HEATING, COOLING, ECO, NIGHT, STANDBY = 8, 4, 2, 16, 1


@pytest.fixture
def mode_writes(fake):
    """Every write of 106 so far, as the words."""
    return lambda: [v for a, v in fake.writes if a == 106]


def _issues(hass, entry) -> set[str]:
    registry = ir.async_get(hass)
    return {name for name in ("serial_control_unmanaged", "mode_keepalive_lost",
                              "mode_not_applied")
            if registry.async_get_issue(DOMAIN, f"{name}_{entry.entry_id}")}


def _stored(hass_storage, entry, **desired):
    hass_storage[STORE_KEY] = {"version": 1, "minor_version": 1, "key": STORE_KEY,
                               "data": {entry.entry_id: {"mode": "dhw_only", "standby": False,
                                                          "eco": False, "night": False,
                                                          **desired}}}


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry.runtime_data.coordinator.mode


async def _command(hass, mode, change):
    await mode.async_command(change, None)
    await hass.async_block_till_done()


# -- the pure part ---------------------------------------------------------------

def test_desired_is_a_word_and_back():
    assert Desired("heating", eco=True).word == 10
    assert Desired("heating", standby=True, night=True).word == 25
    assert Desired().word == 0 and Desired().operating == "dhw_only"
    assert Desired("cooling", standby=True).operating == "standby"
    for word in (0, 1, 3, 4, 8, 9, 10, 24, 25, 26):
        assert Desired.from_word(word).word == word
    assert Desired.load({"mode": "heating"}) is None          # a broken store is no store
    assert Desired.load({"mode": "x", "standby": 0, "eco": 0, "night": 0}) is None


# -- off, and the panel in charge -------------------------------------------------

@pytest.mark.parametrize("options", [{}, {CONF_ALLOW_WRITES: True},
                                     {CONF_MODE_CONTROL: True}])
async def test_without_mode_control_nothing_is_written_and_the_repair_shows(
        hass, config_entry, modbus_clients, mode_unit, advance, mode_writes, options):
    hass.config_entries.async_update_entry(config_entry, options=options)
    fake = mode_unit
    fake.registers[220] = 1
    mode = await _setup(hass, config_entry)
    assert mode.state == "off"                  # (mode control without writes is off too)
    await advance(50)
    assert _issues(hass, config_entry) == set()               # not yet: 60 s debounce
    await advance(30)
    assert _issues(hass, config_entry) == {"serial_control_unmanaged"}
    await advance(300)
    assert fake.writes == [] and fake.e09_episodes != []     # nothing keeps it fed

    fake.registers[220] = 0
    await advance(10)
    assert _issues(hass, config_entry) == set()


async def test_at_220_0_nothing_is_written_whatever_the_panel_does(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    fake = mode_unit
    mode = await _setup(hass, config_entry)
    assert mode.state == "inactive"
    for status in (0, 2, 1, 2 | 128, 98, 0):
        fake.registers[12] = status
        await advance(60)
    assert fake.writes == []
    assert mode.panel == ("off", False) and mode.desired is None
    assert _issues(hass, config_entry) == set()


# -- the hand-over ---------------------------------------------------------------

@pytest.mark.parametrize(("status", "stored", "expected"), [
    (2 | 128, {}, HEATING | NIGHT),                    # panel: heating + night
    (2 | 128, {"eco": True}, HEATING | NIGHT | ECO),   # ECO is invisible at 220 = 0: the store
    (0, {}, STANDBY),                                  # panel off: standby (DHW only is never inferred)
    (0, {"eco": True, "mode": "cooling"}, STANDBY | ECO),
    (1, {}, COOLING),
    (98, {}, HEATING),                                 # heating, pending
])
async def test_the_hand_over_takes_the_panels_mode(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes, hass_storage, status, stored, expected):
    fake = mode_unit
    if stored:
        _stored(hass_storage, config_entry, **stored)
    fake.registers[12] = status
    mode = await _setup(hass, config_entry)
    events = []
    hass.bus.async_listen(f"{DOMAIN}_parameter_written", events.append)
    await advance(30)
    assert mode_writes() == []

    fake.registers[220] = 1                             # the person sets ADDR220 = 1
    await advance(10)
    assert mode_writes() == [expected]                  # at once, not after 60 s
    assert mode.desired.word == expected and mode.state == "active"
    assert len(events) == 1 and events[0].data["new"] == expected
    assert fake.registers[106] == expected


async def test_after_the_flip_it_writes_once_a_minute_and_the_unit_never_alarms(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    fake.registers[12] = 2
    mode = await _setup(hass, config_entry)
    events = []
    hass.bus.async_listen(f"{DOMAIN}_parameter_written", events.append)
    await advance(20)
    fake.registers[220] = 1
    await advance(10)
    assert len(mode_writes()) == 1
    await advance(600)
    assert 10 <= len(mode_writes()) - 1 <= 11           # one per 60 s, not more
    assert fake.e09_episodes == []                      # the unit never raised E09
    assert _issues(hass, config_entry) == set()
    assert len(events) == 1                             # the keep-alive is silent
    assert len(mode.coordinator.writes.log) == 1
    assert mode.keepalive_writes == mode.writes_total - 1
    assert mode.max_gap_s <= 70


async def test_a_flip_back_to_0_stops_the_writes(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    await _setup(hass, config_entry)
    fake.registers[220] = 1
    await advance(70)
    count = len(mode_writes())
    fake.registers[220] = 0                             # handed back on the panel
    await advance(300)
    assert len(mode_writes()) in (count, count + 1)     # at most the tick already due
    after = len(mode_writes())
    await advance(300)
    assert len(mode_writes()) == after


# -- setup ------------------------------------------------------------------------

async def test_setup_at_220_1_writes_the_stored_mode_at_once(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, mode_writes,
        hass_storage, caplog):
    fake = mode_unit
    _stored(hass_storage, config_entry, mode="heating", eco=True)
    fake.registers[220] = 1
    fake.registers[106] = 0                              # a rebooted unit, or somebody else
    with caplog.at_level(logging.WARNING):
        mode = await _setup(hass, config_entry)
    assert mode_writes() == [HEATING | ECO] and mode.state == "active"
    assert sum("holds mode word 0" in r.message for r in caplog.records) == 1


async def test_setup_at_220_1_with_the_same_word_is_silent(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, mode_writes,
        hass_storage, caplog):
    fake = mode_unit
    _stored(hass_storage, config_entry, mode="heating")
    fake.registers[220], fake.registers[106] = 1, HEATING
    events = []
    hass.bus.async_listen(f"{DOMAIN}_parameter_written", events.append)
    with caplog.at_level(logging.WARNING):
        await _setup(hass, config_entry)
    assert mode_writes() == [HEATING] and events == []
    assert not [r for r in caplog.records if "holds mode word" in r.message]


async def test_setup_at_220_1_with_an_empty_store_adopts_106(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, mode_writes,
        advance):
    fake = mode_unit
    fake.registers[220], fake.registers[106] = 1, HEATING | ECO
    mode = await _setup(hass, config_entry)
    assert mode_writes() == []                           # adopted, nothing written yet
    assert mode.desired == Desired("heating", eco=True)
    await advance(10)
    assert mode_writes() == [HEATING | ECO]              # the keep-alive, as due


async def test_a_rebooted_unit_adopted_as_dhw_only(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, mode_writes):
    mode_unit.registers[220] = 1                          # 106 reads 0: the safe value
    mode = await _setup(hass, config_entry)
    assert mode.desired == Desired("dhw_only") and mode.desired.operating == "dhw_only"


async def test_setup_at_220_0_keeps_the_store_and_writes_nothing(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, hass_storage):
    _stored(hass_storage, config_entry, mode="cooling")
    mode = await _setup(hass, config_entry)
    assert mode.desired == Desired("cooling") and mode_unit.writes == []


async def test_restart_restores_the_desired_mode_and_writes_once_more_at_unload(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, mode_writes,
        hass_storage, advance):
    fake = mode_unit
    fake.registers[220] = 1
    mode = await _setup(hass, config_entry)
    await _command(hass, mode, lambda _: Desired("cooling", eco=True, night=True))
    await advance(20)
    before = len(mode_writes())
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert len(mode_writes()) == before + 1               # the last write, a full 255 s ahead
    assert mode_writes()[-1] == COOLING | ECO | NIGHT     # and no standby write
    assert hass_storage[STORE_KEY]["data"][config_entry.entry_id] == {
        "mode": "cooling", "standby": False, "eco": True, "night": True}

    fake.registers[106] = 0                               # the unit forgot (a reboot)
    mode = await _setup(hass, config_entry)
    assert mode.desired == Desired("cooling", eco=True, night=True)
    assert mode_writes()[-1] == COOLING | ECO | NIGHT
    assert fake.registers[106] == COOLING | ECO | NIGHT


async def test_removing_the_entry_forgets_the_mode(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, hass_storage):
    mode_unit.registers[220] = 1
    await _setup(hass, config_entry)
    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.entry_id not in hass_storage[STORE_KEY]["data"]


# -- the link ---------------------------------------------------------------------

async def _active(hass, entry, fake, advance):
    fake.registers[220] = 1
    fake.registers[12] = 2
    mode = await _setup(hass, entry)
    await advance(10)
    return mode


async def test_a_stall_of_30_s_costs_nothing(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await advance(50)                                       # the next write is due inside the stall
    fake.stall(10_000)
    await advance(30)
    assert hass.states.get("sensor.sherpa_water_in").state != "unavailable"
    assert mode.state == "active"                           # stalled only after 60 s
    fake.stall(0)
    count = len(mode_writes())
    await advance(10)
    assert len(mode_writes()) > count                       # the retry went out at once
    assert mode.state == "active"
    assert _issues(hass, config_entry) == set()
    assert fake.e09_episodes == [] and not mode.late_events


async def test_no_write_for_260_s_raises_the_repair_and_the_next_write_clears_it(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes, caplog):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await advance(60)
    fake.stall(10_000)
    await advance(240)
    assert "mode_keepalive_lost" not in _issues(hass, config_entry)
    await advance(30)                                       # 270 s since the last write
    assert "mode_keepalive_lost" in _issues(hass, config_entry)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"mode_keepalive_lost_{config_entry.entry_id}")
    assert int(issue.translation_placeholders["seconds"]) > 255

    fake.stall(0)
    with caplog.at_level(logging.WARNING):
        await advance(10)
    assert "mode_keepalive_lost" not in _issues(hass, config_entry)
    assert len(mode.late_events) == 1
    event = mode.late_events[0]
    assert event["gap_s"] >= 260 and event["expected_pulses"] == 1
    assert {"status_before", "outputs_before", "compressor_seconds_before",
            "compressor_seconds_after", "compressor_running_before"} <= set(event)
    assert any("E09" in r.message for r in caplog.records)
    assert mode.max_gap_s >= 260


async def test_nothing_is_flagged_before_the_first_write_after_a_late_flip(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    # Hours at 220 = 0 must not count as "no write for hours" once it turns to 1.
    fake = mode_unit
    await _setup(hass, config_entry)
    await advance(3600)
    fake.registers[220] = 1
    await advance(10)
    assert _issues(hass, config_entry) == set()


# -- commands ---------------------------------------------------------------------

async def test_a_failed_command_restores_the_previous_mode(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    before = mode.desired
    fake.write_mode[106] = "refuse"
    with pytest.raises(HomeAssistantError):
        await _command(hass, mode, lambda _: Desired("cooling"))
    assert mode.desired == before
    fake.write_mode[106] = "ignore"                         # acknowledged, not applied
    with pytest.raises(HomeAssistantError):
        await _command(hass, mode, lambda _: Desired("cooling"))
    assert mode.desired == before
    fake.write_mode[106] = "accept"
    await advance(60)
    assert mode_writes()[-1] == before.word                 # the timer kept the old word
    assert fake.registers[106] == before.word


async def test_a_command_is_refused_unless_active(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit):
    mode = await _setup(hass, config_entry)                  # 220 = 0
    with pytest.raises(ServiceValidationError) as err:
        await mode.async_command(lambda d: d, None)
    assert err.value.translation_key == "mode_control_inactive"
    assert mode_unit.writes == []


# -- the unit not holding it ---------------------------------------------------------

async def test_a_word_the_unit_lost_is_rewritten_and_announced_once(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await _command(hass, mode, lambda _: Desired("heating"))
    events = []
    hass.bus.async_listen(f"{DOMAIN}_parameter_written", events.append)
    fake.registers[106] = 0                                  # the unit rebooted
    await advance(20)
    assert fake.registers[106] == HEATING and mode.desired.word == HEATING
    assert len(events) == 1 and events[0].data["old"] == 0 and events[0].data["new"] == HEATING


async def test_a_unit_that_ignores_the_word_raises_not_applied_after_three_ticks(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await _command(hass, mode, lambda _: Desired("heating"))
    events = []
    hass.bus.async_listen(f"{DOMAIN}_parameter_written", events.append)
    fake.write_mode[106] = "ignore"
    fake.registers[106] = 0
    await advance(20)
    assert "mode_not_applied" not in _issues(hass, config_entry)
    await advance(30)
    assert "mode_not_applied" in _issues(hass, config_entry)
    assert len(events) == 1                                  # not one per retry

    fake.write_mode[106] = "accept"
    await advance(20)
    assert "mode_not_applied" not in _issues(hass, config_entry)
    assert fake.registers[106] == HEATING


# -- the research action ----------------------------------------------------------------

async def _research(hass, value=HEATING):
    return await hass.services.async_call(DOMAIN, "write_mode_command", {"value": value},
                                          blocking=True, return_response=True)


async def test_the_research_action_is_refused_while_active_or_stalled(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    count = len(mode_writes())
    with pytest.raises(ServiceValidationError) as err:
        await _research(hass)
    assert err.value.translation_key == "mode_control_active"
    fake.stall(10_000)
    await advance(80)
    assert mode.state == "stalled"
    with pytest.raises(ServiceValidationError):
        await _research(hass)
    fake.stall(0)
    await advance(10)
    assert mode.state == "active" and len(mode_writes()) > count


async def test_the_research_action_works_while_mode_control_is_inactive(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit):
    await _setup(hass, config_entry)                         # 220 = 0: inactive
    result = await _research(hass)
    assert result["written"] == HEATING and result["read_back"] == HEATING


# -- diagnostics ------------------------------------------------------------------------

async def test_diagnostics_show_the_controller(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    from custom_components.olimpia_sherpa_modbus.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    mode = await _active(hass, config_entry, mode_unit, advance)
    await advance(120)
    diag = (await async_get_config_entry_diagnostics(hass, config_entry))["mode_control"]
    assert diag["enabled"] is True and diag["state"] == "active"
    assert diag["desired"] == {"mode": "dhw_only", "standby": False, "eco": False,
                               "night": False, "word": 0}
    assert diag["polled_106"] == 0 and diag["remote_controls"] == 1
    assert diag["writes_total"] == mode.writes_total >= 3
    assert diag["keepalive_writes"] == mode.keepalive_writes
    assert diag["max_gap_s"] <= 70 and diag["late_events"] == [] and diag["issues"] == []
    assert diag["last_ok_write_at"]


# -- review findings -----------------------------------------------------------------------

async def _spin(times: int = 30) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


async def _tick_by(hass, freezer, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await _spin()


def _blocking_write(mode, release: asyncio.Event, *, fail: bool = False):
    """Make the controller's first write wait on ``release`` (then go on, or fail)."""
    gate = mode.coordinator.writes
    real, calls = gate.async_mode_write, []

    async def slow(word, **kwargs):
        calls.append(word)
        if len(calls) == 1:
            await release.wait()
            if fail:
                raise HomeAssistantError("write failed")
        return await real(word, **kwargs)

    gate.async_mode_write = slow
    return calls


# 1. ADDR220 is read from the unit before every write

async def test_a_keepalive_never_writes_after_220_was_set_back_but_the_cache_is_stale(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes, freezer):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    count = len(mode_writes())
    fake.registers[220] = 0                      # a person, on the panel; no poll has seen it
    assert mode.state == "active"                # the cache says 1
    freezer.tick(timedelta(seconds=61))          # a keep-alive is due
    await mode._tick()
    assert len(mode_writes()) == count           # ... and 220 read 0 on the unit: nothing written
    assert mode.state == "inactive"              # the cache was told


async def test_a_command_never_writes_after_220_was_set_back(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    before, count = mode.desired, len(mode_writes())
    fake.registers[220] = 0
    with pytest.raises(ServiceValidationError) as err:
        await mode.async_command(lambda _: Desired("heating"), None)
    assert err.value.translation_key == "mode_control_inactive"
    assert len(mode_writes()) == count and mode.desired == before


async def test_the_final_write_never_goes_out_after_220_was_set_back(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    await _active(hass, config_entry, fake, advance)
    count = len(mode_writes())
    fake.registers[220] = 0
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert len(mode_writes()) == count


async def test_the_gate_can_be_made_to_check_220_but_the_research_action_does_not(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit):
    await _setup(hass, config_entry)                         # 220 = 0
    gate = config_entry.runtime_data.coordinator.writes
    with pytest.raises(ServiceValidationError):
        await gate.async_mode_write(HEATING, keepalive=True, expect_serial=True)
    assert mode_unit.writes == []
    assert (await _research(hass))["read_back"] == HEATING   # the research action stays as it was


# 2. the hand-over needs a confirmed flip and a fresh snapshot

async def test_a_glitched_read_of_220_is_not_a_hand_over(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await _command(hass, mode, lambda _: Desired("heating"))
    fake.registers[220] = 0                      # one poll reads 0 ...
    await advance(10)
    fake.registers[220] = 1                      # ... and then 1 again
    await advance(70)
    assert mode.desired == Desired("heating")
    assert all(not w & STANDBY for w in mode_writes())       # hot water was never stopped
    assert fake.registers[106] == HEATING


async def test_a_flip_in_the_first_poll_after_setup_keeps_the_stored_mode(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes, hass_storage):
    fake = mode_unit
    _stored(hass_storage, config_entry, mode="cooling")
    fake.registers[12] = 2                       # the panel has heating
    mode = await _setup(hass, config_entry)
    fake.registers[220] = 1
    await advance(20)                            # the first poll at 1 is no hand-over
    assert mode.desired == Desired("cooling") and mode_writes() == [COOLING]


async def test_an_old_panel_snapshot_is_not_used(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    fake.registers[12] = 2 | 128
    mode = await _setup(hass, config_entry)
    await advance(30)
    assert mode.panel == ("heating", True)
    mode._panel_at -= 100                        # taken long ago: reads have been failing
    fake.registers[220] = 1
    await advance(10)
    # no fresh snapshot, nothing stored: 106 as read (0, DHW only), not the panel's 24
    assert mode.desired == Desired("dhw_only") and mode_writes() == [0]


async def test_a_snapshot_is_used_once(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    fake.registers[12] = 2
    mode = await _setup(hass, config_entry)
    await advance(30)
    fake.registers[220] = 1
    await advance(10)
    assert mode_writes() == [HEATING]
    await _command(hass, mode, lambda _: Desired("cooling"))
    fake.registers[220] = 0
    await advance(10)
    fake.registers[220] = 1                      # a glitch-sized blip: one poll at 0
    await advance(10)
    assert mode.desired == Desired("cooling")


# 3. the controller does not outlive a failed setup

async def test_a_failed_setup_leaves_no_timer_behind(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    fake = mode_unit
    fake.registers[220] = 1
    with patch.object(hass.config_entries, "async_forward_entry_setups",
                      AsyncMock(side_effect=RuntimeError("boom"))):
        assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    mode = config_entry.runtime_data.coordinator.mode
    assert mode._stopped
    fake.writes.clear()
    await advance(300)
    assert [w for w in fake.writes if w[0] == 106] == []


async def test_setup_does_not_wait_for_the_first_write(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, hass_storage):
    _stored(hass_storage, config_entry, mode="heating")
    mode_unit.registers[220] = 1
    release = asyncio.Event()
    started = asyncio.Event()
    real = None

    async def slow(self, word, **kwargs):
        started.set()
        await release.wait()
        return await real(self, word, **kwargs)

    from custom_components.olimpia_sherpa_modbus.writes import WriteGate

    real = WriteGate.async_mode_write
    with patch.object(WriteGate, "async_mode_write", slow):
        setup = hass.async_create_task(hass.config_entries.async_setup(config_entry.entry_id))
        await _spin(300)
        assert started.is_set()                                  # the first write has begun ...
        assert setup.done() and setup.result()                   # ... and setup did not wait for it
        assert config_entry.state is ConfigEntryState.LOADED
        release.set()
        await hass.async_block_till_done()


# 4. stopping waits for work in flight, and nothing writes after it

async def test_unload_waits_for_a_command_in_flight_and_refuses_new_ones(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    release = asyncio.Event()
    calls = _blocking_write(mode, release)
    command = hass.async_create_task(mode.async_command(lambda _: Desired("heating"), None))
    await _spin()
    unload = hass.async_create_task(hass.config_entries.async_unload(config_entry.entry_id))
    await _spin()
    assert not unload.done()                              # waiting for the command's write
    with pytest.raises(ServiceValidationError):           # and no new command gets in
        await mode.async_command(lambda _: Desired("cooling"), None)
    release.set()
    assert await unload
    await command
    assert calls == [HEATING, HEATING]                    # the command, then the final write
    assert fake.registers[106] == HEATING
    fake.writes.clear()
    await advance(120)
    assert fake.writes == []                              # nothing writes after the unload


# 5. the rollback

async def test_a_write_that_landed_with_a_failed_read_back_rolls_back_and_counts_as_sent(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes, freezer):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    before = mode.desired
    freezer.tick(timedelta(seconds=5))
    sent = mode.last_sent
    fake.stall_on(106, 2)                                  # the read-back, and its one retry
    with pytest.raises(HomeAssistantError):
        await mode.async_command(lambda _: Desired("heating"), None)
    assert fake.registers[106] == HEATING                  # the unit did get it
    assert mode.desired == before and mode.last_sent > sent    # so it is fed, and rolled back
    await advance(20)                                      # a poll sees the mismatch, a tick fixes it
    assert fake.registers[106] == before.word              # the timer put the old word back


async def test_the_read_back_is_retried_once_before_rolling_back(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    fake.stall_on(106, 1)
    await _command(hass, mode, lambda _: Desired("heating"))
    assert mode.desired == Desired("heating") and fake.registers[106] == HEATING


async def test_a_hand_over_during_a_command_is_not_rolled_back(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    release = asyncio.Event()
    _blocking_write(mode, release, fail=True)
    command = hass.async_create_task(mode.async_command(lambda _: Desired("heating"), None))
    await _spin()
    mode.panel, mode._panel_at = ("cooling", False), time.monotonic()
    mode._hand_over(time.monotonic())                      # arrives while the write is in flight
    release.set()
    with pytest.raises(HomeAssistantError):
        await command
    assert mode.desired == Desired("cooling") and mode._handover   # the hand-over stands
    await advance(10)
    assert fake.registers[106] == COOLING


async def test_a_hand_over_during_a_command_keeps_its_announcement(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    release = asyncio.Event()
    _blocking_write(mode, release)
    command = hass.async_create_task(mode.async_command(lambda _: Desired("heating"), None))
    await _spin()
    mode.panel, mode._panel_at = ("cooling", True), time.monotonic()
    mode._hand_over(time.monotonic())
    release.set()
    await command
    assert mode.desired == Desired("cooling", night=True) and mode._handover
    await advance(10)
    assert fake.registers[106] == COOLING | NIGHT and not mode._handover


# 6. thresholds follow the measured E09, which a 10 s poll can miss

async def test_the_thresholds_sit_under_the_measured_period():
    assert E09_DETECT < 253.6 <= E09_PERIOD < 255


async def test_the_poll_misses_e09_which_only_the_episode_record_shows(
        hass, config_entry, modbus_clients, mode_unit, advance):
    fake = mode_unit
    fake.registers[220] = 1
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    for _ in range(40):
        await advance(10)
        assert hass.states.get("sensor.sherpa_alarm_1").state == "0"
    assert fake.e09_episodes                               # it happened, unseen


async def test_a_gap_of_250_s_is_already_a_miss(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        freezer):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    fake.stall(10_000)
    await advance(40)                                      # past the next keep-alive
    sent = mode.last_sent
    await _tick_by(hass, freezer, E09_DETECT - (time.monotonic() - sent))   # exactly 250 s
    assert time.monotonic() - sent == pytest.approx(E09_DETECT)
    assert "mode_keepalive_lost" not in _issues(hass, config_entry)
    freezer.tick(timedelta(seconds=2))                     # 252 s: E09 comes at 253.6, so this
    mode._evaluate_issues(time.monotonic())                # is already a miss (a 255 s limit would not)
    assert time.monotonic() - sent == pytest.approx(E09_DETECT + 2)

    assert "mode_keepalive_lost" in _issues(hass, config_entry)
    fake.stall(0)
    await advance(10)
    assert len(mode.late_events) == 1 and mode.late_events[0]["gap_s"] >= E09_DETECT


# 7. a write the unit got counts as fed

async def test_a_write_whose_read_back_failed_is_not_retried_every_tick(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await advance(50)                                      # the next keep-alive is due
    count = len(mode_writes())
    fake.stall_on(106, 2)                                  # its read-back fails twice
    await advance(10)
    assert len(mode_writes()) == count + 1
    assert mode.last_sent == time.monotonic()              # the unit got it: fed
    await advance(40)
    assert len(mode_writes()) == count + 1                 # not rewritten on every tick
    assert "mode_keepalive_lost" not in _issues(hass, config_entry)


# the missing tests

async def test_home_assistant_stopping_writes_the_mode_once_more(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes, hass_storage):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await _command(hass, mode, lambda _: Desired("cooling", eco=True))
    count = len(mode_writes())
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    assert len(mode_writes()) == count + 1 and mode_writes()[-1] == COOLING | ECO
    assert hass_storage[STORE_KEY]["data"][config_entry.entry_id]["mode"] == "cooling"
    assert mode._stopping


async def test_a_keepalive_and_a_command_wait_behind_a_write_check(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes, freezer):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await advance(50)                                      # a keep-alive is nearly due
    release = asyncio.Event()

    async def hold(_seconds):
        await release.wait()                               # the check's 30 s hold

    with patch("custom_components.olimpia_sherpa_modbus.writes._wait", hold):
        check = hass.async_create_task(hass.services.async_call(
            DOMAIN, "verify_write", {"register": "heating_setpoint", "hold_seconds": 30},
            blocking=True, return_response=True))
        await _spin()
        count = len(mode_writes())
        for _ in range(8):                                 # 80 s of ticks behind the check
            await _tick_by(hass, freezer, 10)
        command = hass.async_create_task(mode.async_command(lambda _: Desired("heating"), None))
        await _spin()
        assert len(mode_writes()) == count and not command.done()
        assert mode.state in ("active", "stalled")
        release.set()
        assert (await check)["result"] == "roundtrip_ok"
        await hass.async_block_till_done()
        await command
    assert mode_writes()[count:] == [0, HEATING]           # the keep-alive, then the command
    assert fake.registers[106] == HEATING and mode.desired == Desired("heating")
    assert _issues(hass, config_entry) == set()


async def test_an_options_reload_at_220_1_hands_the_mode_on_without_a_gap(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    mode = await _active(hass, config_entry, fake, advance)
    await _command(hass, mode, lambda _: Desired("heating", night=True))
    count = len(mode_writes())
    hass.config_entries.async_update_entry(
        config_entry, options={**config_entry.options, CONF_UNAVAILABLE_AFTER: 200})
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    new = config_entry.runtime_data.coordinator.mode
    assert new is not mode and mode._stopped
    # the old controller's last write, and the new one's first, both the same word
    assert mode_writes()[count:] == [HEATING | NIGHT, HEATING | NIGHT]
    assert new.desired == Desired("heating", night=True)
    await advance(400)
    assert all(not w & STANDBY for w in mode_writes())
    assert fake.e09_episodes == [] and _issues(hass, config_entry) == set()


async def test_turning_mode_control_off_with_a_reload_stops_all_writes(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, advance,
        mode_writes):
    fake = mode_unit
    await _active(hass, config_entry, fake, advance)
    hass.config_entries.async_update_entry(config_entry, options={CONF_ALLOW_WRITES: True})
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    count = len(mode_writes())
    await advance(300)
    assert len(mode_writes()) == count                     # nothing writes after the reload
    assert _issues(hass, config_entry) == {"serial_control_unmanaged"}


async def test_ticks_that_are_not_ten_seconds_apart_still_write_once_a_minute(
        hass, config_entry, with_mode_control, modbus_clients, mode_unit, freezer):
    fake = mode_unit
    fake.registers[220] = 1
    mode = await _setup(hass, config_entry)
    sent, steps = [], [7, 13, 9, 11, 12, 8, 10, 14, 6, 10]
    for step in steps * 10:                                # 1000 s of jittery timer firings
        await _tick_by(hass, freezer, step)
        await hass.async_block_till_done()
        if mode.last_sent is not None and mode.last_sent not in sent:
            sent.append(mode.last_sent)
    gaps = [b - a for a, b in zip(sent, sent[1:], strict=False)]
    assert len(gaps) >= 12 and min(gaps) >= 60             # never more often than a minute
    assert max(gaps) <= 60 + max(steps) + 10               # and never later than a tick or two
    assert mode.max_gap_s < E09_DETECT and fake.e09_episodes == []
