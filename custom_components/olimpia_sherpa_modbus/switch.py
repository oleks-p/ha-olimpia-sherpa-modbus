"""Writable on/off parameters (the climatic curves) -- once the write check passed.

Same rules as number.py: the "allow writes" option, and a passed write check
for this register on this unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry
from .entity import SherpaEntity, SherpaEntityDescription, add_present_entities, remove_stale, value
from .registers import WRITE_SPECS

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class SherpaSwitchDescription(SwitchEntityDescription, SherpaEntityDescription):
    """A writable on/off parameter."""


SWITCHES: tuple[SherpaSwitchDescription, ...] = tuple(
    SherpaSwitchDescription(
        key=spec.key,
        entity_category=EntityCategory.CONFIG,
        value_fn=value(spec.key),
        present_fn=lambda coordinator, key=spec.key: coordinator.writes.writable(key),
    )
    for spec in WRITE_SPECS.values() if spec.platform == "switch"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SherpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if not coordinator.writes.allowed:
        remove_stale(hass, entry, "switch")
        return
    add_present_entities(coordinator, async_add_entities, SWITCHES,
                         lambda d: SherpaSwitch(coordinator, d, "switch"))


class SherpaSwitch(SherpaEntity, SwitchEntity):
    entity_description: SherpaSwitchDescription

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.writes.writable(self.entity_description.key)

    @property
    def is_on(self) -> bool | None:
        raw = self.entity_description.value_fn(self.coordinator)
        return None if raw is None else raw == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.writes.async_write(self.entity_description.key, 1, self._context)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.writes.async_write(self.entity_description.key, 0, self._context)
