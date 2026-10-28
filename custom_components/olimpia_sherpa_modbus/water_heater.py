"""The hot water as a water heater: tank temperature, setpoint, and on/off.

* Temperature: the DHW tank probe T3. Target: the DHW setpoint (register 210),
  settable only through the write gate, so only once the entry allows writes and
  the write check has passed for it; limits from its WriteSpec.
* On/off: off is standby (the STB bit of 106), on is STB clear, which restores
  the mode the unit had (standby keeps the mode, ECO and night bits). Settable
  only while mode control is active (ADDR220 = 1). Otherwise it is read-only and
  shows what the status word allows: on when heating, cooling or a DHW cycle
  runs, unknown when the status is 0 (standby and DHW only look alike there).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components.water_heater import (
    STATE_HEAT_PUMP,
    WaterHeaterEntity,
    WaterHeaterEntityDescription,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry
from .entity import SherpaEntity, SherpaEntityDescription, value
from .mode_control import ACTIVE
from .registers import WRITE_SPECS

PARALLEL_UPDATES = 1

_SPEC = WRITE_SPECS["dhw_setpoint"]


@dataclass(frozen=True, kw_only=True)
class SherpaWaterHeaterDescription(WaterHeaterEntityDescription, SherpaEntityDescription):
    """The one water heater."""


HOT_WATER = SherpaWaterHeaterDescription(key="hot_water", value_fn=value("dhw_tank"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SherpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SherpaWaterHeater(entry.runtime_data.coordinator, HOT_WATER,
                                          "water_heater")])


class SherpaWaterHeater(SherpaEntity, WaterHeaterEntity):
    entity_description: SherpaWaterHeaterDescription
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = 0.1
    _attr_target_temperature_step = _SPEC.step
    _attr_min_temp = _SPEC.minimum
    _attr_max_temp = _SPEC.maximum
    _attr_operation_list = [STATE_HEAT_PUMP, STATE_OFF]

    @property
    def supported_features(self) -> WaterHeaterEntityFeature:
        features = WaterHeaterEntityFeature(0)
        if self.coordinator.writes.writable("dhw_setpoint"):
            features |= WaterHeaterEntityFeature.TARGET_TEMPERATURE
        if self.coordinator.mode.state == ACTIVE:
            features |= WaterHeaterEntityFeature.ON_OFF | WaterHeaterEntityFeature.OPERATION_MODE
        return features

    @property
    def current_temperature(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data.values.get("dhw_setpoint")

    @property
    def current_operation(self) -> str | None:
        on = self.coordinator.data.values.get("hot_water_on")
        return None if on is None else STATE_HEAT_PUMP if on else STATE_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        await self.coordinator.writes.async_write("dhw_setpoint", kwargs[ATTR_TEMPERATURE],
                                                  self._context)

    async def _standby(self, standby: bool) -> None:
        await self.coordinator.mode.async_command(lambda d: replace(d, standby=standby),
                                                  self._context)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._standby(False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._standby(True)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        await self._standby(operation_mode == STATE_OFF)
