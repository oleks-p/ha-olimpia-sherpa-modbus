"""The Olimpia Splendid Sherpa integration (Modbus RTU).

Reads by default. Writes are opt-in per entry ("allow writes"), and then only
to registers the built-in write check has verified on this very unit -- see
writes.py. The unit's own controller still runs the plant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import (
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.hass_dict import HassKey

from .cards import async_register_cards
from .const import (
    CHECK_HOLD_DEFAULT,
    CHECK_HOLD_MAX,
    CONF_SLAVE,
    DOMAIN,
    PLATFORMS,
    SERVICE_READ_REGISTERS,
    SERVICE_VERIFY_WRITE,
)
from .coordinator import SherpaCoordinator
from .model import NotASherpa, UnsupportedModel, async_identify
from .raw_read import async_read
from .registers import MAX_READ, WRITE_SPECS
from .transport import BusRegistry, Endpoint, SherpaBus, SherpaTransientError
from .writes import CHECKS, WriteChecks

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

VERIFY_WRITE_SCHEMA = vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
    vol.Required("register"): vol.In(sorted(WRITE_SPECS)),
    vol.Optional("hold_seconds", default=CHECK_HOLD_DEFAULT):
        vol.All(vol.Coerce(int), vol.Range(min=1, max=CHECK_HOLD_MAX)),
})

READ_REGISTERS_SCHEMA = vol.Schema({
    vol.Optional("config_entry_id"): cv.string,
    vol.Optional("address"): vol.All(vol.Coerce(int), vol.Range(min=0, max=0xFFFF)),
    vol.Optional("count", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_READ)),
})

#: One bus per physical link, shared by every entry and config flow using it.
BUSES: HassKey[BusRegistry] = HassKey(DOMAIN)


@dataclass
class SherpaRuntime:
    endpoint: Endpoint
    bus: SherpaBus
    coordinator: SherpaCoordinator


SherpaConfigEntry = ConfigEntry[SherpaRuntime]


def bus_registry(hass: HomeAssistant) -> BusRegistry:
    return hass.data.setdefault(BUSES, BusRegistry())


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the admin actions, once, for every entry to use."""

    async def verify_write(call: ServiceCall) -> ServiceResponse:
        entry = _target_entry(hass, call.data.get("config_entry_id"))
        return await entry.runtime_data.coordinator.writes.async_check(
            call.data["register"], call.data["hold_seconds"])

    async def read_registers(call: ServiceCall) -> ServiceResponse:
        entry = _target_entry(hass, call.data.get("config_entry_id"))
        return await async_read(entry.runtime_data.coordinator, call.data.get("address"),
                                call.data["count"])

    # Admin only: it writes to the unit, however briefly and however carefully.
    async_register_admin_service(hass, DOMAIN, SERVICE_VERIFY_WRITE, verify_write,
                                 schema=VERIFY_WRITE_SCHEMA,
                                 supports_response=SupportsResponse.ONLY)
    # Admin only too: it only reads, but at any address and without the map.
    async_register_admin_service(hass, DOMAIN, SERVICE_READ_REGISTERS, read_registers,
                                 schema=READ_REGISTERS_SCHEMA,
                                 supports_response=SupportsResponse.ONLY)
    return True


def _target_entry(hass: HomeAssistant, entry_id: str | None) -> SherpaConfigEntry:
    loaded = [e for e in hass.config_entries.async_entries(DOMAIN)
              if e.state is ConfigEntryState.LOADED]
    if entry_id:
        loaded = [e for e in loaded if e.entry_id == entry_id]
    if len(loaded) != 1:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="choose_entry")
    return loaded[0]


def _issue_id(entry: ConfigEntry) -> str:
    return f"unsupported_model_{entry.entry_id}"


async def async_setup_entry(hass: HomeAssistant, entry: SherpaConfigEntry) -> bool:
    """Identify the unit, then start polling it."""
    endpoint = Endpoint.from_config(entry.data)
    registry = bus_registry(hass)
    bus = registry.acquire(endpoint)
    slave = entry.data[CONF_SLAVE]
    try:
        model = await async_identify(bus, slave)
    except UnsupportedModel as err:
        await registry.release(endpoint)
        placeholders = {"code": str(err.info.identify), "model": err.info.model}
        ir.async_create_issue(
            hass, DOMAIN, _issue_id(entry), is_fixable=False,
            severity=ir.IssueSeverity.ERROR, translation_key="unsupported_model",
            translation_placeholders=placeholders)
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="unsupported_model",
                               translation_placeholders=placeholders) from err
    except NotASherpa as err:
        await registry.release(endpoint)
        raise ConfigEntryError(translation_domain=DOMAIN, translation_key="not_a_sherpa",
                               translation_placeholders={"slave": str(slave)}) from err
    except SherpaTransientError as err:
        await registry.release(endpoint)
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="cannot_connect",
                                  translation_placeholders={"endpoint": str(endpoint)}) from err
    ir.async_delete_issue(hass, DOMAIN, _issue_id(entry))

    checks = hass.data.setdefault(CHECKS, WriteChecks(hass))
    await checks.async_load()
    coordinator = SherpaCoordinator(hass, entry, bus, slave, model, checks.for_entry(entry.entry_id))
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await registry.release(endpoint)
        raise
    try:
        await coordinator.writes.async_resume()
    except HomeAssistantError as err:
        # Not a reason to stop reading the unit: the repair issue says what is left.
        _LOGGER.error("Could not finish an interrupted write check: %s", err)

    entry.runtime_data = SherpaRuntime(endpoint, bus, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    try:
        await async_register_cards(hass, _integration_version(hass))
    except Exception:  # noqa: BLE001 - the entities matter more than the cards
        _LOGGER.warning("Could not set up the Sherpa cards", exc_info=True)
    return True


def _integration_version(hass: HomeAssistant) -> str:
    """The manifest version, which cache-busts the card bundle."""
    try:
        from homeassistant.loader import async_get_loaded_integration

        return async_get_loaded_integration(hass, DOMAIN).version or "0"
    except Exception:  # noqa: BLE001 - only the cache-busting query depends on it
        return "0"


async def async_unload_entry(hass: HomeAssistant, entry: SherpaConfigEntry) -> bool:
    """Stop polling and let the bus go if nothing else uses it."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await bus_registry(hass).release(entry.runtime_data.endpoint)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: SherpaConfigEntry) -> None:
    """A removed unit's write checks go with it: a re-added one is checked afresh."""
    await hass.data.setdefault(CHECKS, WriteChecks(hass)).async_forget(entry.entry_id)
