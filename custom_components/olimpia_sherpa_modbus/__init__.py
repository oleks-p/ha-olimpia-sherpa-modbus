"""The Olimpia Splendid Sherpa S2 integration (Modbus RTU).

Read-only. The unit's own controller owns every setpoint it acts on; this
integration reports what it is doing and never sends anything but reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.util.hass_dict import HassKey

from .const import CONF_SLAVE, DOMAIN, PLATFORMS
from .coordinator import SherpaCoordinator
from .model import NotASherpa, UnsupportedModel, async_identify
from .transport import BusRegistry, Endpoint, SherpaBus, SherpaTransientError

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

    coordinator = SherpaCoordinator(hass, entry, bus, slave, model)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        await registry.release(endpoint)
        raise

    entry.runtime_data = SherpaRuntime(endpoint, bus, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SherpaConfigEntry) -> bool:
    """Stop polling and let the bus go if nothing else uses it."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await bus_registry(hass).release(entry.runtime_data.endpoint)
    return unloaded
