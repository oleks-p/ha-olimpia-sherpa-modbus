#!/usr/bin/env python3
"""Find undocumented registers by changing one thing on the panel at a time.

Each `snap` reads every answering register through the integration's admin
action read_registers (one master on the wire; Home Assistant keeps running),
saves it under a label, and diffs it against the previous snapshot and the
first one. Registers that also change on their own -- temperatures, counters,
whatever moved between the two `baseline` snapshots -- are listed apart, so
the register that follows the panel stands out.

    python3 tools/mode_research.py --ha http://homeassistant.local:8123 \\
        --token-file ~/.ha-token baseline
    python3 tools/mode_research.py ... snap heating-selected
    python3 tools/mode_research.py ... diff 00-baseline 03-heating-selected

Only ever reads. The token is read from the file and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN = "olimpia_sherpa_modbus"


def _names() -> dict[int, str]:
    """address -> key, for the registers the integration already maps."""
    sys.path.insert(0, str(ROOT))
    try:
        from custom_components.olimpia_sherpa_modbus.registers import REGISTERS
    except ImportError:          # no Home Assistant installed: diff without names
        return {}
    names = {}
    for reg in REGISTERS:
        for offset, address in enumerate(range(reg.address, reg.end + 1)):
            names[address] = reg.key if reg.end == reg.address else f"{reg.key}[{offset}]"
    return names


#: Addresses the reference unit refuses (P0 sweep, ADDR220 = 0) near the ones it
#: answers: where a register that only exists in another mode would be.
GAPS = ((10, 11), (103, 104), (196, 196), (201, 205), (214, 216), (282, 284), (286, 289),
        (335, 336), (342, 342), (373, 379), (389, 400), (409, 499), (508, 560))


def read(base: str, token: str, address: int | None = None, count: int = 1) -> dict:
    body = {} if address is None else {"address": address, "count": count}
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/services/{DOMAIN}/read_registers?return_response",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["service_response"]


def changes(a: dict, b: dict) -> dict[int, tuple[int | None, int | None]]:
    ra, rb = a["registers"], b["registers"]
    return {int(k): (ra.get(k), rb.get(k)) for k in sorted(set(ra) | set(rb), key=int)
            if ra.get(k) != rb.get(k)}


def bits(old: int | None, new: int | None) -> str:
    if old is None or new is None:
        return ""
    on = [i for i in range(16) if (new >> i) & 1 and not (old >> i) & 1]
    off = [i for i in range(16) if (old >> i) & 1 and not (new >> i) & 1]
    return " ".join(filter(None, [f"+bit{on}" if on else "", f"-bit{off}" if off else ""]))


def show(title: str, diff: dict, noise: set[int], names: dict[int, str]) -> None:
    signal = {a: v for a, v in diff.items() if a not in noise}
    print(f"  {title}: {len(signal)} changed" + (f" (+{len(diff) - len(signal)} noisy)" if
                                                 len(diff) != len(signal) else ""))
    for address, (old, new) in signal.items():
        name = names.get(address, "UNMAPPED")
        print(f"    {address:>4}  {old!s:>6} -> {new!s:<6} {bits(old, new):<20} {name}")


class Session:
    def __init__(self, directory: pathlib.Path) -> None:
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def snapshots(self) -> list[pathlib.Path]:
        return sorted(p for p in self.dir.glob("[0-9][0-9]-*.json"))

    def load(self, name: str) -> dict:
        matches = [p for p in self.snapshots() if p.stem == name or p.stem.startswith(name)]
        if len(matches) != 1:
            raise SystemExit(f"no single snapshot matches {name!r}")
        return json.loads(matches[0].read_text())

    def save(self, label: str, snapshot: dict) -> pathlib.Path:
        snapshot["label"] = label
        last = self.snapshots()[-1].name[:2] if self.snapshots() else "-1"
        path = self.dir / f"{int(last) + 1:02d}-{label}.json"
        path.write_text(json.dumps(snapshot, indent=1) + "\n")
        return path

    @property
    def noise(self) -> set[int]:
        path = self.dir / "noise.json"
        return set(json.loads(path.read_text())) if path.exists() else set()

    def add_noise(self, addresses) -> None:
        (self.dir / "noise.json").write_text(json.dumps(sorted(self.noise | set(addresses))) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ha", default="http://homeassistant.local:8123")
    ap.add_argument("--token-file", default="~/.ha-token")
    ap.add_argument("--dir", default=str(ROOT / "research" / "modes"),
                    help="where the snapshots go (default research/modes)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baseline", help="two snapshots 15 s apart; what differs is noise")
    snap = sub.add_parser("snap", help="snapshot now, and diff it")
    snap.add_argument("label")
    diff = sub.add_parser("diff", help="diff two saved snapshots")
    diff.add_argument("a")
    diff.add_argument("b")
    sub.add_parser("noise", help="list the registers treated as noise")
    gaps = sub.add_parser("gaps", help="read every usually-refused address, one at a time")
    gaps.add_argument("label")
    args = ap.parse_args(argv)

    session, names = Session(pathlib.Path(args.dir)), _names()
    if args.cmd == "diff":
        show(f"{args.a} -> {args.b}", changes(session.load(args.a), session.load(args.b)),
             session.noise, names)
        return 0
    if args.cmd == "noise":
        print(", ".join(f"{a} {names.get(a, 'UNMAPPED')}" for a in sorted(session.noise)))
        return 0

    with open(os.path.expanduser(args.token_file), encoding="utf-8") as fh:
        token = fh.read().strip()
    if args.cmd == "gaps":
        answered, refused = {}, []
        for start, end in GAPS:
            for address in range(start, end + 1):
                result = read(args.ha, token, address)
                answered.update(result["registers"])
                refused += [r["address"] for r in result["refused"]]
        path = session.dir / f"gaps-{args.label}.json"
        path.write_text(json.dumps({"label": args.label, "registers": answered,
                                    "refused": refused}, indent=1) + "\n")
        print(f"{path.name}: {len(answered)} answered, {len(refused)} refused"
              + (": " + ", ".join(f"{a}={v}" for a, v in answered.items()) if answered else ""))
        return 0
    if args.cmd == "baseline":
        first = read(args.ha, token)
        time.sleep(15)
        second = read(args.ha, token)
        session.save("baseline", first)
        session.save("baseline-again", second)
        moved = changes(first, second)
        session.add_noise(moved)
        print(f"baseline: {len(first['registers'])} registers, {len(first['refused'])} refused "
              f"runs; {len(moved)} moved on their own (noise): "
              + ", ".join(f"{a} {names.get(a, 'UNMAPPED')}" for a in moved))
        return 0

    before = session.snapshots()
    current = read(args.ha, token)
    path = session.save(args.label, current)
    print(f"{path.name}: {len(current['registers'])} registers")
    if before:
        show(f"since {before[-1].stem}", changes(json.loads(before[-1].read_text()), current),
             session.noise, names)
        show(f"since {before[0].stem}", changes(json.loads(before[0].read_text()), current),
             session.noise, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
