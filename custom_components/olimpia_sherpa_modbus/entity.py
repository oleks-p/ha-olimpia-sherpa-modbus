"""Shared entity base for the Sherpa integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTITY_PREFIX, DEFAULT_ENTITY_PREFIX, DEFAULT_NAME, DOMAIN, MANUFACTURER
from .coordinator import SherpaCoordinator


@dataclass(frozen=True, kw_only=True)
class SherpaEntityDescription(EntityDescription):
    """Where an entity's value comes from, and when it exists at all."""

    value_fn: Callable[[SherpaCoordinator], Any]
    #: None: always present. Otherwise checked on every update until true; an
    #: entity is added the first time it holds (e.g. a probe that got wired up).
    present_fn: Callable[[SherpaCoordinator], bool] | None = None
    attrs_fn: Callable[[SherpaCoordinator], dict[str, Any]] | None = None


def value(key: str) -> Callable[[SherpaCoordinator], Any]:
    return lambda coordinator: coordinator.data.values.get(key)


def has_value(key: str) -> Callable[[SherpaCoordinator], bool]:
    return lambda coordinator: coordinator.data.values.get(key) is not None


def has_register(key: str) -> Callable[[SherpaCoordinator], bool]:
    """For model-specific registers: present when the model has them."""
    return lambda coordinator: any(reg.key == key for reg in coordinator.registers)


class SherpaEntity(CoordinatorEntity[SherpaCoordinator]):
    """Wires every entity to the one device and the shared coordinator."""

    _attr_has_entity_name = True
    entity_description: SherpaEntityDescription

    def __init__(self, coordinator: SherpaCoordinator, description: SherpaEntityDescription,
                 domain: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        # Suggest the legacy entity id. Home Assistant uses a suggested id as
        # it stands on first registration, so `sensor.sherpa_water_in` is
        # reclaimed exactly -- and with it the entity's history and long-term
        # statistics, which are keyed by entity id. Display names still come
        # from the translations.
        prefix = entry.data.get(CONF_ENTITY_PREFIX, DEFAULT_ENTITY_PREFIX)
        self.entity_id = f"{domain}.{prefix}_{description.key}"
        model = coordinator.model
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            name=DEFAULT_NAME,
            model=model.model,
            model_id=str(model.identify),
            sw_version=model.firmware,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs_fn = self.entity_description.attrs_fn
        return attrs_fn(self.coordinator) if attrs_fn else None


def add_present_entities(
    coordinator: SherpaCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    descriptions: Iterable[SherpaEntityDescription],
    factory: Callable[[SherpaEntityDescription], Entity],
) -> None:
    """Add each entity once its presence check passes, re-checking on updates.

    Deciding presence once at setup would make the entity set hang on a single
    poll. A probe that reads "absent" on the first cycle -- or is wired up later
    -- would then never get an entity. Entities are only ever added, never
    removed: one that stops reporting shows as unknown and keeps its history.
    """
    pending = list(descriptions)

    @callback
    def sync() -> None:
        ready = [d for d in pending if d.present_fn is None or d.present_fn(coordinator)]
        if not ready:
            return
        for description in ready:
            pending.remove(description)
        async_add_entities([factory(d) for d in ready])

    sync()
    if pending:
        coordinator.config_entry.async_on_unload(coordinator.async_add_listener(sync))
