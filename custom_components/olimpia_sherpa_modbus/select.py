"""The operating mode as a select -- the exact control, with Mode control on.

Four options: standby, DHW only, heating, cooling. The climate entity cannot say
DHW only (it has no such mode), so this is where it is set. The current option is
register 106 as the unit read it back, not what was asked for. Usable only while
the controller is active (ADDR220 = 1); otherwise unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry, derive
from .entity import SherpaEntity, SherpaEntityDescription, add_present_entities, remove_stale, value
from .mode_control import ACTIVE, operating_change

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class SherpaSelectDescription(SelectEntityDescription, SherpaEntityDescription):
    """The operating mode."""


OPERATING_MODE = SherpaSelectDescription(
    key="operating_mode", options=list(derive.OPERATING_MODES),
    value_fn=value("mode_operating"), present_fn=lambda c: c.mode.enabled)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SherpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    if not coordinator.mode.enabled:
        remove_stale(hass, entry, "select")
        return
    add_present_entities(coordinator, async_add_entities, (OPERATING_MODE,),
                         lambda d: SherpaOperatingMode(coordinator, d, "select"))


class SherpaOperatingMode(SherpaEntity, SelectEntity):
    entity_description: SherpaSelectDescription

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.mode.state == ACTIVE

    @property
    def current_option(self) -> str | None:
        return self.entity_description.value_fn(self.coordinator)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.mode.async_command(operating_change(option), self._context)
