# Olimpia Splendid Sherpa S2 for Home Assistant (Modbus RTU)

A config-flow custom integration for the Olimpia Splendid Sherpa S2 air/water heat
pump. It talks to the indoor unit over RS-485 (terminal AB), either directly from
a USB adapter or through a Modbus-TCP / RTU-over-TCP gateway.

**Status: phase P0, evidence gathering.** The integration itself does not exist
yet. This repository currently holds the probe that captures how a real unit
behaves. That capture is the test fixture everything else is built against. The
full plan is in `~/Downloads/olimpia holdings/IMPLEMENTATION_PLAN.md`.

## Evidence (P0)

| What | Where |
|---|---|
| Register probe: identity, 0–999 sweep, block-read rules, link timing | `tools/probe_sherpa.py`, [docs/probe_runbook.md](docs/probe_runbook.md) |
| Legacy YAML entities: registry, units, statistics, definitions, states seen | `tools/legacy_snapshot.py` → `tests/fixtures/legacy_entities.json` |
| 57 days of recorder history for the state words and derived entities | `tools/legacy_snapshot.py` → `tests/fixtures/history_reference.json` |
| What the evidence shows, and the decisions it hands to P1 | [docs/p0_findings.md](docs/p0_findings.md) |
| Python versions of the legacy templates, checked by replaying history | `tests/legacy.py`, `tests/test_fixtures.py` |

## Probe

`tools/probe_sherpa.py` is a standalone, standard-library-only script (Python
3.11+). It runs on the Home Assistant host as-is. It never writes to the unit,
and on a shared bus it will not talk while another master is active.

```bash
python3 tools/probe_sherpa.py --serial /dev/serial/by-id/usb-FTDI_..._port0 \
  --i-stopped-home-assistant
```

Read [docs/probe_runbook.md](docs/probe_runbook.md) before running it against a
live unit.

## Development

```bash
uv run --no-project --python 3.11 --with pytest -- python -m pytest
uv run --no-project --with 'ruff>=0.6' -- ruff check tools tests
```

`tools/legacy_snapshot.py` reads a live Home Assistant: REST, websocket list
commands, and `cat` over ssh. It needs two extra packages:

```bash
uv run --no-project --with websockets --with pyyaml -- python tools/legacy_snapshot.py --help
```

The tests run the probe against `tests/sim.py`, which puts a simulated Sherpa
behind a pseudo-terminal or a TCP socket. The real termios, framing and
fault-handling code runs without hardware. The simulator can stall, corrupt
CRCs, reply late, echo frames and go silent on chosen addresses.
