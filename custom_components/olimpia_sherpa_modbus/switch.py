"""Writable on/off parameters (the climatic curves) -- once the write check passed.

Same rules as number.py: the "allow writes" option, and a passed write check
for this register on this unit.

Also, with Mode control on, the ECO and night switches. They are not parameters:
they are bits of the mode command (register 106), shown as the unit read them
back, and usable only while the controller is active (ADDR220 = 1).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry, derive
from .entity import SherpaEntity, SherpaEntityDescription, add_present_entities, remove_stale, value
from .mode_control import ACTIVE
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


#: ECO is bit 1 of 106, night bit 4 (registers.MODE_COMMAND_BITS).
MODE_SWITCHES: tuple[SherpaSwitchDescription, ...] = tuple(
    SherpaSwitchDescription(
        key=key,
        value_fn=lambda c, n=bit: derive.bit(c.data.values.get("mode_command"), n),
        present_fn=lambda c: c.mode.enabled,
    )
    for key, bit in (("eco", 1), ("night", 4))
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
    if not coordinator.mode.enabled:
        remove_stale(hass, entry, "switch", [d.key for d in MODE_SWITCHES])
    add_present_entities(
        coordinator, async_add_entities, SWITCHES + MODE_SWITCHES,
        lambda d: (SherpaModeSwitch if d in MODE_SWITCHES else SherpaSwitch)(
            coordinator, d, "switch"))


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


class SherpaModeSwitch(SherpaEntity, SwitchEntity):
    """ECO or night: a bit of 106, read back from the unit."""

    entity_description: SherpaSwitchDescription

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.mode.state == ACTIVE

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator)

    async def _set(self, on: bool) -> None:
        key = self.entity_description.key
        await self.coordinator.mode.async_command(lambda d: replace(d, **{key: on}),
                                                  self._context)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
