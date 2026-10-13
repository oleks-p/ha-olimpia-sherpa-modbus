#!/usr/bin/env python3
"""Run the integration's write check on a live unit, one register at a time.

Calls the admin action olimpia_sherpa_modbus.verify_write over Home Assistant's
REST API, so the check goes through the integration and its bus lock -- still
one master on the wire, and Home Assistant keeps running. Each check writes
the register's own value, then one step away, and always restores it.

The order puts the registers that cannot affect the plant right now first
(ECO setpoints and cooling parameters, while the curves run heating) and the
curve enables last. By default it stops at the first result that is not
roundtrip_ok: the unit is then not behaving as expected, and that deserves a
look before any more writes.

    python3 tools/verify_writes.py --ha http://homeassistant.local:8123 \\
        --token-file ~/.ha-token --only heating_eco_setpoint
    python3 tools/verify_writes.py ... --list         # print the order, write nothing

Standard library only. The token is read from the file and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DOMAIN = "olimpia_sherpa_modbus"

#: Safest first. A test keeps this equal to the integration's write candidates.
ORDER = (
    # no effect while the climatic curves are on (211/212 = 1 on the reference unit)
    "heating_eco_setpoint", "cooling_eco_setpoint",
    # cooling: no effect while the unit heats
    "cooling_setpoint", "cooling_curve_max_water_outdoor", "cooling_curve_max_water",
    "cooling_curve_min_water_outdoor", "cooling_curve_min_water",
    # used only by the legionella cycle, which is off here (interval 0)
    "legionella_duration", "legionella_setpoint",
    # DHW: half a degree or one degree of band for a few seconds
    "dhw_hysteresis", "dhw_setpoint",
    # the fixed heating setpoint, unused while the heating curve is on
    "heating_setpoint",
    # these move the live water target, by one step, for the hold
    "water_setpoint_correction", "heating_curve_max_water_outdoor", "heating_curve_max_water",
    "heating_curve_min_water_outdoor", "heating_curve_min_water",
    # switch how the target is computed: last
    "cooling_curve_enabled", "heating_curve_enabled",
)


def call(base: str, token: str, register: str, hold: int, entry: str | None) -> dict:
    body = {"register": register, "hold_seconds": hold}
    if entry:
        body["config_entry_id"] = entry
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/services/{DOMAIN}/verify_write?return_response",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60 + 2 * hold) as resp:
        return json.loads(resp.read())["service_response"]


def summary(result: dict) -> str:
    restored = result.get("restored", result.get("original"))
    return (f"{result['key']:<34} {result['result']:<13} original {result.get('original')}"
            f"  restored {restored}  (register {result['address']})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ha", help="Home Assistant base URL")
    ap.add_argument("--token-file", help="file holding a long-lived admin token")
    ap.add_argument("--only", help="comma-separated registers, checked in the given order")
    ap.add_argument("--hold", type=int, default=5, help="seconds to hold the test value (1-30)")
    ap.add_argument("--entry", help="config entry id, if more than one Sherpa is set up")
    ap.add_argument("--keep-going", action="store_true",
                    help="carry on past a result that is not roundtrip_ok")
    ap.add_argument("--out", help="also write the full results as JSON here")
    ap.add_argument("--list", action="store_true", help="print the order and exit")
    args = ap.parse_args(argv)

    registers = [r.strip() for r in args.only.split(",")] if args.only else list(ORDER)
    unknown = [r for r in registers if r not in ORDER]
    if unknown:
        ap.error(f"not a write candidate: {', '.join(unknown)}")
    if args.list:
        print("\n".join(registers))
        return 0
    if not (args.ha and args.token_file):
        ap.error("--ha and --token-file are required")
    with open(os.path.expanduser(args.token_file), encoding="utf-8") as fh:
        token = fh.read().strip()

    results, status = [], 0
    for register in registers:
        try:
            result = call(args.ha, token, register, args.hold, args.entry)
        except urllib.error.HTTPError as err:
            # write_failed or restore_failed: stop, whatever --keep-going says.
            # A failed restore also raised a repair issue in Home Assistant.
            detail = err.read().decode(errors="replace").strip().replace("\n", " ")
            if err.code == 500:
                # The REST API does not pass an action's own error on; the log has it
                # (writes off, not a candidate, restore failed, no answer, ...).
                detail += " -- see the Home Assistant log for the reason"
            print(f"{register:<34} ERROR {err.code}: {detail}", file=sys.stderr)
            status = 2
            break
        results.append(result)
        print(summary(result), flush=True)
        if result["result"] != "roundtrip_ok":
            status = 1
            if not args.keep_going:
                print("stopping: not roundtrip_ok (use --keep-going to check the rest)",
                      file=sys.stderr)
                break
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=1)
            fh.write("\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
