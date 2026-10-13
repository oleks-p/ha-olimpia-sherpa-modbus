"""Sensor entities.

Every legacy entity keeps its key, unit, device class and state class exactly:
twenty of them carry long-term statistics, which break if any of those change
at the cutover. tests/fixtures/legacy_entities.json is the reference, and a
golden test holds this file to it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SherpaConfigEntry
from .coordinator import SherpaCoordinator
from .derive import MODE_OPTIONS
from .entity import (
    SherpaEntity,
    SherpaEntityDescription,
    add_present_entities,
    has_register,
    has_value,
    value,
)
from .registers import CODE_DESCRIPTIONS, ENUMS

PARALLEL_UPDATES = 0  # all reads go through the coordinator

DIAGNOSTIC = EntityCategory.DIAGNOSTIC
MEASUREMENT = SensorStateClass.MEASUREMENT
TOTAL_INCREASING = SensorStateClass.TOTAL_INCREASING
CELSIUS = UnitOfTemperature.CELSIUS


@dataclass(frozen=True, kw_only=True)
class SherpaSensorDescription(SensorEntityDescription, SherpaEntityDescription):
    """A sensor and where its value comes from."""


def _temperature(key: str, *, statistics: bool = True, **kwargs: Any) -> SherpaSensorDescription:
    return SherpaSensorDescription(
        key=key,
        native_unit_of_measurement=CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=MEASUREMENT if statistics else None,
        suggested_display_precision=1,
        value_fn=value(key),
        **kwargs,
    )


def _parameter(key: str, *, enabled: bool = False, **kwargs: Any) -> SherpaSensorDescription:
    """A service parameter, read-only: diagnostic, and off unless asked for."""
    kwargs.setdefault("value_fn", value(key))
    return SherpaSensorDescription(
        key=key, entity_category=DIAGNOSTIC, entity_registry_enabled_default=enabled, **kwargs)


def _enum(key: str, *, enabled: bool = False) -> SherpaSensorDescription:
    table = ENUMS[key]

    def state(coordinator: SherpaCoordinator) -> str | None:
        raw = coordinator.data.values.get(key)
        return table.get(raw) if raw is not None else None

    return _parameter(key, enabled=enabled, device_class=SensorDeviceClass.ENUM,
                      options=list(table.values()), value_fn=state)


def _word(key: str) -> SherpaSensorDescription:
    """A raw state word: kept for diagnostics and for the legacy dashboards."""
    return SherpaSensorDescription(key=key, entity_category=DIAGNOSTIC, value_fn=value(key))


def _codes(list_key: str) -> Callable[[SherpaCoordinator], dict[str, Any]]:
    def attrs(coordinator: SherpaCoordinator) -> dict[str, Any]:
        active = coordinator.data.values.get(list_key) or []
        return {"active": active,
                "descriptions": {code: CODE_DESCRIPTIONS.get(code, "") for code in active}}

    return attrs


def _counter(key: str, **kwargs: Any) -> SherpaSensorDescription:
    return SherpaSensorDescription(
        key=key, native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION, state_class=TOTAL_INCREASING,
        value_fn=value(key), **kwargs)


SENSORS: tuple[SherpaSensorDescription, ...] = (
    # -- probes -----------------------------------------------------------
    _temperature("water_in"),
    _temperature("water_out"),
    _temperature("dhw_tank"),
    _temperature("outdoor_air"),
    # Fitted on Aquadue models (T5-T7) or with a solar probe (T8) only.
    _temperature("dhw_compressor_temp", present_fn=has_value("dhw_compressor_temp")),
    _temperature("dhw_condenser_temp", present_fn=has_value("dhw_condenser_temp")),
    _temperature("dhw_evaporator_temp", present_fn=has_value("dhw_evaporator_temp")),
    _temperature("solar_temp", present_fn=has_value("solar_temp")),
    # -- what the unit is doing ---------------------------------------------
    SherpaSensorDescription(
        key="mode", device_class=SensorDeviceClass.ENUM, options=list(MODE_OPTIONS),
        value_fn=value("mode")),
    SherpaSensorDescription(
        key="error_code", value_fn=value("error_code"), attrs_fn=_codes("error_codes")),
    SherpaSensorDescription(
        key="override_code", value_fn=value("override_code"),
        attrs_fn=lambda c: {**_codes("override_codes")(c),
                            "mapping": "bit n = OR(n+1), inferred from the defrost bit"}),
    SherpaSensorDescription(
        key="pump_step", state_class=MEASUREMENT, value_fn=value("pump_step")),
    SherpaSensorDescription(
        key="pump_duty", native_unit_of_measurement=PERCENTAGE, state_class=MEASUREMENT,
        value_fn=value("pump_duty")),
    SherpaSensorDescription(
        key="water_delta", native_unit_of_measurement=CELSIUS, state_class=MEASUREMENT,
        suggested_display_precision=1, value_fn=value("water_delta")),
    SherpaSensorDescription(
        key="compressor_rate", native_unit_of_measurement="s/min", state_class=MEASUREMENT,
        value_fn=value("compressor_rate")),
    # -- runtime ------------------------------------------------------------
    _counter("compressor_seconds"),
    _counter("pump_seconds"),
    _counter("filter_seconds"),
    _counter("dhw_compressor_seconds", present_fn=has_register("dhw_compressor_seconds")),
    _counter("dhw_pump_seconds", present_fn=has_register("dhw_pump_seconds")),
    _counter("smart_grid_1_seconds", entity_category=DIAGNOSTIC,
             entity_registry_enabled_default=False),
    _counter("smart_grid_2_seconds", entity_category=DIAGNOSTIC,
             entity_registry_enabled_default=False),
    SherpaSensorDescription(
        key="compressor_hours", native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION, state_class=TOTAL_INCREASING,
        value_fn=value("compressor_hours")),
    SherpaSensorDescription(
        key="pump_hours", native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION, state_class=TOTAL_INCREASING,
        value_fn=value("pump_hours")),
    # -- setpoints (read-only mirrors; the unit's controller owns them) ------
    _temperature("cooling_setpoint"),
    _temperature("cooling_eco_setpoint"),
    _temperature("heating_setpoint"),
    _temperature("heating_eco_setpoint"),
    _temperature("dhw_setpoint"),
    _temperature("legionella_setpoint"),
    # A hysteresis is a temperature DIFFERENCE. Tagged `temperature`, Home
    # Assistant would convert it with the absolute formula (10 K -> 50 degF).
    SherpaSensorDescription(
        key="dhw_hysteresis", native_unit_of_measurement=CELSIUS, state_class=MEASUREMENT,
        suggested_display_precision=1, value_fn=value("dhw_hysteresis")),
    SherpaSensorDescription(
        key="legionella_start_minutes", native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION, value_fn=value("legionella_start_minutes")),
    SherpaSensorDescription(key="legionella_start", value_fn=value("legionella_start")),
    # -- raw words -----------------------------------------------------------
    _word("inputs"),
    _word("status"),
    _word("outputs"),
    _word("override"),
    _word("alarm_1"),
    _word("alarm_2"),
    _word("identify_code"),
    # -- service parameters (diagnostic) -------------------------------------
    _enum("remote_controls", enabled=True),
    _enum("dhw_source", enabled=True),
    _enum("legionella_mode", enabled=True),
    _enum("aux_heaters"),
    _enum("dhw_mode"),
    _enum("smart_grid"),
    _temperature("boiler_threshold", statistics=False, entity_category=DIAGNOSTIC,
                 entity_registry_enabled_default=False),
    _temperature("freeze_protection", statistics=False, entity_category=DIAGNOSTIC,
                 entity_registry_enabled_default=False),
    _parameter("legionella_interval", native_unit_of_measurement=UnitOfTime.DAYS,
               device_class=SensorDeviceClass.DURATION),
    _parameter("legionella_duration", native_unit_of_measurement=UnitOfTime.MINUTES,
               device_class=SensorDeviceClass.DURATION),
    _parameter("water_setpoint_correction", native_unit_of_measurement=CELSIUS,
               suggested_display_precision=1),
    *(
        _temperature(f"{mode}_curve_{end}", statistics=False, entity_category=DIAGNOSTIC,
                     entity_registry_enabled_default=False)
        for mode in ("cooling", "heating")
        for end in ("max_water_outdoor", "max_water", "min_water_outdoor", "min_water")
    ),
    # -- link health -----------------------------------------------------------
    SherpaSensorDescription(
        key="last_successful_read", device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=DIAGNOSTIC, value_fn=lambda c: c.last_success_at),
    SherpaSensorDescription(
        key="read_failures", entity_category=DIAGNOSTIC, value_fn=lambda c: c.read_failures),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SherpaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    add_present_entities(
        coordinator, async_add_entities, SENSORS,
        lambda description: SherpaSensor(coordinator, description, "sensor"))


class SherpaSensor(SherpaEntity, SensorEntity):
    entity_description: SherpaSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)
