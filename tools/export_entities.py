#!/usr/bin/env python3
"""Write entities.json: every entity this release can create, and what it is.

Dashboard tooling can vendor this file per release and
check what it binds against it, so what a dashboard draws and binds can
only name entities the pinned release really provides. A test fails if the
committed file falls behind the code.

    .venv/bin/python tools/export_entities.py            # rewrite entities.json
    .venv/bin/python tools/export_entities.py --check    # exit 1 if it is stale
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "entities.json"


def build() -> dict:
    from custom_components.olimpia_sherpa_modbus.binary_sensor import BINARY_SENSORS
    from custom_components.olimpia_sherpa_modbus.const import DEFAULT_ENTITY_PREFIX, DOMAIN
    from custom_components.olimpia_sherpa_modbus.number import NUMBERS
    from custom_components.olimpia_sherpa_modbus.registers import WRITE_SPECS
    from custom_components.olimpia_sherpa_modbus.sensor import SENSORS
    from custom_components.olimpia_sherpa_modbus.switch import SWITCHES

    manifest = json.loads(
        (ROOT / "custom_components" / DOMAIN / "manifest.json").read_text())

    def record(domain: str, d) -> dict:
        rec = {"domain": domain, "key": d.key}
        for field in ("native_unit_of_measurement", "device_class", "state_class",
                      "entity_category"):
            value = getattr(d, field, None)
            if value is not None:
                rec[field.removeprefix("native_")] = str(value)
        if getattr(d, "options", None):
            rec["options"] = list(d.options)
        if not d.entity_registry_enabled_default:
            rec["enabled_default"] = False
        if domain in ("number", "switch"):
            # Created only with "allow writes" on and the write check passed on
            # the unit: never something a customer dashboard can count on.
            spec = WRITE_SPECS[d.key]
            rec["writable"] = True
            if domain == "number":
                rec.update(min=spec.minimum, max=spec.maximum, step=spec.step)
        elif d.present_fn is not None:
            rec["conditional"] = True   # created only when the hardware reports it
        return rec

    return {
        "domain": DOMAIN,
        "version": manifest["version"],
        "default_entity_prefix": DEFAULT_ENTITY_PREFIX,
        # Off by default; then per register, after the write check (writes.py).
        "writes": "opt_in",
        "entity_id": "<domain>.<entity_prefix>_<key>",
        "entities": [record("sensor", d) for d in SENSORS]
        + [record("binary_sensor", d) for d in BINARY_SENSORS]
        + [record("number", d) for d in NUMBERS]
        + [record("switch", d) for d in SWITCHES],
    }


def render() -> str:
    return json.dumps(build(), indent=1, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="fail if entities.json is stale")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print("entities.json is stale; run tools/export_entities.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(build()['entities'])} entities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
