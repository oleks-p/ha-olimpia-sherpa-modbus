"""Binary sensors: the decoded bits, the fault flags and the compressor."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry
from .coordinator import SherpaCoordinator
from .entity import SherpaEntity, SherpaEntityDescription, add_present_entities, value
from .registers import INPUT_BITS, OUTPUT_BITS, STATUS_MASKS


@dataclass(frozen=True, kw_only=True)
class SherpaBinaryDescription(BinarySensorEntityDescription, SherpaEntityDescription):
    """A binary sensor and where its value comes from."""


def _flag(key: str, **kwargs) -> SherpaBinaryDescription:
    return SherpaBinaryDescription(key=key, value_fn=value(key), **kwargs)


def _enabled(key: str) -> SherpaBinaryDescription:
    """A 0/1 service parameter, read-only."""

    def state(coordinator: SherpaCoordinator) -> bool | None:
        raw = coordinator.data.values.get(key)
        return None if raw is None else raw == 1

    return SherpaBinaryDescription(key=key, entity_category=EntityCategory.DIAGNOSTIC,
                                   value_fn=state)


# Device classes follow the legacy entities exactly: changing one changes how
# the recorded history reads ("Running" vs "On"), so only in_flow and error
# carry one.
BINARY_SENSORS: tuple[SherpaBinaryDescription, ...] = (
    _flag("in_flow", device_class=BinarySensorDeviceClass.RUNNING),
    *(_flag(key) for key in INPUT_BITS if key != "in_flow"),
    *(_flag(key) for key in STATUS_MASKS),
    *(_flag(key) for key in OUTPUT_BITS),
    _flag("defrost"),
    _flag("power"),
    _flag("error", device_class=BinarySensorDeviceClass.PROBLEM),
    _flag("warning"),
    SherpaBinaryDescription(
        key="compressor_running", value_fn=value("compressor_running"),
        attrs_fn=lambda c: {"rate_s_per_min": c.data.values.get("compressor_rate")}),
    _enabled("cooling_curve_enabled"),
    _enabled("heating_curve_enabled"),
    _enabled("external_boiler_enabled"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SherpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    add_present_entities(
        coordinator, async_add_entities, BINARY_SENSORS,
        lambda description: SherpaBinarySensor(coordinator, description, "binary_sensor"))


class SherpaBinarySensor(SherpaEntity, BinarySensorEntity):
    entity_description: SherpaBinaryDescription

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator)
