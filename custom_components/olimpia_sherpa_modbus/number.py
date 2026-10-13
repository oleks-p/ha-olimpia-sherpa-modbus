"""Writable parameters as number entities -- only once the write check passed.

Opt-in twice over: nothing here exists unless the entry's "allow writes" option
is on, and then only for registers the write check has verified on this unit.
The read-only sensor of the same key stays: it carries the long-term
statistics (a number has none) and is what customer dashboards show. These
belong on a service page.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry
from .entity import SherpaEntity, SherpaEntityDescription, add_present_entities, remove_stale, value
from .registers import WRITE_SPECS, WriteSpec

PARALLEL_UPDATES = 1  # one write at a time: they share one bus

#: Temperature differences, not temperatures: no device class, or Home Assistant
#: would convert a 10 K band with the absolute formula.
DELTAS = {"dhw_hysteresis", "water_setpoint_correction"}


@dataclass(frozen=True, kw_only=True)
class SherpaNumberDescription(NumberEntityDescription, SherpaEntityDescription):
    """A writable parameter."""


def _describe(spec: WriteSpec) -> SherpaNumberDescription:
    key = spec.key
    if key == "legionella_duration":
        unit, device_class = UnitOfTime.MINUTES, NumberDeviceClass.DURATION
    elif key in DELTAS:
        unit, device_class = UnitOfTemperature.CELSIUS, None
    else:
        unit, device_class = UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE
    return SherpaNumberDescription(
        key=key,
        native_min_value=spec.minimum,
        native_max_value=spec.maximum,
        native_step=spec.step,
        native_unit_of_measurement=unit,
        device_class=device_class,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=value(key),
        present_fn=lambda coordinator, key=key: coordinator.writes.writable(key),
    )


NUMBERS: tuple[SherpaNumberDescription, ...] = tuple(
    _describe(spec) for spec in WRITE_SPECS.values() if spec.platform == "number")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SherpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if not coordinator.writes.allowed:
        remove_stale(hass, entry, "number")
        return
    add_present_entities(coordinator, async_add_entities, NUMBERS,
                         lambda d: SherpaNumber(coordinator, d, "number"))


class SherpaNumber(SherpaEntity, NumberEntity):
    entity_description: SherpaNumberDescription

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.writes.writable(self.entity_description.key)

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.writes.async_write(self.entity_description.key, value, self._context)
