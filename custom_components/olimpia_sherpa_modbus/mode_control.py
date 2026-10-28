"""Mode control: set the unit's operating mode through register 106, and keep it fed.

Opt-in (Allow writes + Mode control), and active only while the panel has handed
control to RS-485 (ADDR220 = 1). Source of the register facts: Olimpia RDE448;
what the unit did on the reference unit: docs/p6_mode_command_test.md; the design:
docs/p6_mode_control.md.

With ADDR220 = 1 the unit acts on 106 at once and raises E09 (alarm relay, pump
stopped for about 2.5 s) every 255 s unless 106 is written. So the controller

* writes the desired word every 60 s (a keep-alive, silent: no event, no log),
  from its own timer, apart from the poll, which stops on an outage;
* reads it back, and rewrites at once if the unit holds something else;
* never writes while ADDR220 is 0 or 2, and never writes ADDR220 at all. Every
  write re-reads ADDR220 from the unit first (the cache can be hours old in a
  link stall), and writes nothing unless it reads 1;
* on a hand-over seen while running (ADDR220 0 -> 1, after at least two polls
  at 0, so a glitched read cannot arm it), takes the mode the panel had, from
  the snapshot of a confirmed poll no older than a minute.

The desired mode lives in a Store, not in an entity: three entities share it, and
the keep-alive needs it before any entity exists.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.hass_dict import HassKey

from . import derive
from .const import (
    CONF_MODE_CONTROL,
    DOMAIN,
    E09_DETECT,
    E09_PERIOD,
    FINAL_WRITE_TIMEOUT,
    HANDOVER_CONFIRM_POLLS,
    KEEPALIVE_INTERVAL,
    MODE_TICK,
    NOT_APPLIED_TICKS,
    PANEL_MAX_AGE,
    STALLED_AFTER,
    UNMANAGED_AFTER,
)

if TYPE_CHECKING:
    from .coordinator import SherpaCoordinator

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
STORE_KEY = f"{DOMAIN}.mode_control"
#: The one ModeStore per Home Assistant, shared by every entry.
MODE_STORE: HassKey[ModeStore] = HassKey(f"{DOMAIN}_mode_store")

OFF, INACTIVE, ACTIVE, STALLED = "off", "inactive", "active", "stalled"


@dataclass(frozen=True)
class Desired:
    """What Home Assistant wants the unit to do: one word for 106.

    Standby is a flag beside the mode, not a mode: it sets the STB bit and keeps
    the mode bit, ECO and night, so leaving standby restores them and the ECO and
    night switches stay truthful while the unit is in standby.
    """

    mode: str = "dhw_only"          # dhw_only | heating | cooling
    standby: bool = False
    eco: bool = False
    night: bool = False

    @property
    def word(self) -> int:
        return derive.command_word(self.mode, standby=self.standby, eco=self.eco,
                                   night=self.night)

    @property
    def operating(self) -> str:
        """standby | dhw_only | heating | cooling, as the select shows it."""
        return "standby" if self.standby else self.mode

    @classmethod
    def from_word(cls, word: int) -> Desired:
        return cls(mode=derive.command_mode(word), standby=bool(word & 1),
                   eco=bool(word & 2), night=bool(word & 16))

    @classmethod
    def load(cls, data: dict[str, Any] | None) -> Desired | None:
        try:
            desired = cls(mode=data["mode"], standby=bool(data["standby"]),
                          eco=bool(data["eco"]), night=bool(data["night"]))
        except (KeyError, TypeError):
            return None
        return desired if desired.mode in derive.COMMAND_MODES else None


def operating_change(option: str) -> Callable[[Desired], Desired]:
    """The change for a select option. Standby keeps the mode; the others leave it."""
    if option == "standby":
        return lambda d: replace(d, standby=True)
    return lambda d: replace(d, mode=option, standby=False)


class ModeStore:
    """The desired mode per config entry, in Home Assistant's storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)
        self._data: dict[str, dict[str, Any]] | None = None

    async def async_load(self) -> None:
        if self._data is None:
            self._data = await self._store.async_load() or {}

    def get(self, entry_id: str) -> dict[str, Any] | None:
        assert self._data is not None
        return self._data.get(entry_id)

    def put(self, entry_id: str, desired: Desired) -> None:
        assert self._data is not None
        self._data[entry_id] = asdict(desired)
        self._store.async_delay_save(lambda: self._data, 1)

    async def async_flush(self) -> None:
        if self._data is not None:
            await self._store.async_save(self._data)

    async def async_forget(self, entry_id: str) -> None:
        await self.async_load()
        if self._data.pop(entry_id, None) is not None:
            await self._store.async_save(self._data)


class ModeController:
    """Per unit: the desired word, its keep-alive, the hand-over and the repair issues."""

    def __init__(self, coordinator: SherpaCoordinator) -> None:
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.desired: Desired | None = None
        #: Monotonic time the unit last acknowledged a write of 106 (its E09 clock
        #: restarted then, even if the read-back failed), reset when ADDR220 leaves 1.
        self.last_sent: float | None = None
        #: Monotonic and wall time of the last write that was also read back right.
        self.last_ok_write: float | None = None
        self.last_ok_write_at: datetime | None = None
        #: (selected_mode, night) as the panel had it, from a confirmed poll while
        #: ADDR220 != 1, and the monotonic time it was taken.
        self.panel: tuple[str | None, bool | None] | None = None
        self._panel_at: float | None = None
        self.writes_total = 0
        self.keepalive_writes = 0
        self.max_gap_s = 0.0
        #: Gaps over E09_DETECT, each a place where E09 certainly happened: what the
        #: unit and the compressor counter did meanwhile (the open question of
        #: docs/p6_mode_command_test.md, answered passively).
        self.late_events: deque[dict[str, Any]] = deque(maxlen=10)
        self._store: ModeStore | None = None
        self._lock = asyncio.Lock()
        self._unsub: list[Callable[[], None]] = []
        self._stop_unsub: Callable[[], None] | None = None
        self._tasks: set[asyncio.Task] = set()
        self._stopping = False
        self._stopped = False
        self._started = time.monotonic()
        #: Consecutive fresh polls with ADDR220 != 1, and the last poll counted.
        self._off_polls = 0
        self._seen_success: float | None = None
        self._seen_sent: float | None = None
        #: Since when ADDR220 has read 1 without a break (monotonic).
        self._active_since: float | None = None
        self._unmanaged_since: float | None = None
        self._first = True              # the first write after setup is not waited for
        self._handover = False          # desired came from the panel: announce its write
        self._mismatch = 0              # consecutive writes read back as something else
        self._mismatch_noted = False
        self._at_last_write: dict[str, Any] = {}

    # -- state -----------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        coordinator = self.coordinator
        return (coordinator.writes.allowed
                and bool(coordinator.config_entry.options.get(CONF_MODE_CONTROL, False))
                and any(reg.key == "mode_command" for reg in coordinator.registers))

    @property
    def state(self) -> str:
        """off | inactive (ADDR220 is not 1, or unknown) | active | stalled."""
        if not self.enabled:
            return OFF
        if self._remote() != 1:
            return INACTIVE
        last = self.coordinator.last_success
        if last is None or time.monotonic() - last > STALLED_AFTER:
            return STALLED
        return ACTIVE

    def _values(self) -> dict[str, Any]:
        return self.coordinator.data.values

    def _remote(self) -> int | None:
        return self._values().get("remote_controls")

    def _spawn(self, coro) -> None:
        task = self.hass.async_create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -- start and stop ----------------------------------------------------------

    async def async_start(self, store: ModeStore) -> None:
        self._store = store
        now = self._started = time.monotonic()
        values = self._values()
        remote = values.get("remote_controls")
        self._seen_success = self.coordinator.last_success
        if remote == 1:
            self._active_since = now
        elif remote is not None:
            # Seeded, not confirmed: one poll can be a glitch (see _on_update).
            if values.get("selected_mode") is not None:
                self.panel, self._panel_at = (values["selected_mode"],
                                              values.get("mode_night")), now
            self._off_polls = 1
        stored = Desired.load(store.get(self.coordinator.config_entry.entry_id))
        if self.enabled:
            self.desired = stored
        self._unsub.append(self.coordinator.async_add_listener(self._on_update))
        if self.enabled:
            # The first write is a task, not an await: setup must not wait on the bus.
            self._spawn(self._tick())
            self._unsub.append(async_track_time_interval(
                self.hass, self._tick, timedelta(seconds=MODE_TICK)))
            self._stop_unsub = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._on_stop)
        self._evaluate_issues(now)

    async def async_stop(self) -> None:
        """Stop for good: no new work, wait for the work in flight, write once more,
        flush the Store. Idempotent. No standby write: an options change reloads
        the entry and must not stop the heating. Nothing writes after this returns,
        so the bus can be released and the next controller (a reload) has it alone."""
        if self._stopped:
            return
        self._stopped = self._stopping = True
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        if self._stop_unsub is not None:
            self._stop_unsub()
            self._stop_unsub = None
        await self._drain()
        if self.state in (ACTIVE, STALLED):
            await self._final_write()
        if self._store is not None and self.desired is not None:
            await self._store.async_flush()
        self._clear_issues()

    async def _drain(self) -> None:
        """Let the ticks in flight finish (they are short), then cancel what is left."""
        tasks = [t for t in self._tasks if t is not asyncio.current_task()]
        if tasks:
            _done, pending = await asyncio.wait(tasks, timeout=FINAL_WRITE_TIMEOUT)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _on_stop(self, _event: Event) -> None:
        # Home Assistant is stopping: the unit starts the outage with a full 255 s.
        self._stop_unsub = None
        self._stopping = True
        await self._final_write()
        if self._store is not None:
            await self._store.async_flush()

    async def _final_write(self) -> None:
        """One last keep-alive, behind whatever holds the lock, within the timeout."""
        if self.desired is None or self._remote() != 1:
            return
        try:
            async with asyncio.timeout(FINAL_WRITE_TIMEOUT), self._lock:
                await self.coordinator.writes.async_mode_write(
                    self.desired.word, keepalive=True, expect_serial=True)
                self._sent(keepalive=True)
        except (HomeAssistantError, TimeoutError) as err:
            self._sent(keepalive=True)
            _LOGGER.debug("The last write of the mode command did not go out: %s", err)

    # -- the coordinator's updates -----------------------------------------------

    @callback
    def _on_update(self) -> None:
        """Every poll: the panel snapshot, the hand-over, the repair issues.

        Only a fresh poll counts. This is also called when a write patches the cache
        and when a poll fails (stale data), and neither is a new observation.
        """
        values, now = self._values(), time.monotonic()
        remote = values.get("remote_controls")
        fresh = self.coordinator.last_success != self._seen_success
        if fresh:
            self._seen_success = self.coordinator.last_success
        if fresh and remote is not None:
            if remote != 1:
                self._active_since = None
                self.last_sent = None           # not fed any more: no gap to measure
                self._off_polls += 1
                # A snapshot only from a confirmed poll: a glitched read of 0 would
                # carry the status word of ADDR220 = 1, which follows 106, not the panel.
                if (self._off_polls >= HANDOVER_CONFIRM_POLLS
                        and values.get("selected_mode") is not None):
                    self.panel, self._panel_at = (values["selected_mode"],
                                                  values.get("mode_night")), now
            else:
                confirmed = self._off_polls >= HANDOVER_CONFIRM_POLLS
                self._off_polls = 0
                if self._active_since is None:
                    self._active_since = now
                if confirmed and self.enabled:
                    self._hand_over(now)
        self._evaluate_issues(now)

    def _hand_over(self, now: float) -> None:
        """ADDR220 went to 1 while running: take the mode the panel had.

        From the snapshot of a confirmed poll before the flip, if it is fresh (a
        minute): after the flip the status word follows 106 and is no longer the
        panel's. With no fresh snapshot the stored desired stands (106 as read if
        there is none). DHW only is never inferred (status 0 reads as standby on
        the panel); ECO is invisible at 220 = 0, so it stays as stored. Written on
        the next tick, which is kicked now.
        """
        previous = self.desired
        if self.panel is not None and self._panel_at is not None \
                and now - self._panel_at <= PANEL_MAX_AGE:
            selected, night = self.panel
            previous = previous or Desired()
            if selected == "off":
                self.desired = replace(previous, mode="dhw_only", standby=True,
                                       night=bool(night))
            else:
                self.desired = replace(previous, mode=selected, standby=False,
                                       night=bool(night))
        elif previous is None:
            self.desired = Desired.from_word(self._values().get("mode_command") or 0)
        self._panel_at = None                   # used: the next flip needs a new snapshot
        self._handover = True
        self._save()
        _LOGGER.info("ADDR220 is now 1: taking over the panel's mode, %s%s",
                     self.desired.operating, " + night" if self.desired.night else "")
        self._spawn(self._tick())

    # -- the tick ----------------------------------------------------------------

    async def _tick(self, _now: datetime | None = None) -> None:
        if self._stopping or self._lock.locked() or not self.enabled:
            return                                    # one at a time; the next one retries
        async with self._lock:
            if self._stopping:
                return
            try:
                await self._write_if_due()
            finally:
                self._evaluate_issues(time.monotonic())

    async def _write_if_due(self) -> None:
        values = self._values()
        if values.get("remote_controls") != 1:
            return                                    # the panel is in charge: write nothing
        polled = values.get("mode_command")
        if self.desired is None:
            # Nothing stored (first run): adopt what the unit holds. A rebooted unit
            # reads 0, DHW only, which is safe. No write now; the next tick's
            # keep-alive is due at once.
            if polled is not None:
                self.desired = Desired.from_word(polled)
                self._save()
            return
        word, now = self.desired.word, time.monotonic()
        due = (self._first or self._handover or self.last_sent is None
               or now - self.last_sent >= KEEPALIVE_INTERVAL
               or (polled is not None and polled != word))
        if not due:
            return
        if self._first and polled is not None and polled != word:
            _LOGGER.warning("The unit holds mode word %s, Home Assistant wants %s (the unit "
                            "rebooted, or somebody else wrote 106): writing ours", polled, word)
        # Silent when it is only the keep-alive. A change -- a hand-over, or a word the
        # unit does not hold -- is announced once, not on every retry of the same one.
        change = self._handover or (polled is not None and polled != word
                                    and not self._mismatch_noted)
        try:
            back = await self.coordinator.writes.async_mode_write(
                word, keepalive=not change, before=polled, expect_serial=True)
        except ServiceValidationError as err:
            # ADDR220 does not read 1 on the unit (the cache was behind), or writes are off.
            _LOGGER.debug("Mode command not written: %s", err)
            return
        except HomeAssistantError as err:
            self._sent(keepalive=not change)          # the FC6 may have landed
            _LOGGER.debug("Mode command write failed (%s); trying again next tick", err)
            return
        self._sent(keepalive=not change)
        self._wrote()
        self._handover = self._first = False
        if back != word:
            self._mismatch += 1
            self._mismatch_noted = True
        else:
            self._mismatch = 0
            self._mismatch_noted = False

    def _wrote(self) -> None:
        """A write that went out and was read back."""
        self.last_ok_write, self.last_ok_write_at = time.monotonic(), dt_util.utcnow()

    def _sent(self, *, keepalive: bool) -> None:
        """Bookkeeping for a write the unit acknowledged (the gate stamps it)."""
        sent = self.coordinator.writes.last_mode_sent
        if sent is None or sent == self._seen_sent:
            return
        self._seen_sent = sent
        values = self._values()
        if self.last_sent is not None:
            gap = sent - self.last_sent
            self.max_gap_s = max(self.max_gap_s, gap)
            if gap > E09_DETECT:
                self._late(gap, values)
        self.last_sent = sent
        self.writes_total += 1
        self.keepalive_writes += keepalive
        self._at_last_write = self._snapshot(values)

    @staticmethod
    def _snapshot(values: dict[str, Any]) -> dict[str, Any]:
        return {"status": values.get("status"), "outputs": values.get("outputs"),
                "compressor_seconds": values.get("compressor_seconds"),
                "compressor_running": values.get("compressor_running")}

    def _late(self, gap: float, values: dict[str, Any]) -> None:
        """A write after more than E09_DETECT s: E09 happened, gap // 254 times."""
        before, after = self._at_last_write, self._snapshot(values)
        self.late_events.append({
            "start": (dt_util.utcnow() - timedelta(seconds=gap)).isoformat(),
            "end": dt_util.utcnow().isoformat(), "gap_s": round(gap),
            "expected_pulses": int(gap // E09_PERIOD),
            "status_before": before.get("status"), "status_after": after["status"],
            "outputs_before": before.get("outputs"), "outputs_after": after["outputs"],
            "compressor_seconds_before": before.get("compressor_seconds"),
            "compressor_seconds_after": after["compressor_seconds"],
            "compressor_running_before": before.get("compressor_running"),
        })
        _LOGGER.warning("The mode command was not written for %.0f s: the unit raised E09 about "
                        "%d time(s) meanwhile (alarm relay, pump stopped for ~3 s each)",
                        gap, gap // E09_PERIOD)

    def _save(self) -> None:
        if self._store is not None and self.desired is not None:
            self._store.put(self.coordinator.config_entry.entry_id, self.desired)

    # -- commands ------------------------------------------------------------------

    async def async_command(self, change: Callable[[Desired], Desired],
                            context: Context | None = None) -> None:
        """A user's change (select, switch, climate, water heater): all or nothing.

        The new desired is written and read back; if the write fails or the unit
        does not hold it, the previous desired is back and the caller gets an
        error, so the timer never keeps retrying something that was refused. Only
        if the desired is still the new one: a hand-over may have replaced it while
        the write was in flight, and that must stand.
        """
        inactive = ServiceValidationError(translation_domain=DOMAIN,
                                          translation_key="mode_control_inactive")
        if self._stopping or self.state != ACTIVE:
            raise inactive
        async with self._lock:
            if self._stopping:
                raise inactive
            polled = self._values().get("mode_command")
            previous = self.desired
            if previous is None:
                previous = Desired.from_word(polled or 0)
            new = change(previous)
            self.desired = new
            try:
                back = await self.coordinator.writes.async_mode_write(
                    new.word, keepalive=False, before=polled, context=context,
                    expect_serial=True)
            except HomeAssistantError:
                self._sent(keepalive=False)           # the FC6 may have landed
                self._rollback(new, previous)
                raise
            self._sent(keepalive=False)
            if back != new.word:
                self._rollback(new, previous)
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="write_not_applied",
                    translation_placeholders={"key": "mode_command", "expected": str(new.word),
                                              "actual": str(back)})
            self._wrote()
            if self.desired is new:
                self._handover = False
                self._mismatch, self._mismatch_noted = 0, False
            self._save()
        self._evaluate_issues(time.monotonic())

    def _rollback(self, new: Desired, previous: Desired) -> None:
        if self.desired is new:
            self.desired = previous

    # -- repair issues ---------------------------------------------------------------

    def _evaluate_issues(self, now: float) -> None:
        """The three repairs. None is fixable from here: each says what to do on the panel."""
        entry_id = self.coordinator.config_entry.entry_id
        remote = self._remote()
        serial = remote == 1

        # 220 = 1 and nothing keeps the unit fed (option or writes off, or no 106).
        unmanaged = serial and not self.enabled
        if not unmanaged:
            self._unmanaged_since = None
        elif self._unmanaged_since is None:
            self._unmanaged_since = now
        self._issue(f"serial_control_unmanaged_{entry_id}", "serial_control_unmanaged",
                    unmanaged and now - self._unmanaged_since >= UNMANAGED_AFTER,
                    ir.IssueSeverity.WARNING)

        # Controller on, and the unit has not been sent 106 for E09_DETECT s (own clock,
        # since ADDR220 became 1 if nothing was sent yet): E09 is on its way.
        since = max(self.last_sent or float("-inf"), self._active_since or float("inf"))
        silent = self.enabled and serial and now - since
        self._issue(f"mode_keepalive_lost_{entry_id}", "mode_keepalive_lost",
                    bool(silent) and silent > E09_DETECT, ir.IssueSeverity.ERROR,
                    {"seconds": str(int(silent or 0))})

        self._issue(f"mode_not_applied_{entry_id}", "mode_not_applied",
                    self.enabled and serial and self._mismatch >= NOT_APPLIED_TICKS,
                    ir.IssueSeverity.WARNING)

    def _issue(self, issue_id: str, key: str, raised: bool, severity: ir.IssueSeverity,
               placeholders: dict[str, str] | None = None) -> None:
        if raised:
            ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=False,
                                  severity=severity, translation_key=key,
                                  translation_placeholders=placeholders)
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    def _clear_issues(self) -> None:
        entry_id = self.coordinator.config_entry.entry_id
        for issue_id in (f"serial_control_unmanaged_{entry_id}",
                         f"mode_keepalive_lost_{entry_id}", f"mode_not_applied_{entry_id}"):
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    # -- diagnostics ------------------------------------------------------------------

    def diagnostics(self) -> dict[str, Any]:
        values = self._values()
        entry_id = self.coordinator.config_entry.entry_id
        registry = ir.async_get(self.hass)
        issues = [i for i in ("serial_control_unmanaged", "mode_keepalive_lost",
                              "mode_not_applied")
                  if registry.async_get_issue(DOMAIN, f"{i}_{entry_id}") is not None]
        return {
            "enabled": self.enabled,
            "state": self.state,
            "desired": None if self.desired is None else {**asdict(self.desired),
                                                          "word": self.desired.word},
            "polled_106": values.get("mode_command"),
            "remote_controls": values.get("remote_controls"),
            "panel": self.panel,
            "last_ok_write_at": self.last_ok_write_at.isoformat() if self.last_ok_write_at
            else None,
            "writes_total": self.writes_total,
            "keepalive_writes": self.keepalive_writes,
            "max_gap_s": round(self.max_gap_s, 1),
            "late_events": list(self.late_events),
            "issues": issues,
        }
