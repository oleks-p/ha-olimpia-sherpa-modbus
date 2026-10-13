#!/usr/bin/env python3
"""Snapshot a site's legacy, YAML-driven Sherpa entities before the cutover.

Writes two test fixtures:

``legacy_entities.json``
    One record per ``sensor.<prefix>_*`` / ``binary_sensor.<prefix>_*`` entity:
    - registry entry and current state;
    - unit, device and state class;
    - long-term-statistics metadata;
    - the YAML that defines it (register, scale and poll rate for modbus
      sensors; the Jinja for templates);
    - every state it has taken in the recorder's history.
    The integration's golden tests hold its entities to this, so entity ids,
    units and statistics continue unbroken.

``history_<site>.json``
    The recorder's raw history for the state words, the compressor counter and
    the legacy derived entities. Replaying the raw words through the
    integration's decoders must reproduce what the legacy templates showed.
    The legacy compressor-running estimate is kept too, so an improved one can
    be compared with it.

Read-only throughout: REST GETs, websocket list commands, ``cat`` over ssh.

    uv run --no-project --with websockets --with pyyaml -- python tools/legacy_snapshot.py \\
        --ha http://192.168.30.141:8123 --token-file ~/.config/hvac-platform/ha-token \\
        --ssh user@192.168.30.141 --config /home/user/homeassistant/config \\
        --site uahs01 --out-dir tests/fixtures
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

# Entities replayed by the derived-logic tests. Raw words in, legacy derived
# states out. Temperatures and the pump/filter counters are left out: they are
# the bulk of the recorder and no derived logic needs their history.
REPLAY_SUFFIXES = (
    "status", "outputs", "override", "alarm_1", "alarm_2", "inputs", "pump_step",
    "compressor_seconds", "compressor_rate", "compressor_running", "mode", "error_code",
    "power", "error", "warning", "mode_pending", "mode_dhw", "defrost",
)
SENTINEL_STATES = ("unavailable", "unknown")
MAX_ENUMERATED = 40


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class HomeAssistant:
    def __init__(self, base: str, token: str):
        self.base, self.token = base.rstrip("/"), token

    def rest(self, path: str):
        req = urllib.request.Request(self.base + path,
                                     headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.load(resp)

    def ws(self, *messages: dict) -> list:
        from websockets.sync.client import connect

        url = re.sub(r"^http", "ws", self.base) + "/api/websocket"
        results = []
        with connect(url, max_size=2**26) as sock:
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

    def history(self, entity_id: str, start: dt.datetime, end: dt.datetime) -> list[dict]:
        query = urllib.parse.urlencode({
            "end_time": end.isoformat(), "filter_entity_id": entity_id,
            "minimal_response": "", "no_attributes": "", "significant_changes_only": "0"})
        rows = self.rest(f"/api/history/period/{urllib.parse.quote(start.isoformat())}?{query}")
        return rows[0] if rows else []


def fetch_packages(ssh: str, config: str, prefix: str) -> dict[str, str]:
    """Every package file that mentions the prefix, as text."""
    listing = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", ssh,
         f"cd {config} && grep -l -i -E '\\b{prefix}_' packages/*.yaml configuration.yaml"
         " 2>/dev/null; true"],
        capture_output=True, text=True, check=True).stdout.split()
    texts = {}
    for name in sorted(listing):
        texts[name] = subprocess.run(["ssh", "-o", "BatchMode=yes", ssh, f"cat {config}/{name}"],
                                     capture_output=True, text=True, check=True).stdout
    return texts


def yaml_definitions(texts: dict[str, str]) -> dict[str, dict]:
    """Map unique_id (or derived entity id when there is none) to its YAML.

    Files are taken in the order Home Assistant loads packages (alphabetical),
    and the first definition of a unique_id wins -- later duplicates are what
    HA rejects with "does not generate unique IDs".
    """
    import yaml

    class Loader(yaml.SafeLoader):
        """SafeLoader that keeps HA's !include / !secret tags as plain strings."""

    def keep_tag(_loader, suffix, node):
        return f"!{suffix} {getattr(node, 'value', '')}"

    Loader.add_multi_constructor("!", keep_tag)

    found: dict[str, dict] = {}
    # Home Assistant loads one modbus hub per port and drops later duplicates
    # whole ("host/port ... is duplicate, not loaded!"), sensors and all.
    hubs_loaded: dict[str, str] = {}

    def add(key: str, record: dict) -> None:
        if key in found:
            found[key].setdefault("shadowed_in", []).append(record["file"])
        else:
            found[key] = record

    for name, text in texts.items():
        data = yaml.load(text, Loader=Loader) or {}  # noqa: S506 -- SafeLoader subclass
        for hub in data.get("modbus") or []:
            endpoint = f"{hub.get('type')}:{hub.get('port') or hub.get('host')}"
            loaded_from = hubs_loaded.setdefault(endpoint, name)
            for sensor in hub.get("sensors") or []:
                add(sensor.get("unique_id") or f"sensor.{slugify(sensor['name'])}",
                    {"file": name, "kind": "modbus", "hub": hub.get("name"),
                     "hub_loaded": loaded_from == name, "definition": sensor})
        for block in data.get("template") or []:
            for domain in ("sensor", "binary_sensor"):
                for item in block.get(domain) or []:
                    add(item.get("unique_id") or f"{domain}.{slugify(item['name'])}",
                        {"file": name, "kind": "template", "definition": item})
        for domain in ("sensor", "binary_sensor"):
            for item in data.get(domain) or []:
                if not isinstance(item, dict) or "platform" not in item:
                    continue
                add(item.get("unique_id") or f"{domain}.{slugify(item['name'])}",
                    {"file": name, "kind": item["platform"], "definition": item})
    return found


def observed(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    values = [s for s in counts if s not in SENTINEL_STATES]
    summary: dict = {"records": len(rows),
                     "first": rows[0]["last_changed"] if rows else None,
                     "sentinels": {s: counts[s] for s in SENTINEL_STATES if s in counts}}
    if len(values) <= MAX_ENUMERATED:
        summary["states"] = dict(sorted(((s, counts[s]) for s in values),
                                        key=lambda kv: (-kv[1], kv[0])))
    else:
        numbers = []
        for value in values:
            with contextlib.suppress(ValueError):
                numbers.append(float(value))
        summary["distinct"] = len(values)
        if numbers:
            summary["min"], summary["max"] = min(numbers), max(numbers)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ha", required=True, help="Home Assistant base URL")
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--ssh", required=True, help="user@host of the Home Assistant machine")
    ap.add_argument("--config", required=True, help="config directory on that host")
    ap.add_argument("--site", required=True, help="site code, used in the history file name")
    ap.add_argument("--prefix", default="sherpa")
    ap.add_argument("--days", type=float, default=90.0, help="history to read (recorder keeps 90)")
    ap.add_argument("--out-dir", default="tests/fixtures")
    args = ap.parse_args(argv)

    with open(os.path.expanduser(args.token_file), encoding="utf-8") as fh:
        ha = HomeAssistant(args.ha, fh.read().strip())
    pattern = re.compile(rf"^(sensor|binary_sensor)\.{re.escape(args.prefix)}_")
    end = dt.datetime.now(dt.UTC).replace(microsecond=0)
    start = end - dt.timedelta(days=args.days)

    config = ha.rest("/api/config")
    states = {s["entity_id"]: s for s in ha.rest("/api/states") if pattern.match(s["entity_id"])}
    (listing,) = ha.ws({"type": "config/entity_registry/list"})
    ids = sorted(e["entity_id"] for e in listing if pattern.match(e["entity_id"]))
    registry, statistics = ha.ws({"type": "config/entity_registry/get_entries", "entity_ids": ids},
                                 {"type": "recorder/list_statistic_ids"})
    statistics = {s["statistic_id"]: s for s in statistics if pattern.match(s["statistic_id"])}
    texts = fetch_packages(args.ssh, args.config, args.prefix)
    definitions = yaml_definitions(texts)
    print(f"{len(states)} entities, {len(registry)} in the registry, {len(statistics)} with "
          f"long-term statistics; YAML from {', '.join(texts)}", file=sys.stderr)

    entities: dict[str, dict] = {}
    histories: dict[str, list[dict]] = {}
    for entity_id in sorted(set(states) | set(registry)):
        domain, _, key = entity_id.partition(".")
        key = key[len(args.prefix) + 1:]
        entry = registry.get(entity_id) or {}
        state = states.get(entity_id, {})
        attrs = state.get("attributes", {})
        unique_id = entry.get("unique_id")
        source = definitions.get(unique_id) if unique_id else definitions.get(entity_id)
        stat = statistics.get(entity_id)
        rows = ha.history(entity_id, start, end)
        histories[entity_id] = rows
        entities[entity_id] = {
            "key": key,
            "domain": domain,
            "platform": entry.get("platform") or (source or {}).get("kind"),
            "unique_id": unique_id,
            "in_registry": bool(entry),
            "friendly_name": attrs.get("friendly_name"),
            "entity_category": entry.get("entity_category"),
            "disabled_by": entry.get("disabled_by"),
            "unit": attrs.get("unit_of_measurement"),
            "device_class": attrs.get("device_class"),
            "state_class": attrs.get("state_class"),
            "icon": attrs.get("icon"),
            "statistics": None if stat is None else {
                "unit": stat.get("statistics_unit_of_measurement"),
                "unit_class": stat.get("unit_class"),
                "has_mean": bool(stat.get("has_mean") or stat.get("mean_type")),
                "has_sum": bool(stat.get("has_sum")),
            },
            "state_at_capture": state.get("state"),
            "defined_in": (source or {}).get("file"),
            "shadowed_in": (source or {}).get("shadowed_in", []),
            "kind": (source or {}).get("kind"),
            "hub_loaded": (source or {}).get("hub_loaded"),
            "definition": (source or {}).get("definition"),
            "history": observed(rows),
        }
        print(f"  {entity_id:46} {len(rows):6} history rows", file=sys.stderr)

    os.makedirs(args.out_dir, exist_ok=True)
    legacy = {
        "captured_at": end.isoformat(),
        "site": args.site,
        "ha_version": config.get("version"),
        "history_window": {"start": start.isoformat(), "end": end.isoformat()},
        "source_files": {name: hashlib.sha256(text.encode()).hexdigest()
                         for name, text in texts.items()},
        "entities": entities,
    }
    write(os.path.join(args.out_dir, "legacy_entities.json"), legacy)

    t0 = start.timestamp()
    replay = {
        "captured_at": end.isoformat(),
        "site": args.site,
        "start": start.isoformat(),
        "format": "entity_id -> [[seconds since start, state], ...]; a state holds until the next",
        "entities": {
            entity_id: [[round(dt.datetime.fromisoformat(r["last_changed"]).timestamp() - t0, 3),
                         r["state"]] for r in histories[entity_id]]
            for entity_id in (f"{d}.{args.prefix}_{s}" for s in REPLAY_SUFFIXES
                              for d in ("sensor", "binary_sensor"))
            if entity_id in histories
        },
    }
    write(os.path.join(args.out_dir, f"history_{args.site}.json"), replay)
    return 0


def write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {path} ({os.path.getsize(path) // 1024} KiB)", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
