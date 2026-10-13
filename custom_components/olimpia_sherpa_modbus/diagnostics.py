"""Diagnostics: raw register words alongside the decoded view, for bug reports.

The raw words matter most: they let a decoding problem be reproduced against
the simulator without access to the unit.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import SherpaConfigEntry
from .block_planner import describe
from .const import CONF_SERIAL_PORT
from .registers import REGISTER_MAP_VERSION

TO_REDACT = {CONF_HOST, CONF_SERIAL_PORT}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SherpaConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    model = coordinator.model
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "model": {
            "identify": model.identify,
            "firmware": [model.fw_197, model.fw_198],
            "idu": model.idu,
            "odu": model.odu,
            "name": model.model,
            "features": sorted(model.features),
            "register_map": REGISTER_MAP_VERSION,
        },
        "link": coordinator.link_stats(),
        "writes": {
            "allowed": coordinator.writes.allowed,
            "writable": sorted(k for k in coordinator.writes.checks
                               if coordinator.writes.writable(k)),
            "checks": dict(sorted(coordinator.writes.checks.items())),
            "recent_writes": list(coordinator.writes.log),
        },
        "block_plan": describe(coordinator.blocks),
        "stale": data.stale,
        "values": {k: v for k, v in sorted(data.values.items())},
        "raw_registers": dict(sorted(data.raw.items(), key=lambda kv: int(kv[0].split("+")[0]))),
    }
