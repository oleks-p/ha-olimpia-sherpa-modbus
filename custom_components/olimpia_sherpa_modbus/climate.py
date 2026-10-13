"""The heat pump as a climate entity -- read-only.

It shows what the panel has selected (heating, cooling or off), what the unit
is doing, the water temperature and the water target. It cannot change the
mode: over Modbus there is no command for it with ADDR220 = 0, and the panel
stays in charge (docs/p5_mode_research.md). So it offers only the mode the
unit is in, and no target temperature to set; the setpoints are numbers, on
the service board, once their write check has passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityDescription,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry
from .entity import SherpaEntity, SherpaEntityDescription, value

PARALLEL_UPDATES = 0  # read-only: nothing is ever sent

MODES = {"off": HVACMode.OFF, "heating": HVACMode.HEAT, "cooling": HVACMode.COOL}


@dataclass(frozen=True, kw_only=True)
class SherpaClimateDescription(ClimateEntityDescription, SherpaEntityDescription):
    """The one climate entity."""


HEAT_PUMP = SherpaClimateDescription(key="heat_pump", value_fn=value("selected_mode"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SherpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SherpaClimate(entry.runtime_data.coordinator, HEAT_PUMP, "climate")])


def _curve(values: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "enabled": None if values.get(f"{kind}_curve_enabled") is None
        else bool(values.get(f"{kind}_curve_enabled")),
        "outdoor_at_max_water": values.get(f"{kind}_curve_max_water_outdoor"),
        "max_water": values.get(f"{kind}_curve_max_water"),
        "outdoor_at_min_water": values.get(f"{kind}_curve_min_water_outdoor"),
        "min_water": values.get(f"{kind}_curve_min_water"),
    }


class SherpaClimate(SherpaEntity, ClimateEntity):
    entity_description: SherpaClimateDescription
    _attr_supported_features = ClimateEntityFeature(0)
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_precision = 0.1

    @property
    def _values(self) -> dict[str, Any]:
        return self.coordinator.data.values

    @property
    def hvac_mode(self) -> HVACMode | None:
        return MODES.get(self._values.get("selected_mode"))

    @property
    def hvac_modes(self) -> list[HVACMode]:
        # Only the mode the unit is in: there is no other one to switch to from
        # here, and offering them would only end in an error.
        mode = self.hvac_mode
        return [mode] if mode is not None else []

    @property
    def hvac_action(self) -> HVACAction | None:
        values, mode = self._values, self.hvac_mode
        if mode is None:
            return None
        if mode is HVACMode.OFF:
            return HVACAction.OFF
        if values.get("defrost"):
            return HVACAction.DEFROSTING
        if values.get("mode") in ("domestic_hot_water", "anti_legionella"):
            return HVACAction.IDLE          # the compressor serves the tank, not the rooms
        if values.get("compressor_running"):
            return HVACAction.HEATING if mode is HVACMode.HEAT else HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        return self._values.get("water_out")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        values = self._values
        return {
            "water_target": values.get("water_target"),
            "water_target_source": values.get("water_target_source"),
            "water_in": values.get("water_in"),
            "water_out": values.get("water_out"),
            "outdoor_air": values.get("outdoor_air"),
            "dhw_in_progress": values.get("mode") == "domestic_hot_water",
            "night": values.get("mode_night"),
            "remote_controls": values.get("remote_controls"),
            # The curves themselves, for cards that draw them: their sensors are
            # diagnostic and off by default, the registers are always read.
            **{f"{kind}_curve": _curve(values, kind) for kind in ("heating", "cooling")},
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """The only mode offered is the current one: nothing to do."""
