"""Opt-in writes, and the write check that has to pass before any of them.

Nothing here runs unless the entry's "allow writes" option is on. Even then a
register is written only when all of these hold:

1. it has a WriteSpec (registers.WRITE_SPECS), which a forbidden register can
   never get;
2. the write check has passed for it **on this unit and firmware**;
3. the value is in range and on the step;
4. it differs from what the unit holds now -- read fresh, not from the cache;
5. the rate limits allow it.

The write check is how a register earns (2), and it replaces the probe's
``--verify-writes`` for a unit the integration already polls: it goes through
the integration's own bus lock, so there is still exactly one master on the
wire. For one register it:

* reads the current value,
* writes that same value back and reads it (is FC6 accepted at all?),
* writes one step away, reads at once and again after ``hold`` seconds
  (does it apply, and does it stay?),
* and always writes the original back, in ``finally``.

The result is kept per unit in Home Assistant's storage, keyed by identify
code and firmware -- a firmware update invalidates it, because the update
resets the service parameters and may change what the controller accepts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from .const import (
    CONF_ALLOW_WRITES,
    DOMAIN,
    EVENT_PARAMETER_WRITTEN,
    WRITE_DAILY_LIMIT,
    WRITE_MIN_INTERVAL,
)
from .registers import BY_KEY, FORBIDDEN_WRITES, WRITE_SPECS, Kind, Reg, WriteSpec
from .transport import SherpaIllegalError, SherpaTransientError

if TYPE_CHECKING:
    from .coordinator import SherpaCoordinator

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}.write_checks"
#: The one WriteChecks per Home Assistant, shared by every entry.
CHECKS: HassKey[WriteChecks] = HassKey(f"{DOMAIN}_write_checks")

#: Results of the write check.
ROUNDTRIP_OK = "roundtrip_ok"   # applied, and stayed applied
REFUSED = "refused"             # the unit answered with a Modbus exception
IGNORED = "ignored"             # accepted, but the register did not change
REVERTED = "reverted"           # applied, then the controller put its own value back
UNVERIFIABLE = "unverifiable"   # the current value is outside the spec; nothing written


def encode(reg: Reg, value: float) -> int:
    raw = round(value / reg.scale)
    return raw & 0xFFFF if reg.kind is Kind.I16 else raw


def decode(reg: Reg, raw: int) -> float:
    value = raw - 0x10000 if reg.kind is Kind.I16 and raw & 0x8000 else raw
    return round(value * reg.scale, 3)


def on_step(spec: WriteSpec, value: float) -> bool:
    steps = (value - spec.minimum) / spec.step
    return spec.minimum <= value <= spec.maximum and abs(steps - round(steps)) < 1e-6


#: Between restore attempts: long enough for a stalled link to come back.
RESTORE_RETRY_DELAY = 1.0


async def _wait(seconds: float) -> None:
    """The check's only waits (the hold, the restore retries), in one place."""
    await asyncio.sleep(seconds)


class WriteChecks:
    """Write-check results, per config entry, in Home Assistant's storage.

    Also the one restore a check still owes, if any: it is saved before the
    test value goes out, so a restart in the middle of a check -- or a restore
    that failed -- is finished at the next setup instead of being forgotten.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)
        self._data: dict[str, dict[str, dict[str, Any]]] | None = None
        self._pending: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        if self._data is None:
            stored = await self._store.async_load() or {}
            self._data = stored.get("entries", {})
            self._pending = stored.get("pending", {})

    def for_entry(self, entry_id: str) -> dict[str, dict[str, Any]]:
        assert self._data is not None
        return self._data.setdefault(entry_id, {})

    def pending(self, entry_id: str) -> dict[str, Any] | None:
        return self._pending.get(entry_id)

    async def async_record(self, entry_id: str, result: dict[str, Any]) -> None:
        self.for_entry(entry_id)[result["key"]] = result
        await self._async_save()

    async def async_set_pending(self, entry_id: str, pending: dict[str, Any] | None) -> None:
        if pending is None:
            if self._pending.pop(entry_id, None) is None:
                return
        else:
            self._pending[entry_id] = pending
        await self._async_save()

    async def async_forget(self, entry_id: str) -> None:
        await self.async_load()
        dropped = self._data.pop(entry_id, None) is not None
        dropped |= self._pending.pop(entry_id, None) is not None
        if dropped:
            await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save({"entries": self._data, "pending": self._pending})


class WriteGate:
    """What may be written on one unit, and the write path itself."""

    def __init__(self, coordinator: SherpaCoordinator, checks: dict[str, dict[str, Any]]) -> None:
        self.coordinator = coordinator
        self.checks = checks
        self.allowed = bool(coordinator.config_entry.options.get(CONF_ALLOW_WRITES, False))
        self.log: deque[dict[str, Any]] = deque(maxlen=20)
        self._last_write: dict[str, float] = {}
        self._recent: deque[float] = deque()
        # A write and a check are each several bus exchanges; the bus lock
        # keeps the exchanges apart, this keeps the sequences apart -- or a
        # check's restore could undo a write made during its hold.
        self._lock = asyncio.Lock()

    # -- what is writable ---------------------------------------------------

    def verified(self, key: str) -> bool:
        """The write check passed for this register on this unit and firmware."""
        check = self.checks.get(key) or {}
        model = self.coordinator.model
        return (check.get("result") == ROUNDTRIP_OK
                and check.get("identify") == model.identify
                and check.get("firmware") == model.firmware)

    def writable(self, key: str) -> bool:
        spec = WRITE_SPECS.get(key)
        return (self.allowed and spec is not None
                and BY_KEY[key].address not in FORBIDDEN_WRITES
                and any(r.key == key for r in self.coordinator.registers)
                and self.verified(key))

    # -- the write path -------------------------------------------------------

    async def async_write(self, key: str, value: float, context: Context | None = None) -> None:
        if not self.allowed:
            raise ServiceValidationError(translation_domain=DOMAIN,
                                         translation_key="writes_disabled")
        if not self.writable(key):
            raise ServiceValidationError(translation_domain=DOMAIN,
                                         translation_key="not_writable",
                                         translation_placeholders={"key": key})
        spec, reg = WRITE_SPECS[key], BY_KEY[key]
        if not on_step(spec, value):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="out_of_range",
                translation_placeholders={"key": key, "value": str(value),
                                          "minimum": str(spec.minimum),
                                          "maximum": str(spec.maximum), "step": str(spec.step)})
        raw = encode(reg, value)
        async with self._lock:
            before = await self._read(reg)
            if before == raw:
                self.coordinator.patch_register(reg.address, before)
                return  # already so: no write, no wear
            self._rate_limit(key)
            await self._send(reg, raw)
            after = await self._read(reg)
            self._note(key, reg, before, raw, after, context)
        if after != raw:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="write_not_applied",
                translation_placeholders={"key": key, "expected": str(value),
                                          "actual": str(decode(reg, after))})

    def _rate_limit(self, key: str) -> None:
        now = time.monotonic()
        while self._recent and now - self._recent[0] > 86400:
            self._recent.popleft()
        if (now - self._last_write.get(key, float("-inf")) < WRITE_MIN_INTERVAL
                or len(self._recent) >= WRITE_DAILY_LIMIT):
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="rate_limited",
                translation_placeholders={"key": key, "interval": str(int(WRITE_MIN_INTERVAL)),
                                          "daily": str(WRITE_DAILY_LIMIT)})
        self._last_write[key] = now
        self._recent.append(now)

    async def _read(self, reg: Reg) -> int:
        try:
            (raw,) = await self.coordinator.bus.read(self.coordinator.slave, reg.address, 1)
        except (SherpaTransientError, SherpaIllegalError) as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed",
                                     translation_placeholders={"error": str(err)}) from err
        return raw

    async def _send(self, reg: Reg, raw: int) -> None:
        try:
            await self.coordinator.bus.write(self.coordinator.slave, reg.address, raw)
        except SherpaIllegalError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_refused",
                                     translation_placeholders={"code": str(err.code)}) from err
        except SherpaTransientError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed",
                                     translation_placeholders={"error": str(err)}) from err

    def _note(self, key: str, reg: Reg, before: int, raw: int, after: int,
              context: Context | None) -> None:
        coordinator = self.coordinator
        coordinator.patch_register(reg.address, after)
        record = {"at": dt_util.utcnow().isoformat(), "key": key, "address": reg.address,
                  "old": decode(reg, before), "new": decode(reg, raw),
                  "read_back": decode(reg, after),
                  "user_id": context.user_id if context else None}
        self.log.append(record)
        coordinator.hass.bus.async_fire(
            EVENT_PARAMETER_WRITTEN,
            {"entry_id": coordinator.config_entry.entry_id, **record}, context=context)
        _LOGGER.info("Wrote %s (register %s): %s -> %s, read back %s", key, reg.address,
                     record["old"], record["new"], record["read_back"])

    # -- the write check ----------------------------------------------------------

    async def async_check(self, key: str, hold: float) -> dict[str, Any]:
        """Prove a register can be written on this unit. Always restores it."""
        if not self.allowed:
            raise ServiceValidationError(translation_domain=DOMAIN,
                                         translation_key="writes_disabled")
        spec, reg = WRITE_SPECS.get(key), BY_KEY.get(key)
        if spec is None or reg is None or reg.address in FORBIDDEN_WRITES or not any(
                r.key == key for r in self.coordinator.registers):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_a_candidate",
                                         translation_placeholders={"key": key})
        async with self._lock:
            return await self._check(spec, reg, hold)

    async def _check(self, spec: WriteSpec, reg: Reg, hold: float) -> dict[str, Any]:
        model = self.coordinator.model
        result: dict[str, Any] = {
            "key": reg.key, "address": reg.address, "identify": model.identify,
            "firmware": model.firmware, "checked_at": dt_util.utcnow().isoformat(),
            "remote_controls": self.coordinator.data.values.get("remote_controls"),
            "hold_s": hold, "steps": [],
        }
        steps = result["steps"]
        original = await self._read(reg)
        result["original"] = decode(reg, original)
        neighbour = self._neighbour(spec, reg, original)
        if neighbour is None:
            result["result"] = UNVERIFIABLE
            return await self._finish(result)

        owed = False
        try:
            # 1. the same value back: is FC6 accepted at all?
            try:
                await self.coordinator.bus.write(self.coordinator.slave, reg.address, original)
            except SherpaIllegalError as err:
                steps.append({"write": decode(reg, original), "refused": err.code})
                result["result"] = REFUSED
                return await self._finish(result)
            steps.append({"write": decode(reg, original), "read": decode(reg, await self._read(reg))})
            # 2. one step away: does it apply, and does it stay? The restore is
            # on record before the test value goes out, so a restart during the
            # hold is put right by the next setup (async_resume).
            await self._store.async_set_pending(self._entry_id, {
                "key": reg.key, "address": reg.address, "original": original,
                "test": neighbour, "at": dt_util.utcnow().isoformat()})
            owed = True
            await self.coordinator.bus.write(self.coordinator.slave, reg.address, neighbour)
            now = await self._read(reg)
            await _wait(hold)
            later = await self._read(reg)
            steps.append({"write": decode(reg, neighbour), "read": decode(reg, now),
                          f"read_after_{hold:g}s": decode(reg, later)})
            result["result"] = (IGNORED if now != neighbour
                                else REVERTED if later != neighbour else ROUNDTRIP_OK)
        except SherpaIllegalError as err:
            steps.append({"write": decode(reg, neighbour), "refused": err.code})
            result["result"] = REFUSED
        except SherpaTransientError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed",
                                     translation_placeholders={"error": str(err)}) from err
        finally:
            if owed:
                await self._restore(reg, original, result)
        return await self._finish(result)

    async def async_resume(self) -> None:
        """Pay a restore that an interrupted or failed check still owes.

        Runs at setup. If the register still holds the check's test value, the
        original goes back; if it holds anything else, it was put right since
        (on the panel, say) and nothing is written.
        """
        owed = self._store.pending(self._entry_id)
        if owed is None:
            return
        reg = BY_KEY.get(owed.get("key", ""))
        if reg is None or reg.address != owed.get("address"):
            await self._store.async_set_pending(self._entry_id, None)
            return
        if not self.allowed:
            # Writes were switched off since: leave it to a person, and say so.
            self._raise_issue(reg, owed["original"])
            return
        async with self._lock:
            current = await self._read(reg)
            if current != owed["test"]:
                await self._settled(reg)
                return
            _LOGGER.warning("%s (register %s) was left on %s by an interrupted write check; "
                            "restoring %s", reg.key, reg.address, decode(reg, current),
                            decode(reg, owed["original"]))
            await self._restore(reg, owed["original"], {})

    def _neighbour(self, spec: WriteSpec, reg: Reg, original: int) -> int | None:
        """One step from the current value, inside the spec; None if it cannot be."""
        if spec.platform == "switch":
            return 1 - original if original in (0, 1) else None
        current = decode(reg, original)
        if not on_step(spec, current):
            return None
        target = current + spec.step if current + spec.step <= spec.maximum else current - spec.step
        return encode(reg, target)

    async def _restore(self, reg: Reg, original: int, result: dict[str, Any]) -> None:
        last_error: Exception | None = None
        for _attempt in range(3):
            try:
                await self.coordinator.bus.write(self.coordinator.slave, reg.address, original)
                (back,) = await self.coordinator.bus.read(self.coordinator.slave, reg.address, 1)
                if back == original:
                    result["restored"] = decode(reg, back)
                    self.coordinator.patch_register(reg.address, back)
                    await self._settled(reg)
                    return
            except (SherpaTransientError, SherpaIllegalError) as err:
                last_error = err
            await _wait(RESTORE_RETRY_DELAY)
        # The unit is left on the test value. Say so loudly and specifically, and
        # keep the debt on record: the next setup tries again.
        result["restored"] = None
        self._raise_issue(reg, original)
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="restore_failed",
            translation_placeholders={"key": reg.key, "address": str(reg.address),
                                      "value": str(decode(reg, original))}) from last_error

    async def _settled(self, reg: Reg) -> None:
        await self._store.async_set_pending(self._entry_id, None)
        ir.async_delete_issue(self.coordinator.hass, DOMAIN, f"restore_failed_{reg.key}")

    def _raise_issue(self, reg: Reg, original: int) -> None:
        # Persistent: it must outlive a restart, as the changed value does.
        ir.async_create_issue(
            self.coordinator.hass, DOMAIN, f"restore_failed_{reg.key}", is_fixable=False,
            is_persistent=True, severity=ir.IssueSeverity.ERROR,
            translation_key="restore_failed",
            translation_placeholders={"key": reg.key, "address": str(reg.address),
                                      "value": str(decode(reg, original))})

    @property
    def _store(self) -> WriteChecks:
        return self.coordinator.hass.data[CHECKS]

    @property
    def _entry_id(self) -> str:
        return self.coordinator.config_entry.entry_id

    async def _finish(self, result: dict[str, Any]) -> dict[str, Any]:
        await self._store.async_record(self._entry_id, result)
        self.checks[result["key"]] = result
        _LOGGER.info("Write check %s: %s", result["key"], result["result"])
        # Let the number/switch platforms add the entity, if it just became writable.
        self.coordinator.async_update_listeners()
        return result
