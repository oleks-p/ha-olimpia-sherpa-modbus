"""Polling coordinator: reads the planned blocks on their tiers and decodes them."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import derive
from .block_planner import Block, plan_blocks, split
from .const import CONF_UNAVAILABLE_AFTER, DEFAULT_UNAVAILABLE_AFTER, DOMAIN
from .model import ModelInfo
from .registers import (
    ALARM_1_CODES,
    ALARM_2_CODES,
    DEFROST_BIT,
    INPUT_BITS,
    OUTPUT_BITS,
    OVERRIDE_CODES,
    PUMP_DUTY_FALLBACK,
    REGISTERS,
    STATUS_MASKS,
    Kind,
    Reg,
    Tier,
)
from .transport import SherpaBus, SherpaIllegalError, SherpaTransientError
from .writes import WriteGate

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

#: A tier is due this much before its full interval has passed, so a 30 s tier
#: polled from a 10 s loop does not slip to 40 s on scheduling jitter.
TIER_SLACK = 2.0


def decode(reg: Reg, words: list[int], offset: int) -> float | int | None:
    """Raw words at ``offset`` -> the register's value, or None if absent/insane."""
    if reg.kind is Kind.U32:
        return (words[offset] << 16) | words[offset + 1]  # high word first
    raw = words[offset]
    if raw in reg.sentinels:
        return None
    value: float | int = raw - 0x10000 if reg.kind is Kind.I16 and raw & 0x8000 else raw
    if reg.scale != 1.0:
        value = round(value * reg.scale, 3)
    if reg.sane and not reg.sane[0] <= value <= reg.sane[1]:
        return None
    return value


@dataclass
class SherpaData:
    """One poll's worth of decoded state."""

    values: dict[str, Any] = field(default_factory=dict)
    #: Raw words per block key, for diagnostics.
    raw: dict[str, list[int]] = field(default_factory=dict)
    #: True when this cycle's reads failed and the values are the last good ones.
    stale: bool = False

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


class SherpaCoordinator(DataUpdateCoordinator[SherpaData]):
    """Reads the Sherpa on its poll tiers and decodes the register map."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        bus: SherpaBus,
        slave: int,
        model: ModelInfo,
        write_checks: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {slave}",
            update_interval=timedelta(seconds=Tier.CONTROL.seconds),
        )
        self.bus = bus
        self.slave = slave
        self.model = model
        self.unavailable_after = float(
            entry.options.get(CONF_UNAVAILABLE_AFTER, DEFAULT_UNAVAILABLE_AFTER))
        self.registers = tuple(
            reg for reg in REGISTERS if reg.feature is None or reg.feature in model.features)
        self.blocks: list[Block] = list(plan_blocks(self.registers))
        self._cache: dict[str, list[int]] = {}
        self._rejected: set[str] = set()
        self._last_read: dict[Tier, float] = {}
        self._compressor = derive.CompressorEstimator()
        self._last_inputs: int | None = None
        self._inputs_glitch = False
        # Link health, surfaced as diagnostic entities and in diagnostics.
        self.last_success: float | None = None
        self.last_success_at: datetime | None = None
        self.consecutive_failures = 0
        self.read_failures = 0
        self.inputs_glitches = 0
        self.split_blocks: list[str] = []
        self.data = SherpaData()
        self.writes = WriteGate(self, write_checks if write_checks is not None else {})

    # -- polling ---------------------------------------------------------

    async def _async_update_data(self) -> SherpaData:
        now = time.monotonic()
        due = {
            tier for tier in Tier
            if now - self._last_read.get(tier, float("-inf")) >= tier.seconds - TIER_SLACK
        }
        try:
            for block in list(self.blocks):
                if block.tier in due:
                    await self._fetch(block)
        except SherpaTransientError as err:
            self.consecutive_failures += 1
            self.read_failures += 1
            # A stall of 10-30 s is normal on this link. Keep showing the last
            # good values until the outage has lasted `unavailable_after`; the
            # tiers that were not read stay due and are retried next cycle.
            if self.last_success is None or now - self.last_success > self.unavailable_after:
                raise UpdateFailed(f"No answer from the Sherpa: {err}") from err
            _LOGGER.debug("Read failed (%s); keeping the last values", err)
            data = self._build()
            data.stale = True
            return data

        for tier in due:
            self._last_read[tier] = now
        if Tier.COUNTER in due:
            self._compressor.add(now, self._decoded("compressor_seconds"))
        self.last_success = now
        self.last_success_at = dt_util.utcnow()
        self.consecutive_failures = 0
        return self._build()

    async def _fetch(self, block: Block) -> None:
        try:
            words = await self.bus.read(self.slave, block.address, block.count)
        except SherpaIllegalError as err:
            if block.count > block.registers[0].words:
                self._split(block, err)
                for single in split(block):
                    await self._fetch(single)
                return
            # One register the unit does not have: show it as unknown, keep going.
            if block.key not in self._rejected:
                self._rejected.add(block.key)
                _LOGGER.warning("The Sherpa does not answer register %s (%s); it will show as "
                                "unknown", block.registers[0].key, err)
            self._cache.pop(block.key, None)
            return
        self._cache[block.key] = words

    def _split(self, block: Block, err: Exception) -> None:
        """Replace a rejected block with one read per register, for good.

        A fixed fallback to the smallest safe read, never a search for the
        largest one that works: on this class of device the accepted counts are
        not monotonic, and a search finds the wrong answer.
        """
        _LOGGER.warning("The Sherpa refused the read %s (%s); reading those registers one at "
                        "a time from now on", block, err)
        index = self.blocks.index(block)
        self.blocks[index:index + 1] = split(block)
        self.split_blocks.append(str(block))
        self._cache.pop(block.key, None)

    # -- decoding --------------------------------------------------------

    def _decoded(self, key: str) -> Any:
        return self._raw_values().get(key)

    def _raw_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for block in self.blocks:
            words = self._cache.get(block.key)
            if words is None:
                continue
            for reg in block.registers:
                values[reg.key] = decode(reg, words, reg.address - block.address)
        return values

    def _build(self) -> SherpaData:
        """Decode the whole cache, not just this cycle's reads.

        Slow tiers are read once every ten minutes or hour; their values must
        survive the fast polls in between.
        """
        values = self._raw_values()
        data = SherpaData(values=values,
                          raw={key: list(words) for key, words in self._cache.items()})

        # Register 8 reading 0 claims every active-low input is active at once
        # -- flow switch, thermostat and all four mode contacts. Seen five times
        # in 57 days, around E07 episodes: a glitch read, not plant state. The
        # raw word stays visible; the decoded inputs hold their previous value.
        inputs = values.get("inputs")
        if inputs == 0:
            if not self._inputs_glitch:
                self._inputs_glitch = True
                self.inputs_glitches += 1
            inputs = self._last_inputs
        elif inputs is not None:
            self._inputs_glitch = False
            self._last_inputs = inputs
        for key, n in INPUT_BITS.items():
            values[key] = derive.inverted_bit(inputs, n)

        status, outputs, override = values.get("status"), values.get("outputs"), \
            values.get("override")
        for key, (mask, how) in STATUS_MASKS.items():
            values[key] = derive.masked(status, mask, how)
        for key, n in OUTPUT_BITS.items():
            values[key] = derive.bit(outputs, n)
        values["defrost"] = derive.bit(override, DEFROST_BIT)
        values["mode"] = derive.mode(status)
        values["power"] = derive.power(status, outputs)

        alarm_1, alarm_2 = values.get("alarm_1"), values.get("alarm_2")
        values["error"] = derive.any_set(alarm_1, alarm_2)
        values["error_codes"] = (derive.active_codes(alarm_1, ALARM_1_CODES) or []) + (
            derive.active_codes(alarm_2, ALARM_2_CODES) or [])
        values["error_code"] = derive.codes_text(
            derive.active_codes(alarm_1, ALARM_1_CODES),
            derive.active_codes(alarm_2, ALARM_2_CODES))
        values["warning"] = None if override is None else override > 0
        override_codes = derive.active_codes(override, OVERRIDE_CODES)
        values["override_codes"] = override_codes or []
        values["override_code"] = derive.codes_text(override_codes)

        table = [values.get(f"pump_duty_{step}") for step in range(1, 9)]
        if all(v is None for v in table):
            table = list(PUMP_DUTY_FALLBACK)
        values["pump_duty"] = derive.pump_duty(values.get("pump_step"), table)
        values["compressor_hours"] = derive.hours(values.get("compressor_seconds"))
        values["pump_hours"] = derive.hours(values.get("pump_seconds"))
        values["water_delta"] = derive.water_delta(values.get("water_out"),
                                                   values.get("water_in"))
        values["legionella_start"] = derive.clock_text(values.get("legionella_start_minutes"))
        values["compressor_rate"] = self._compressor.rate
        values["compressor_running"] = self._compressor.running
        return data

    def patch_register(self, address: int, raw: int) -> None:
        """Fold a word just read back after a write into the cache, and publish.

        The cache is what every value is decoded from. A setpoint is read once
        every ten minutes, so without this a written value would only show up
        on the next setpoint poll.
        """
        for block in self.blocks:
            words = self._cache.get(block.key)
            if words is not None and block.address <= address <= block.end:
                words[address - block.address] = raw
        self.async_set_updated_data(self._build())

    # -- diagnostics -----------------------------------------------------

    def link_stats(self) -> dict[str, Any]:
        return {
            "last_success": self.last_success_at.isoformat() if self.last_success_at else None,
            "consecutive_failures": self.consecutive_failures,
            "read_failures": self.read_failures,
            "requests": self.bus.requests,
            "bus_failures": self.bus.failures,
            "last_error": self.bus.last_error,
            "inputs_glitches": self.inputs_glitches,
            "split_blocks": list(self.split_blocks),
            "rejected_registers": sorted(self._rejected),
        }
