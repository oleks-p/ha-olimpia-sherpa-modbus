# Olimpia Splendid Sherpa S2 for Home Assistant (Modbus RTU)

A config-flow integration for the Olimpia Splendid **Sherpa S2** air/water heat
pump. It talks to the indoor unit over RS-485 (terminal **AB**), either from a
USB adapter on the Home Assistant host or through a network gateway.

**v0.1.0 is read-only.** It reports what the unit is doing and never sends
anything but reads; the unit's own controller owns every setpoint. Writable
setpoints, behind an option that is off by default, are planned for v0.2.0.

## What you get

- **Temperatures:** water in/out (T1/T2), DHW tank (T3), outdoor air (T4), and
  the water delta. Probes T5–T8 (Aquadue, solar) appear only when fitted.
- **What it is doing:** a mode sensor (standby / cooling / heating / domestic
  hot water / anti-legionella, translated) plus one binary sensor per status
  bit: night, pending, DHW cycle, legionella.
- **Compressor running:** the unit has no bit for this. It is derived from the
  runtime counter, and over 57 days of recorded history it agrees with the
  reference site's previous setup in 99.9 % of samples.
- **Outputs:** circulation pump and duty, 3-way valve, electric heaters EH1/EH2,
  external boiler call, alarm relay.
- **Faults:** error codes E01–E27 and override codes OR01–OR13, with their
  descriptions from the manual. Defrost is reported separately.
- **Runtime counters:** compressor, pump and filter, in seconds and hours.
- **Setpoints and service parameters**, read-only. The less common parameters
  are diagnostic entities and disabled by default.
- **Link health:** last successful read and read failures. RS-485 stalls of
  10–30 s are normal on this unit and don't make entities unavailable; only an
  outage longer than 120 s (configurable) does.
- **Languages:** English and Ukrainian.

Tested against **SHERPA S2 BIG + SHERPA S2 14T, firmware 0.57, identify code
1134**. Other register layouts are refused with a repair issue rather than read
wrongly. If you have one, capture it with [the probe](#probe) and open an issue.

## Install

Copy `custom_components/olimpia_sherpa_modbus` into your Home Assistant
`config/custom_components/`, or add this repository to HACS as a custom
repository. Then restart.

**Only one master on the bus.** Stop anything else that polls the Sherpa first,
such as an old `modbus:` YAML configuration or an i3 controller. Two masters
collide and the unit raises E09.

## Configure

*Settings → Devices & services → Add integration → Olimpia Splendid Sherpa S2*,
then choose:

- **USB / RS-485 adapter**
  - The serial port: prefer a `/dev/serial/by-id/...` path.
  - Baud rate: 9600.
  - The unit's Modbus address: parameter **ADDR247**, factory default 1.
- **Network gateway**
  - Host and port.
  - *Transparent serial server (RTU over TCP)* or *Modbus TCP gateway*.
  - The Modbus address, as above.

The **entity ID prefix**, default `sherpa`, starts every entity id
(`sensor.sherpa_water_in`, …). Keep `sherpa` to take over the entity ids,
history and long-term statistics of an existing YAML setup that used the same
names.

Options: how long the link may fail before entities go unavailable (default
120 s). The connection can be changed later with *Reconfigure*; entity ids and
history are kept.

`dashboards/sherpa.yaml` is a ready-made dashboard. The schematic view uses
[heat-pump-card](https://github.com/ManfredTremmel/lovelace-heat-pump-card).

## How it talks to the unit

Measured on the reference unit, and enforced by the tests:

- Everything is a **holding register** (FC3). The address is the Olimpia
  parameter number. FC4 is not supported.
- A read that spans an address the unit does not have is **refused**. Inside a
  run of answering registers any length works, up to the longest run (65
  registers). The integration reads whole runs, polls on five tiers (10 s to
  1 h), and makes 5 requests per 10 s cycle.
- Counters are 32-bit, **high word first**.
- The unit needs **60 ms** between frames. After a failed exchange the link is
  reset and left quiet for a second, because RTU has no transaction id and a
  late reply must not be taken as the next answer.

## Probe

`tools/probe_sherpa.py` is a standalone, standard-library-only script (Python
3.11+). It captures a unit's register map and read rules into the JSON the
tests are built on. It never writes to the unit, and it will not talk while
another master is active. See [docs/probe_runbook.md](docs/probe_runbook.md).
`tools/pi_probe_run.sh` runs it on a Home Assistant host with HA stopped and
always starts HA again.

## Development

```bash
uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest          # 175 tests: integration (HA 2026.8.2) + probe + fixtures
.venv/bin/ruff check custom_components tools tests
docker compose up -d                # a dev Home Assistant against a simulated unit
```

- `tests/integration`: the integration against a fake built from the reference
  unit's capture. It includes a golden test against the legacy entities, and a
  replay of 57 days of recorded history through the decoders.
- `tests/probe`: the probe, against a simulated unit on a pseudo-terminal and
  on TCP.
- `docs/p0_findings.md`: what the evidence showed, and the decisions taken from
  it.
