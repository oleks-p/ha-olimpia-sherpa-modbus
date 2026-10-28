#!/usr/bin/env python3
"""The P6 test: does the unit follow the mode command, register 106?

Olimpia's RDE448 says register 106 selects the operating mode while ADDR220 = 1
(bits: 1 standby, 2 ECO, 4 cooling, 8 heating, 16 night; heating and cooling
both clear is DHW only), and that the unit raises E09 when 106 has not been
written for 255 s. This checks both on the unit, one step at a time, as
docs/p6_mode_command_test.md describes:

    status     read only: what the unit holds now. Run it first.
    panel      ADDR220 = 0, panel on standby: write heating, watch, put 106 back
    serial     ADDR220 = 1: standby, heating, heating+ECO, heating+night, DHW only
    watchdog   ADDR220 = 1: write heating, wait until the unit heats without a DHW
               cycle, then write nothing for 10 min. When does E09 come, how
               long does it stay, and does the unit keep heating through it?
               --need-compressor also requires the compressor to be running
               (its runtime counter rising) before the silence starts, and
               says whether the counter kept rising through each E09.
    restore    ADDR220 = 0 again: put 106 back to what `status` found

Writes go through the integration's admin action write_mode_command (it needs
"Allow writes"), reads through read_registers: one master on the wire, and Home
Assistant keeps running. ADDR220 is changed only by a person, on the panel.
Each step saves its samples under research/mode_command/. Ctrl-C stops a step:
`panel` puts 106 back, `serial` and `watchdog` write standby.

    python3 tools/mode_command_test.py --ha http://homeassistant.local:8123 \\
        --token-file ~/.ha-token status

Standard library only. The token is read from the file and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN = "olimpia_sherpa_modbus"

# -- register 106 and the words that show what the unit does --------------------------

STANDBY, ECO, COOLING, HEATING, NIGHT = 1, 2, 4, 8, 16
#: In the order a name reads best: "heating+eco", not "eco+heating".
COMMAND_BITS = {STANDBY: "standby", HEATING: "heating", COOLING: "cooling", ECO: "eco",
                NIGHT: "night"}
SERIAL_STEPS = (STANDBY, HEATING, HEATING | ECO, HEATING | NIGHT, 0)

#: Register 12. Bits 5 and 6 together are "pending"; every DHW cycle also sets bit 1.
STATUS_BITS = {0x01: "cooling", 0x02: "heating", 0x04: "dhw", 0x08: "legionella",
               0x60: "pending", 0x80: "night"}
OUTPUT_BITS = {0: "pump", 1: "dhw_pump", 2: "eh1", 3: "eh2", 4: "3way", 5: "k5",
               7: "boiler", 8: "alarm"}
E09 = 1 << 8                       # register 100, bit n -> E(n+1)

#: What a sample reads: runs the unit answers whole (registers.ANSWERING_RUNS).
SAMPLE = ((8, 1), (12, 1), (100, 3), (105, 2), (220, 1))
#: The watchdog's fast sample: the status word, the alarms, the outputs and 106.
#: E09 has been seen on the panel for about a second, so every read counts.
QUICK = ((12, 1), (100, 3), (105, 2))
#: Registers 270-271, the compressor's runtime counter (u32, high word first). It
#: rises one per second while the compressor runs, and only then.
COUNTER = (270, 2)
FIELDS = {"8": "inputs", "12": "status", "100": "alarm_1", "101": "alarm_2", "102": "override",
          "105": "outputs", "106": "mode_command", "220": "remote_controls"}


def command_name(value: int | None) -> str:
    if value is None:
        return "?"
    names = [name for bit, name in COMMAND_BITS.items() if value & bit]
    if not value & (STANDBY | COOLING | HEATING):
        names.insert(0, "dhw-only")
    return "+".join(names)


def status_name(status: int | None) -> str:
    if status is None:
        return "?"
    names = [name for mask, name in STATUS_BITS.items() if status & mask == mask]
    return "+".join(names) or "standby"


def outputs_name(outputs: int | None) -> str:
    if outputs is None:
        return "?"
    return "+".join(name for bit, name in OUTPUT_BITS.items() if outputs >> bit & 1) or "-"


def errors(s: dict) -> str:
    a1, a2 = s.get("alarm_1") or 0, s.get("alarm_2") or 0
    codes = [f"E{n + 1:02d}" for n in range(9) if a1 >> n & 1]
    codes += [f"E{20 + n}" for n in range(8) if a2 >> n & 1]
    return ",".join(codes) or "-"


def selected(status: int) -> str:
    """What the status word says is selected: heating, cooling, none -- or dhw,
    which hides the selection, because a DHW cycle sets the heating bit."""
    if status & 0x0C:
        return "dhw"
    return "heating" if status & 0x02 else "cooling" if status & 0x01 else "none"


def follows(value: int, status: int) -> str:
    """Does the status word show what 106 asks for? yes, no, or dhw (can't tell)."""
    want = wanted(value)
    shown = selected(status)
    if shown == "dhw" and want != "none":
        return "dhw"
    night = bool(value & NIGHT) == bool(status & 0x80)
    return "yes" if (shown == want or (shown == "dhw" and want == "none")) and night else "no"


# -- Home Assistant -------------------------------------------------------------------

class Failed(Exception):
    """An action call failed; the message says why, as far as the API tells."""


class Api:
    def __init__(self, base: str, token: str, entry: str | None) -> None:
        self.base, self.token, self.entry = base.rstrip("/"), token, entry

    def _call(self, service: str, body: dict) -> dict:
        if self.entry:
            body = {**body, "config_entry_id": self.entry}
        req = urllib.request.Request(
            f"{self.base}/api/services/{DOMAIN}/{service}?return_response",
            data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())["service_response"]
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace").strip().replace("\n", " ")
            if err.code == 500:
                # The REST API does not pass the action's own error on; the log has it.
                detail += " -- see the Home Assistant log for the reason"
            raise Failed(f"{service}: HTTP {err.code}: {detail}") from err
        except (urllib.error.URLError, TimeoutError) as err:
            raise Failed(f"{service}: {err}") from err

    def sample(self, quick: bool = False, counter: bool = False) -> dict:
        words: dict[str, int] = {}
        for address, count in (QUICK if quick else SAMPLE) + (COUNTER,) * counter:
            words.update(self._call("read_registers",
                                    {"address": address, "count": count})["registers"])
        sample = {name: words.get(address) for address, name in FIELDS.items()}
        if counter:
            sample["compressor_seconds"] = counter_value(words)
        return sample

    def identity(self) -> dict:
        result = self._call("read_registers", {"address": 199, "count": 1})
        return {"identify": result["identify"], "firmware": result["firmware"]}

    def command(self, value: int) -> dict:
        return self._call("write_mode_command", {"value": value})


# -- one step's record ---------------------------------------------------------------

class Run:
    """Prints each sample and write as it happens, and keeps them in one JSON file."""

    def __init__(self, api: Api, directory: pathlib.Path, step: str, args: dict) -> None:
        self.api = api
        directory.mkdir(parents=True, exist_ok=True)
        number = len(list(directory.glob("[0-9][0-9]-*.json")))
        self.path = directory / f"{number:02d}-{step}.json"
        self.t0 = time.monotonic()
        self.last_write = float("-inf")
        self.data: dict = {"step": step, "started": _now(), "args": args, "events": []}

    @property
    def t(self) -> float:
        return time.monotonic() - self.t0

    def _add(self, kind: str, fields: dict, save: bool = True) -> dict:
        event = {"t": round(self.t, 1), "at": _now(), "kind": kind, **fields}
        self.data["events"].append(event)
        if save:
            self.save()
        return event

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, indent=1) + "\n")

    def sample(self, quick: bool = False, show: bool = True, counter: bool = False) -> dict:
        """One sample, as recorded (with its time, "t"). A quick one is saved later."""
        event = self._add("sample", self.api.sample(quick, counter), save=not quick)
        if show:
            print(f"  {self.t:>5.0f}s       {_line(event)}", flush=True)
        return event

    def write(self, value: int, why: str = "write") -> dict:
        result = self.api.command(value)
        self.last_write = time.monotonic()
        event = self._add(why, {**result, "mode_command": result["read_back"]})
        s = {"mode_command": result["read_back"], **{k: result[k] for k in (
            "status", "outputs", "alarm_1", "alarm_2", "remote_controls")}}
        back = "" if result["read_back"] == value else f" (read back {result['read_back']})"
        print(f"  {self.t:>5.0f}s {why:<5} {value} {command_name(value)}{back}", flush=True)
        print(f"  {self.t:>5.0f}s       {_line(s)}", flush=True)
        return event

    def watch(self, seconds: float, interval: float, keepalive: tuple[int, float] | None = None
              ) -> list[dict]:
        """Sample every ``interval`` for ``seconds``; rewrite (value, every) if asked."""
        samples, end = [], time.monotonic() + seconds
        while time.monotonic() < end:
            time.sleep(max(0.0, min(interval, end - time.monotonic())))
            if keepalive and time.monotonic() - self.last_write >= keepalive[1]:
                self.write(keepalive[0], "keep")
            samples.append(self.sample())
        return samples


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def counter_value(words: dict) -> int | None:
    high, low = words.get(str(COUNTER[0])), words.get(str(COUNTER[0] + 1))
    return None if high is None or low is None else high << 16 | low


def _line(s: dict) -> str:
    counter = s.get("compressor_seconds")
    return (f"106={s.get('mode_command')!s:<3} {command_name(s.get('mode_command')):<18} "
            f"status={s.get('status')!s:<4} {status_name(s.get('status')):<26} "
            f"out={s.get('outputs')!s:<4} {outputs_name(s.get('outputs')):<16} "
            f"alarms={errors(s):<8} 220={s.get('remote_controls')}"
            + ("" if counter is None else f" compressor={counter}s"))


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(f"not now: {message}")


# -- the steps ------------------------------------------------------------------------

def step_status(run: Run) -> None:
    identity = run.api.identity()
    run.data["identity"] = identity
    s = run.sample()
    print(f"identify {identity['identify']}, firmware {identity['firmware']}; "
          f"ADDR220 = {s['remote_controls']}; 106 = {s['mode_command']} "
          f"({command_name(s['mode_command'])}); the status word shows "
          f"{selected(s['status'] or 0)} selected")
    if identity["identify"] != 1134:
        print("this is not the reference layout (1134): stop here", file=sys.stderr)


def step_panel(run: Run, hold: float, interval: float) -> None:
    s = run.sample()
    _require(s["remote_controls"] == 0, f"ADDR220 reads {s['remote_controls']}; this step "
             "needs 0 (display)")
    _require(not s["status"] & 0x0F, f"status reads {s['status']} ({status_name(s['status'])}); "
             "select standby on the panel first, so a change shows")
    original = s["mode_command"]
    run.data["abort_value"] = original
    run.write(HEATING)
    seen = run.watch(hold, interval)
    run.write(original, "back")
    run.watch(15, interval)
    verdict = {
        "followed": any(selected(x["status"]) == "heating" for x in seen),
        "held": all(x["mode_command"] == HEATING for x in seen),
    }
    run.data["verdict"] = verdict
    print(f"\nwith ADDR220 = 0 the unit {'FOLLOWED' if verdict['followed'] else 'ignored'} "
          f"106 = {HEATING}; 106 {'kept' if verdict['held'] else 'did not keep'} the value")


def step_serial(run: Run, steps: list[int], hold: float, interval: float,
                keepalive: float) -> None:
    s = run.sample()
    _require(s["remote_controls"] == 1, f"ADDR220 reads {s['remote_controls']}; set it to 1 "
             "on the panel first")
    run.data["abort_value"] = STANDBY
    table = []
    for value in steps:
        print(f"\n-- {command_name(value)} --")
        run.write(value)
        last = run.watch(hold, interval, (value, keepalive))[-1]
        table.append({"value": value, "status": last["status"], "outputs": last["outputs"],
                      "alarms": errors(last), "follows": follows(value, last["status"])})
    run.data["verdict"] = table
    print(f"\n{'106':<20} {'status at the end':<32} {'outputs':<16} {'alarms':<8} follows")
    for row in table:
        print(f"{row['value']:<3} {command_name(row['value']):<16} {row['status']:<4} "
              f"{status_name(row['status']):<27} {outputs_name(row['outputs']):<16} "
              f"{row['alarms']:<8} {row['follows']}")
    print(f"\n106 now holds {steps[-1]} ({command_name(steps[-1])}). Next: `watchdog`, or set "
          "ADDR220 = 0 on the panel and run `restore`. With no write for 255 s the unit "
          "raises E09.")


#: Counter seconds the compressor must gain between the two confirming samples, and the
#: time between them. It counts one per second while running: 10 s should give about 10.
CONFIRM_GAP = 10.0
CONFIRM_RISE = 5


def wait_for_compressor(run: Run, value: int, window: float) -> dict:
    """Keep writing ``value`` until the compressor is running -- right now.

    Whether E09 stops a *running* compressor is the open question (the two E09
    on 2026-10-28 came with it idle), so a silence with the compressor off
    proves nothing. The silence may only start from a compressor seen running
    just before it: two samples ``CONFIRM_GAP`` s apart, immediately before the
    final write, must show the counter rising. One that rose a while ago and has
    stopped since does not count. The two samples are recorded as
    ``compressor_confirmed``. Raises Failed if that does not happen within
    ``window`` seconds: the caller's abort then writes standby, the safe restore.
    """
    print(f"waiting up to {window:.0f} s for the compressor to run")
    deadline = run.t + window
    while True:
        a = run.sample(counter=True)
        if a["compressor_seconds"] is None:
            raise Failed("the compressor counter (registers 270-271) did not answer")
        time.sleep(CONFIRM_GAP)
        b = run.sample(counter=True)
        rise = (b["compressor_seconds"] or 0) - a["compressor_seconds"]
        if rise >= CONFIRM_RISE:
            run.data["compressor_confirmed"] = {
                "counter_a": a["compressor_seconds"], "counter_b": b["compressor_seconds"],
                "t_a": a["t"], "t_b": b["t"], "rise": rise}
            print(f"compressor running: counter {a['compressor_seconds']} -> "
                  f"{b['compressor_seconds']} s in {b['t'] - a['t']:.0f} s")
            return run.write(value)            # the silence starts from a fresh write
        if run.t >= deadline:
            raise Failed(f"the compressor counter did not rise in {window:.0f} s (stands at "
                         f"{b['compressor_seconds']}): run this when space heating really runs")
        run.watch(20, 20, (value, 60))         # keep the unit fed while waiting


def compressor_through(trace: list[dict], episodes: list[dict], start: float,
                       after_s: float = 15.0) -> list[dict]:
    """Per E09 episode: did the runtime counter keep rising through it?

    Compares the counter before the episode with the first sample ``after_s``
    after it ended (the last sample, if the run ended first). An episode lasts
    about a second, so the counter itself cannot show it: what shows is a
    compressor that stopped and waits out its restart delay, which would leave
    the counter standing still. "rising" means at least half a second per second.
    """
    seen = [(round(x["t"] - start, 1), x["compressor_seconds"]) for x in trace
            if x.get("compressor_seconds") is not None]
    out = []
    for n, e in enumerate(episodes, 1):
        before = [p for p in seen if p[0] <= e["up_s"]]
        end = e["down_s"] if e["down_s"] is not None else e["up_s"]
        later = [p for p in seen if p[0] >= end + after_s] or seen[-1:]
        if not before or not later or later[0][0] <= before[-1][0]:
            out.append({"episode": n, "rising": None})
            continue
        (t0, c0), (t1, c1) = before[-1], later[0]
        out.append({"episode": n, "from_s": t0, "to_s": t1, "counter_before": c0,
                    "counter_after": c1, "rising": c1 - c0 >= 0.5 * (t1 - t0)})
    return out


def step_watchdog(run: Run, value: int, settle: float, silence: float,
                  interval: float, need_compressor: bool = False,
                  compressor_window: float = 180) -> None:
    s = run.sample()
    _require(s["remote_controls"] == 1, f"ADDR220 reads {s['remote_controls']}; set it to 1 "
             "on the panel first")
    run.data["abort_value"] = STANDBY
    want = wanted(value)
    last = run.write(value)
    # A DHW cycle sets the heating bit and hides the selection: what E09 does to
    # heating only shows outside one. Wait for that, keeping 106 written.
    if settle:
        print(f"waiting up to {settle:.0f} s for {want} without a DHW cycle")
        deadline = run.t + settle
        while selected(last["status"]) != want:
            if run.t >= deadline:
                raise Failed(f"no {want} without a DHW cycle in {settle:.0f} s: try again "
                             "later, or with --settle 0")
            last = run.watch(30, 30, (value, 60))[-1]
        last = run.write(value)            # the silence starts from a fresh write
    if need_compressor:
        last = wait_for_compressor(run, value, compressor_window)
    print(f"no writes for {silence:.0f} s from now; sampling every {interval:g} s, printing "
          "changes and a line every 30 s")
    start, prev = last["t"], last
    trace: list[dict] = []
    episodes: list[dict] = []
    changes: list[dict] = []
    note = run.t + 30
    while run.t - start < silence:
        time.sleep(interval)
        x = run.sample(quick=True, show=False, counter=need_compressor)
        trace.append(x)
        at = round(x["t"] - start, 1)
        up, was = _e09(x), _e09(prev)
        if up and not was:
            episodes.append({"up_s": at, "not_up_at_s": round(prev["t"] - start, 1),
                             "down_s": None})
            print(f"  {at:>6.1f}s E09 up")
        elif was and not up and episodes:
            episodes[-1]["down_s"] = at
            print(f"  {at:>6.1f}s E09 down")
        state = (x["status"], x["outputs"], x["mode_command"])
        changed = state != (prev["status"], prev["outputs"], prev["mode_command"])
        if changed:
            changes.append({"at_s": at, "status": x["status"], "outputs": x["outputs"],
                            "mode_command": x["mode_command"]})
        if changed or run.t >= note:
            print(f"  {at:>6.1f}s       {_line(x)}", flush=True)
            note = run.t + 30
            run.save()
        prev = x
    up_at_rewrite = _e09(prev)
    print(f"writing {value} again")
    rewrite = run.write(value)
    cleared = None
    if up_at_rewrite:
        while run.t - rewrite["t"] < 60 and cleared is None:
            time.sleep(interval)
            x = run.sample(quick=True, show=False, counter=need_compressor)
            trace.append(x)
            if not _e09(x):
                cleared = round(x["t"] - rewrite["t"], 1)
    run.data["verdict"] = {
        "value": value, "silence_s": silence, "interval_s": interval,
        "status_at_start": last["status"], "outputs_at_start": last["outputs"],
        "e09": episodes, "changes": changes,
        "e09_up_at_rewrite": up_at_rewrite, "cleared_after_rewrite_s": cleared,
    }
    if need_compressor:
        through = compressor_through(trace, episodes, start)
        run.data["verdict"]["compressor_through_e09"] = through
        run.data["verdict"]["compressor_kept_rising"] = (
            None if not through or any(c["rising"] is None for c in through)
            else all(c["rising"] for c in through))
    print(f"\n{len(episodes)} E09 episode(s) in {silence:.0f} s without a write "
          f"(RDE448: E09 after 255 s):")
    for e in episodes:
        down = f"down at {e['down_s']:.1f} s" if e["down_s"] is not None else "still up"
        print(f"  up at {e['up_s']:.1f} s (not yet at {e['not_up_at_s']:.1f} s), {down}")
    if changes:
        print("status, outputs or 106 changed:")
        for c in changes:
            print(f"  {c['at_s']:>6.1f}s       {_line(c)}")
    else:
        print(f"status, outputs and 106 did not change: {status_name(last['status'])}, "
              f"{outputs_name(last['outputs'])}, 106 = {value}")
    for c in run.data["verdict"].get("compressor_through_e09", ()):
        said = {True: "yes", False: "NO", None: "unknown"}[c["rising"]]
        detail = "" if c["rising"] is None else (
            f" (counter {c['counter_before']} -> {c['counter_after']} s between "
            f"{c['from_s']:.1f} s and {c['to_s']:.1f} s)")
        print(f"counter kept rising through episode {c['episode']}: {said}{detail}")
    if up_at_rewrite:
        print("E09 was up at the rewrite; " + (f"it cleared {cleared:.1f} s later"
              if cleared is not None else "it did NOT clear within 60 s: clear it on the panel"))
    print("Nothing writes 106 now, so E09 comes back within 255 s: set ADDR220 = 0 on the "
          "panel and run `restore`, or run `serial` again")


def wanted(value: int) -> str:
    """What the status word should show selected for this 106 value."""
    return ("none" if value & STANDBY else "heating" if value & HEATING
            else "cooling" if value & COOLING else "none")


def _e09(sample: dict) -> bool:
    return bool((sample.get("alarm_1") or 0) & E09)


def step_restore(run: Run, value: int) -> None:
    s = run.sample()
    _require(s["remote_controls"] == 0, f"ADDR220 reads {s['remote_controls']}; set it back "
             "to 0 on the panel first")
    run.write(value)
    print(f"\n106 is {value} again and the panel is in control. On the panel: select the mode "
          "the unit was in before the test, and clear E09 if it is still shown.")


def baseline_command(directory: pathlib.Path) -> int:
    """106 as the first `status` step found it; 0, as on the reference unit, if none."""
    for path in sorted(directory.glob("[0-9][0-9]-status.json")):
        for event in json.loads(path.read_text())["events"]:
            if event["kind"] == "sample" and event.get("mode_command") is not None:
                return event["mode_command"]
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ha", default="http://homeassistant.local:8123")
    ap.add_argument("--token-file", default="~/.ha-token")
    ap.add_argument("--entry", help="config entry id, if more than one Sherpa is set up")
    ap.add_argument("--dir", default=str(ROOT / "research" / "mode_command"),
                    help="where the records go (default research/mode_command)")
    sub = ap.add_subparsers(dest="step", required=True)
    sub.add_parser("status", help="read only: what the unit holds now")
    panel = sub.add_parser("panel", help="ADDR220 = 0: is 106 ignored?")
    panel.add_argument("--hold", type=float, default=60)
    panel.add_argument("--interval", type=float, default=5, help="seconds between samples")
    serial = sub.add_parser("serial", help="ADDR220 = 1: does the unit follow 106?")
    serial.add_argument("--hold", type=float, default=60, help="seconds on each value")
    serial.add_argument("--cooling", action="store_true", help="also try cooling (4)")
    serial.add_argument("--steps", help="comma-separated values instead of the default sequence")
    serial.add_argument("--keepalive", type=float, default=60,
                        help="rewrite the value this often within a hold (well under 255 s)")
    serial.add_argument("--interval", type=float, default=5, help="seconds between samples")
    watchdog = sub.add_parser("watchdog", help="ADDR220 = 1: what does E09 do?")
    watchdog.add_argument("--value", type=int, default=HEATING)
    watchdog.add_argument("--settle", type=float, default=1200,
                          help="seconds to wait (writing) for the unit to do what --value asks "
                               "without a DHW cycle; 0 to start at once")
    watchdog.add_argument("--silence", type=float, default=600,
                          help="seconds without a write: 600 covers two 255 s periods")
    watchdog.add_argument("--interval", type=float, default=0.5,
                          help="seconds between samples during the silence")
    watchdog.add_argument("--need-compressor", action="store_true",
                          help="start the silence only once the compressor runs (its runtime "
                               "counter rises), and say whether it kept running through each "
                               "E09. Run it when space heating really runs. A compressor that "
                               "E09 stops may wait out its restart delay twice")
    watchdog.add_argument("--compressor-window", type=float, default=180,
                          help="seconds to wait (writing) for the counter to rise; if it does "
                               "not, abort with a standby write")
    restore = sub.add_parser("restore", help="ADDR220 = 0 again: put 106 back")
    restore.add_argument("--value", type=int, help="default: what `status` found")
    args = ap.parse_args(argv)

    directory = pathlib.Path(args.dir)
    steps = list(SERIAL_STEPS)
    if args.step == "serial":
        if args.steps:
            steps = [int(v) for v in args.steps.split(",")]
        elif args.cooling:
            steps.insert(-1, COOLING)
        bad = [v for v in steps if not 0 <= v <= 31 or v & HEATING and v & COOLING]
        if bad:
            ap.error(f"not a mode command: {bad}")
        if args.keepalive >= 255:
            ap.error("--keepalive must be under 255 s, or the unit raises E09")
    with open(os.path.expanduser(args.token_file), encoding="utf-8") as fh:
        token = fh.read().strip()
    api = Api(args.ha, token, args.entry)
    recorded = {k: v for k, v in vars(args).items() if k not in ("token_file", "ha")}
    run = Run(api, directory, args.step, recorded)
    print(f"{args.step}: recording to {run.path}")
    try:
        if args.step == "status":
            step_status(run)
        elif args.step == "panel":
            step_panel(run, args.hold, args.interval)
        elif args.step == "serial":
            step_serial(run, steps, args.hold, args.interval, args.keepalive)
        elif args.step == "watchdog":
            step_watchdog(run, args.value, args.settle, args.silence, args.interval,
                          args.need_compressor, args.compressor_window)
        else:
            step_restore(run, baseline_command(directory) if args.value is None else args.value)
    except (KeyboardInterrupt, Failed) as err:
        run.data["stopped"] = str(err) or "interrupted"
        print(f"\nstopped: {run.data['stopped']}", file=sys.stderr)
        abort = run.data.get("abort_value")
        if abort is not None:
            try:
                run.write(abort, "abort")
            except Failed as again:
                print(f"could not write {abort} ({command_name(abort)}): {again}",
                      file=sys.stderr)
        print("If ADDR220 is 1: set it to 0 on the panel, then run `restore`. Without writes "
              "the unit raises E09 within about 4 minutes.", file=sys.stderr)
        return 130 if isinstance(err, KeyboardInterrupt) else 2
    finally:
        run.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
