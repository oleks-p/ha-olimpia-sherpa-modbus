"""Raw register reads for research and support, through the integration's bus.

The admin action read_registers returns words exactly as the unit sends them,
without the register map in between. Without an address it snapshots every
run of registers the reference unit answers, which is how undocumented
registers are found: take a snapshot, change something on the unit's panel,
take another, and diff. It goes through the same bus lock as the polling,
so there is still one master on the wire, and it only ever reads (FC3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .registers import ANSWERING_RUNS, MAX_READ
from .transport import SherpaIllegalError, SherpaTransientError

if TYPE_CHECKING:
    from .coordinator import SherpaCoordinator


def spans(address: int | None, count: int) -> list[tuple[int, int]]:
    """(start, count) requests: one range, or every answering run, each <= MAX_READ."""
    ranges = [(address, count)] if address is not None else [
        (start, end - start + 1) for start, end in ANSWERING_RUNS]
    out = []
    for start, length in ranges:
        while length > 0:
            out.append((start, min(length, MAX_READ)))
            start, length = start + MAX_READ, length - MAX_READ
    return out


async def async_read(coordinator: SherpaCoordinator, address: int | None,
                     count: int) -> dict[str, Any]:
    registers: dict[str, int] = {}
    refused: list[dict[str, int]] = []
    for start, length in spans(address, count):
        try:
            words = await coordinator.bus.read(coordinator.slave, start, length)
        except SherpaIllegalError as err:
            # Not an error here: finding where the unit says "no" is half the point.
            refused.append({"address": start, "count": length, "exception": err.code})
            continue
        except SherpaTransientError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="read_failed",
                                     translation_placeholders={"error": str(err)}) from err
        registers.update({str(start + i): word for i, word in enumerate(words)})
    model = coordinator.model
    return {
        "read_at": dt_util.utcnow().isoformat(),
        "identify": model.identify,
        "firmware": model.firmware,
        "registers": registers,
        "refused": refused,
    }
