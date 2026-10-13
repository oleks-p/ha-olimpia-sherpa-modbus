#!/usr/bin/env python3
"""Move a live Home Assistant from YAML-driven Sherpa entities to the integration.

The YAML setup (a `modbus:` hub plus template, derivative and threshold
sensors) and the integration name their entities the same way:
`<domain>.<prefix>_<key>`. History and long-term statistics are keyed by
entity id, so they carry over -- if the new entities get exactly those ids.
They only can once the old registry entries have released them, and Home
Assistant keeps a registry entry long after the YAML that made it is gone.

Each step is separate and checked before anything is sent:

    plan            read-only: what would be removed, and a snapshot to verify against
    remove-legacy   remove exactly the planned registry entries (refuses on any drift)
    add             run the config flow (serial or network), creating the entry
    verify          ids, owners, units, state classes, statistics, repairs, log

    uv run --no-project --with websockets -- python tools/cutover.py \\
        --ha http://192.168.30.141:8123 --token-file ~/.config/hvac-platform/ha-token plan

The order matters and lives in docs/cutover.md: remove-legacy only after the
YAML is gone and Home Assistant has restarted; add straight after.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request

DOMAIN = "olimpia_sherpa_modbus"
#: Platforms the YAML setup used. Nothing else is ever removed.
LEGACY_PLATFORMS = frozenset({"modbus", "template", "derivative", "threshold"})


class HA:
    def __init__(self, base: str, token: str) -> None:
        self.base, self.token = base.rstrip("/"), token

    def rest(self, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path, data=data, method="POST" if body is not None else "GET",
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
        try:
            return json.loads(raw)
        except ValueError:
            return raw.decode(errors="replace")

    def ws(self, *messages: dict) -> list:
        from websockets.sync.client import connect

        results = []
        with connect(re.sub(r"^http", "ws", self.base) + "/api/websocket",
                     max_size=2**26) as sock:
            json.loads(sock.recv())
            sock.send(json.dumps({"type": "auth", "access_token": self.token}))
            if json.loads(sock.recv()).get("type") != "auth_ok":
                raise SystemExit("websocket authentication failed")
            for n, message in enumerate(messages, start=1):
                sock.send(json.dumps({**message, "id": n}))
                while True:
                    reply = json.loads(sock.recv())
                    if reply.get("id") == n:
                        break
                if not reply.get("success"):
                    raise SystemExit(f"{message['type']} failed: {reply.get('error')}")
                results.append(reply["result"])
        return results


def _ours(entity_id: str, prefix: str) -> bool:
    return re.match(rf"^(sensor|binary_sensor)\.{re.escape(prefix)}_", entity_id) is not None


def _registry(ha: HA, prefix: str) -> list[dict]:
    (entries,) = ha.ws({"type": "config/entity_registry/list"})
    return [e for e in entries if _ours(e["entity_id"], prefix)]


def legacy_entries(ha: HA, prefix: str) -> list[dict]:
    """Registry entries the YAML setup owns: legacy platforms, no config entry."""
    return [e for e in _registry(ha, prefix)
            if e["platform"] in LEGACY_PLATFORMS and not e.get("config_entry_id")]


def cmd_plan(ha: HA, args) -> int:
    states = {s["entity_id"]: s for s in ha.rest("/api/states") if _ours(s["entity_id"], args.prefix)}
    (stats,) = ha.ws({"type": "recorder/list_statistic_ids"})
    stats = {s["statistic_id"]: s for s in stats if _ours(s["statistic_id"], args.prefix)}
    (entries,) = ha.ws({"type": "config_entries/get", "domain": DOMAIN})
    legacy = legacy_entries(ha, args.prefix)
    others = [e for e in _registry(ha, args.prefix) if e not in legacy]
    plan = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "prefix": args.prefix,
        "existing_entries": [e["entry_id"] for e in entries],
        "remove": sorted(e["entity_id"] for e in legacy),
        "remove_unique_ids": {e["entity_id"]: e["unique_id"] for e in legacy},
        "keep_untouched": sorted(e["entity_id"] for e in others),
        "snapshot": {
            entity_id: {
                "unit": s["attributes"].get("unit_of_measurement"),
                "state_class": s["attributes"].get("state_class"),
                "device_class": s["attributes"].get("device_class"),
                "state": s["state"],
            } for entity_id, s in states.items()},
        "statistics": {sid: {"unit": s.get("statistics_unit_of_measurement"),
                             "has_sum": bool(s.get("has_sum"))} for sid, s in stats.items()},
    }
    with open(args.plan, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=1, ensure_ascii=False)
    by_platform: dict[str, int] = {}
    for e in legacy:
        by_platform[e["platform"]] = by_platform.get(e["platform"], 0) + 1
    print(f"{len(states)} {args.prefix}_* entities live, {len(stats)} with long-term statistics")
    print(f"would remove {len(legacy)} legacy registry entries: {by_platform}")
    if others:
        print(f"left alone (not legacy YAML): {', '.join(plan['keep_untouched'])}")
    if entries:
        print(f"!! {DOMAIN} is already configured: {plan['existing_entries']}")
    print(f"wrote {args.plan}")
    return 0


def cmd_remove_legacy(ha: HA, args) -> int:
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    now = {e["entity_id"]: e for e in legacy_entries(ha, plan["prefix"])}
    drift = sorted(set(now) ^ set(plan["remove"]))
    changed = [eid for eid in set(now) & set(plan["remove"])
               if now[eid]["unique_id"] != plan["remove_unique_ids"][eid]]
    if drift or changed:
        print(f"refusing: the live registry no longer matches the plan "
              f"(drift {drift[:6]}, changed {changed[:6]}). Re-run plan.")
        return 1
    if not args.yes:
        print(f"would remove {len(now)} entries; pass --yes to do it")
        return 0
    ha.ws(*({"type": "config/entity_registry/remove", "entity_id": eid} for eid in plan["remove"]))
    left = legacy_entries(ha, plan["prefix"])
    print(f"removed {len(plan['remove'])} legacy registry entries; {len(left)} remain")
    return 0 if not left else 1


def cmd_add(ha: HA, args) -> int:
    flow = ha.rest("/api/config/config_entries/flow", {"handler": DOMAIN})
    step = "serial" if args.serial_port else "network"
    flow = ha.rest(f"/api/config/config_entries/flow/{flow['flow_id']}", {"next_step_id": step})
    if step == "serial":
        data = {"serial_port": args.serial_port, "baudrate": str(args.baudrate),
                "slave": args.slave, "entity_prefix": args.prefix}
    else:
        data = {"host": args.host, "port": args.port, "transport": args.framing,
                "slave": args.slave, "entity_prefix": args.prefix}
    result = ha.rest(f"/api/config/config_entries/flow/{flow['flow_id']}", data)
    if result.get("type") != "create_entry":
        print(f"config flow did not finish: {result.get('type')} {result.get('errors')}")
        return 1
    print(f"created {result['title']} ({result['result']['entry_id']}), "
          f"state {result['result'].get('state')}")
    return 0


def cmd_verify(ha: HA, args) -> int:
    with open(args.plan, encoding="utf-8") as fh:
        plan = json.load(fh)
    prefix = plan["prefix"]
    (entries,) = ha.ws({"type": "config_entries/get", "domain": DOMAIN})
    if len(entries) != 1 or entries[0]["state"] != "loaded":
        print(f"!! expected one loaded {DOMAIN} entry, found {entries}")
        return 1
    entry_id = entries[0]["entry_id"]
    registry = {e["entity_id"]: e for e in _registry(ha, prefix)}
    states = {s["entity_id"]: s for s in ha.rest("/api/states") if _ours(s["entity_id"], prefix)}
    (stats,) = ha.ws({"type": "recorder/list_statistic_ids"})
    stats = {s["statistic_id"]: s for s in stats if _ours(s["statistic_id"], prefix)}
    (issues,) = ha.ws({"type": "repairs/list_issues"})
    issues = issues.get("issues", []) if isinstance(issues, dict) else issues
    problems: list[str] = []

    for entity_id, before in plan["snapshot"].items():
        entry, state = registry.get(entity_id), states.get(entity_id)
        if entry is None or entry.get("config_entry_id") != entry_id:
            problems.append(f"{entity_id}: not owned by the integration ({entry and entry['platform']})")
            continue
        if state is None:
            problems.append(f"{entity_id}: no state")
            continue
        attrs = state["attributes"]
        for key, attr in (("unit", "unit_of_measurement"), ("state_class", "state_class")):
            if attrs.get(attr) != before[key]:
                problems.append(f"{entity_id}: {key} {before[key]!r} -> {attrs.get(attr)!r}")
    for sid, before in plan["statistics"].items():
        now = stats.get(sid)
        if now is None or now.get("statistics_unit_of_measurement") != before["unit"]:
            problems.append(f"statistics {sid}: {before} -> {now}")
    # Every entity the integration made must sit on <domain>.<prefix>_<key> for
    # its own key: anything else (a "_2" suffix) means an old entry still held it.
    collisions = [eid for eid, r in registry.items() if r.get("config_entry_id") == entry_id
                  and eid != f"{eid.split('.')[0]}.{prefix}_"
                  f"{r['unique_id'].removeprefix(entry_id + '_')}"]
    if collisions:
        problems.append(f"ids not where they belong: {collisions}")
    leftovers = [e for e, r in registry.items() if r["platform"] in LEGACY_PLATFORMS]
    if leftovers:
        problems.append(f"legacy registry entries still present: {leftovers}")
    unavailable = sorted(e for e, s in states.items() if s["state"] == "unavailable"
                         and registry.get(e, {}).get("config_entry_id") == entry_id)
    if unavailable:
        problems.append(f"unavailable: {unavailable}")
    stat_issues = [i for i in issues if i.get("domain") in ("sensor", "recorder", DOMAIN)
                   and any(w in i.get("issue_id", "") for w in (prefix, "units", "state_class",
                                                                DOMAIN))]
    if stat_issues:
        problems.append(f"repairs: {[i['issue_id'] for i in stat_issues]}")
    log = ha.rest("/api/error_log")
    errors = [ln for ln in str(log).splitlines()
              if " ERROR " in ln and (DOMAIN in ln or "pymodbus" in ln)]
    if errors:
        problems.append(f"{len(errors)} error line(s) in the log, last: {errors[-1][:200]}")

    ours = [e for e, r in registry.items() if r.get("config_entry_id") == entry_id]
    print(f"{len(ours)} entities on the integration, {len(states)} with a state; "
          f"{len(plan['snapshot'])} legacy entities checked, {len(plan['statistics'])} statistics")
    for p in problems:
        print(f"  !! {p}")
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 0 if not problems else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ha", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--prefix", default="sherpa")
    ap.add_argument("--plan", default="cutover-plan.json")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    remove = sub.add_parser("remove-legacy")
    remove.add_argument("--yes", action="store_true")
    add = sub.add_parser("add")
    add.add_argument("--serial-port")
    add.add_argument("--baudrate", type=int, default=9600)
    add.add_argument("--host")
    add.add_argument("--port", type=int, default=502)
    add.add_argument("--framing", choices=("rtu_over_tcp", "tcp"), default="rtu_over_tcp")
    add.add_argument("--slave", type=int, default=201)
    sub.add_parser("verify")
    args = ap.parse_args(argv)
    if args.command == "add" and not (args.serial_port or args.host):
        ap.error("add needs --serial-port or --host")
    with open(os.path.expanduser(args.token_file), encoding="utf-8") as fh:
        ha = HA(args.ha, fh.read().strip())
    return {"plan": cmd_plan, "remove-legacy": cmd_remove_legacy, "add": cmd_add,
            "verify": cmd_verify}[args.command](ha, args)


if __name__ == "__main__":
    raise SystemExit(main())
