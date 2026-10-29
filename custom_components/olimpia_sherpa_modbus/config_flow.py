"""Config flow: pick the link, check the identity registers, done."""

from __future__ import annotations

import glob
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from . import bus_registry
from .const import (
    CONF_ALLOW_WRITES,
    CONF_BAUDRATE,
    CONF_ENTITY_PREFIX,
    CONF_MODE_CONTROL,
    CONF_SERIAL_PORT,
    CONF_SLAVE,
    CONF_TRANSPORT,
    CONF_UNAVAILABLE_AFTER,
    DEFAULT_BAUDRATE,
    DEFAULT_ENTITY_PREFIX,
    DEFAULT_SLAVE,
    DEFAULT_TCP_PORT,
    DEFAULT_UNAVAILABLE_AFTER,
    DOMAIN,
    MAX_UNAVAILABLE_AFTER,
    MIN_UNAVAILABLE_AFTER,
    TRANSPORT_RTU_OVER_TCP,
    TRANSPORT_SERIAL,
    TRANSPORT_TCP,
)
from .model import ModelInfo, NotASherpa, UnsupportedModel, async_identify
from .transport import Endpoint, SherpaTransientError

BAUDRATES = ["9600", "19200", "38400", "57600", "115200"]
SLAVE = vol.All(vol.Coerce(int), vol.Range(min=1, max=247))


def _list_serial_ports() -> list[str]:
    """Stable by-id paths first; then whatever pyserial sees (in a container the
    by-id links may not exist, only the mapped device)."""
    from serial.tools import list_ports

    ports = sorted(glob.glob("/dev/serial/by-id/*"))
    ports += sorted(p.device for p in list_ports.comports() if p.device not in ports)
    return ports


def _serial_schema(defaults: dict[str, Any], ports: list[str], *,
                   with_prefix: bool) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_SERIAL_PORT, default=defaults.get(CONF_SERIAL_PORT, vol.UNDEFINED)):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=ports, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_BAUDRATE, default=str(defaults.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=BAUDRATES, mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_SLAVE, default=defaults.get(CONF_SLAVE, DEFAULT_SLAVE)): SLAVE,
    }
    if with_prefix:
        fields[vol.Required(CONF_ENTITY_PREFIX, default=DEFAULT_ENTITY_PREFIX)] = str
    return vol.Schema(fields)


def _network_schema(defaults: dict[str, Any], *, with_prefix: bool) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_TCP_PORT)):
            vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Required(CONF_TRANSPORT,
                     default=defaults.get(CONF_TRANSPORT, TRANSPORT_RTU_OVER_TCP)):
            selector.SelectSelector(selector.SelectSelectorConfig(
                options=[TRANSPORT_RTU_OVER_TCP, TRANSPORT_TCP], translation_key="framing",
                mode=selector.SelectSelectorMode.LIST)),
        vol.Required(CONF_SLAVE, default=defaults.get(CONF_SLAVE, DEFAULT_SLAVE)): SLAVE,
    }
    if with_prefix:
        fields[vol.Required(CONF_ENTITY_PREFIX, default=DEFAULT_ENTITY_PREFIX)] = str
    return vol.Schema(fields)


async def _identify(hass: HomeAssistant, data: dict[str, Any]
                    ) -> tuple[ModelInfo | None, dict[str, str], dict[str, str]]:
    """Read the identity registers through the shared bus registry.

    Going through the registry matters: if another entry already polls this
    port, the check queues on the same bus instead of opening the port a
    second time -- two masters is exactly what makes the unit raise E09.
    """
    endpoint = Endpoint.from_config(data)
    registry = bus_registry(hass)
    bus = registry.acquire(endpoint)
    try:
        return await async_identify(bus, data[CONF_SLAVE]), {}, {}
    except SherpaTransientError:
        return None, {"base": "cannot_connect"}, {}
    except NotASherpa:
        return None, {"base": "not_a_sherpa"}, {}
    except UnsupportedModel as err:
        return None, {"base": "unsupported_model"}, {"code": str(err.info.identify)}
    finally:
        await registry.release(endpoint)


def _unique_id(data: dict[str, Any]) -> str:
    return f"{Endpoint.from_config(data).key}#{data[CONF_SLAVE]}"


class SherpaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one Sherpa."""

    VERSION = 1

    def __init__(self) -> None:
        self._errors: dict[str, str] = {}
        self._placeholders: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["serial", "network"])

    async def async_step_serial(self, user_input: dict[str, Any] | None = None
                                ) -> ConfigFlowResult:
        if user_input is not None:
            data = {**user_input, CONF_TRANSPORT: TRANSPORT_SERIAL,
                    CONF_BAUDRATE: int(user_input[CONF_BAUDRATE])}
            result = await self._async_create(data, "serial")
            if result is not None:
                return result
        ports = await self.hass.async_add_executor_job(_list_serial_ports)
        return self.async_show_form(
            step_id="serial", errors=self._errors, description_placeholders=self._placeholders,
            data_schema=self.add_suggested_values_to_schema(
                _serial_schema({}, ports, with_prefix=True), user_input or {}))

    async def async_step_network(self, user_input: dict[str, Any] | None = None
                                 ) -> ConfigFlowResult:
        if user_input is not None:
            result = await self._async_create(dict(user_input), "network")
            if result is not None:
                return result
        return self.async_show_form(
            step_id="network", errors=self._errors, description_placeholders=self._placeholders,
            data_schema=self.add_suggested_values_to_schema(
                _network_schema({}, with_prefix=True), user_input or {}))

    async def _async_create(self, data: dict[str, Any], step: str) -> ConfigFlowResult | None:
        self._errors, self._placeholders = {}, {}
        prefix = data[CONF_ENTITY_PREFIX] = data[CONF_ENTITY_PREFIX].strip()
        if not prefix or slugify(prefix) != prefix:
            self._errors = {CONF_ENTITY_PREFIX: "invalid_prefix"}
            return None
        if any(e.data.get(CONF_ENTITY_PREFIX) == prefix for e in self._async_current_entries()):
            self._errors = {CONF_ENTITY_PREFIX: "prefix_in_use"}
            return None
        await self.async_set_unique_id(_unique_id(data))
        self._abort_if_unique_id_configured()
        info, self._errors, self._placeholders = await _identify(self.hass, data)
        if info is None:
            return None
        return self.async_create_entry(title=info.model, data=data)

    # -- reconfigure: same unit, different link --------------------------------

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None
                                     ) -> ConfigFlowResult:
        """Offer both link types, not only the one currently in use.

        Putting a Modbus gateway in front of the bus turns a serial entry into a
        TCP one, and the entry has to survive that: every entity's unique_id is
        derived from the entry_id, so removing and re-adding the integration
        orphans all of them along with their history.
        """
        self._errors, self._placeholders = {}, {}
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_serial", "reconfigure_network"])

    async def async_step_reconfigure_serial(
            self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_relink(user_input, serial=True)

    async def async_step_reconfigure_network(
            self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._async_relink(user_input, serial=False)

    async def _async_relink(self, user_input: dict[str, Any] | None, *,
                            serial: bool) -> ConfigFlowResult:
        """Rewrite one entry's link, keeping the entry itself."""
        entry = self._get_reconfigure_entry()
        step = "reconfigure_serial" if serial else "reconfigure_network"
        if user_input is not None:
            # Drop the other link's keys. Endpoint and the options flow both read
            # the transport first, so a leftover serial_port on a TCP entry would
            # not be used - but it would be read as truth by the next person
            # looking at the stored data, which is how a stale port gets probed.
            kept = {k: v for k, v in entry.data.items()
                    if k not in (CONF_SERIAL_PORT, CONF_BAUDRATE, CONF_HOST, CONF_PORT)}
            data = {**kept, **user_input}
            if serial:
                data[CONF_TRANSPORT] = TRANSPORT_SERIAL
                data[CONF_BAUDRATE] = int(user_input[CONF_BAUDRATE])
            unique_id = _unique_id(data)
            if unique_id != entry.unique_id and any(
                    e.unique_id == unique_id for e in self._async_current_entries()):
                return self.async_abort(reason="already_configured")
            info, self._errors, self._placeholders = await _identify(self.hass, data)
            if info is not None:
                return self.async_update_reload_and_abort(
                    entry, unique_id=unique_id, title=info.model, data=data)
        defaults = {**entry.data, **(user_input or {})}
        if serial:
            ports = await self.hass.async_add_executor_job(_list_serial_ports)
            schema = _serial_schema(defaults, ports, with_prefix=False)
        else:
            schema = _network_schema(defaults, with_prefix=False)
        return self.async_show_form(step_id=step, data_schema=schema,
                                    errors=self._errors,
                                    description_placeholders=self._placeholders)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> SherpaOptionsFlow:
        return SherpaOptionsFlow()


class SherpaOptionsFlow(OptionsFlowWithReload):
    """Link tolerance, whether verified parameters may be written, and mode control."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        options = self.config_entry.options
        if user_input is not None:
            writes = bool(user_input.get(CONF_ALLOW_WRITES, False))
            mode = bool(user_input.get(CONF_MODE_CONTROL, False))
            if mode and not writes:
                # Mode control writes register 106: it cannot be on with writes off.
                errors["base"] = "mode_control_needs_writes"
            else:
                return self.async_create_entry(data={
                    CONF_UNAVAILABLE_AFTER: int(user_input[CONF_UNAVAILABLE_AFTER]),
                    CONF_ALLOW_WRITES: writes,
                    CONF_MODE_CONTROL: mode,
                })
        current = {**options, **(user_input or {})}
        schema = vol.Schema({
            vol.Required(CONF_UNAVAILABLE_AFTER,
                         default=current.get(CONF_UNAVAILABLE_AFTER, DEFAULT_UNAVAILABLE_AFTER)):
                selector.NumberSelector(selector.NumberSelectorConfig(
                    min=MIN_UNAVAILABLE_AFTER, max=MAX_UNAVAILABLE_AFTER, step=10,
                    unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)),
            vol.Required(CONF_ALLOW_WRITES, default=current.get(CONF_ALLOW_WRITES, False)):
                selector.BooleanSelector(),
            vol.Required(CONF_MODE_CONTROL, default=current.get(CONF_MODE_CONTROL, False)):
                selector.BooleanSelector(),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
