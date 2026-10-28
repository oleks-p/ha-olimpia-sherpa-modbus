# Olimpia Splendid Sherpa for Home Assistant (Modbus RTU)

A config-flow integration for Olimpia Splendid **Sherpa** air/water heat
pumps. It talks to the indoor unit over RS-485 (terminal **AB**), either from a
USB adapter on the Home Assistant host or through a network gateway.

It reads by default. **Writes are opt-in:** with *Allow writes* on, a setpoint
becomes writable only after the built-in [write check](docs/write_check.md) has
proved, on this very unit, that the unit applies it and keeps it. The unit's
own controller still runs the plant.

## What you get

- **Temperatures:** water in/out (T1/T2), DHW tank (T3), outdoor air (T4), and
  the water delta. Probes T5–T8 (Aquadue, solar) appear only when fitted.
- **What it is doing:** a mode sensor (standby / cooling / heating / domestic
  hot water / anti-legionella, translated) plus one binary sensor per status
  bit: night, pending, DHW cycle, legionella.
- **Compressor running:** the unit has no bit for this. It is derived from the
  rate of the runtime counter.
- **Outputs:** circulation pump and duty, 3-way valve, electric heaters EH1/EH2,
  external boiler call, alarm relay.
- **Faults:** error codes E01–E27 and override codes OR01–OR13, with their
  descriptions from the manual. Defrost is reported separately.
- **Runtime counters:** compressor, pump and filter, in seconds and hours.
- **Heat pump (climate):** the mode selected on the panel (heating, cooling,
  off), what the unit is doing, the supply water temperature, and a calculated
  water target from the climatic curve. Read-only while the panel is in control:
  Modbus has no mode command then. With [mode control](#mode-control-opt-in) on
  and the panel handed over, it sets off, heat and cool.
- **Hot water (water heater):** the tank temperature and the DHW setpoint. The
  setpoint is settable once its write check has passed. On and off need mode
  control.
- **Mode control (opt-in):** set standby, DHW only, heating, cooling, ECO and
  night from Home Assistant, through register 106. See
  [below](#mode-control-opt-in).
- **Setpoints and service parameters** as sensors. The less common parameters
  are diagnostic entities and disabled by default.
- **Writable setpoints (opt-in):** heating, cooling and their ECO values, DHW,
  anti-legionella, the climatic-curve points and enables, and the water setpoint
  correction. Each becomes a number or switch entity once its write check passes.
  The sensor of the same name stays and keeps the statistics.
- **Link health:** last successful read and read failures. RS-485 stalls of
  10–30 s are normal on this unit and don't make entities unavailable; only an
  outage longer than 120 s (configurable) does.
- **Languages:** English and Ukrainian.

## Supported units

The unit says which register layout it has in register 199 (the identify code),
and the integration reads only layouts it has a map for. Today that is one:

| Identify code | Layout | Status |
|---|---|---|
| 1134 | Sherpa S2 controller | **Verified** on SHERPA S2 BIG + SHERPA S2 14T, firmware 0.57 |

The other indoor units of the S2 range (S2 3W, Tower S2, Aquadue S2) and the
outdoor units S2 E, S2 and S2 T share the S2 controller: registers 370 and
371 list them all. They probably report 1134 and work, but that is not verified yet. The
Aquadue circuit's sensors only appear on an Aquadue.

Any other identify code (Olimpia's documentation gives 1026 for the original
Sherpa and 1061 for the original Aquadue) is refused with a repair issue, not
read with the wrong map. If you have such a unit, capture it with
[the probe](#probe) and open an issue; one capture is enough to add its layout.

## Install

Copy `custom_components/olimpia_sherpa_modbus` into your Home Assistant
`config/custom_components/`, or add this repository to HACS as a custom
repository. Then restart.

**Only one master on the bus.** Stop anything else that polls the Sherpa first,
such as an old `modbus:` YAML configuration or another controller on terminal
AB. Two masters collide and the unit raises E09.

## Configure

*Settings → Devices & services → Add integration → Olimpia Splendid Sherpa*,
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

Options:

- How long the link may fail before entities go unavailable (default 120 s).
- **Allow writes** (default off).
- **Mode control** (default off; needs *Allow writes*).

The connection can be changed later with *Reconfigure*; entity ids and history
are kept.

## Cards

The integration ships two Lovelace cards and registers them itself (on
storage-mode dashboards; for a YAML-mode setup, add
`/olimpia_sherpa_modbus/sherpa-cards.js` as a module resource):

- `custom:sherpa-schematic-card`: the plant, with the water route the heat pump
  is using right now.
- `custom:sherpa-control-card`: the mode, the water against its target, the
  climatic curve, the tank, and the setpoints. Setpoints can be edited only
  where writes are allowed and verified.

Both take `prefix` (default `sherpa`), `title` and `labels`. They follow the
user's language, English or Ukrainian. The sources are in `cards/` (Lit +
TypeScript); `cd cards && npm ci && npm run build` rebuilds the bundle, and CI
checks that the committed bundle matches its source.

`dashboards/sherpa.yaml` is a ready-made dashboard for everyday use. The
schematic view uses
[heat-pump-card](https://github.com/ManfredTremmel/lovelace-heat-pump-card).
`dashboards/sherpa_service.yaml` is an admin board for the writable parameters.

## Writes

With *Allow writes* on, run the **Verify write** action for a parameter. You can
run it from *Developer tools → Actions*, or with `tools/verify_writes.py` for
several in a row. The check:

1. writes the parameter's own value back;
2. writes a value one step away and holds it, reading it at once and after the
   hold;
3. always restores the original.

Only a `roundtrip_ok` result makes the parameter writable. The result is stored
for this unit and firmware, and a firmware update voids it.

Each write is also:

- range- and step-checked;
- skipped if the unit already holds the value;
- rate-limited: once per 10 s per parameter, 50 a day;
- read back.

A value the unit did not take is an error, not a silent change. Parameters that
could hurt the installation or cut communication are never writable, for
example ADDR220, 229, 247 and 401, the model, the cascade, the protections and
the pump PWM. Details: [docs/write_check.md](docs/write_check.md).

## Mode control (opt-in)

Home Assistant can set the unit's operating mode through register 106. The
register facts come from Olimpia's *RDE448, Modbus communication* (not in this
repository); how the unit behaved is in
[docs/p6_mode_command_test.md](docs/p6_mode_command_test.md), and the design in
[docs/p6_mode_control.md](docs/p6_mode_control.md).

**Turn it on:** *Allow writes* and *Mode control* in the options. Then, on the
panel, set **ADDR220 = 1**. Only a person changes ADDR220; the integration never
writes it.

- **While ADDR220 = 1** the unit takes the mode from 106, and Home Assistant
  writes it every 60 s and reads it back. Every write first reads ADDR220 from
  the unit, and stops if it is not 1. Without a write the unit raises E09
  after 255 s: the alarm relay closes and the pump stops for about 3 s, every
  255 s.
- **While ADDR220 is 0 or 2** the panel is in charge. Nothing is written. The
  select, the ECO and night switches and the water heater's on/off are
  unavailable, and the climate is read-only, as without the option.
- **Hand-over to Home Assistant** (ADDR220 0 to 1, after two polls at 0): the
  mode the panel had carries over (heating, cooling or off, and night). ECO can't be seen at
  ADDR220 = 0, so it stays as last set. DHW only is never inferred.
- **Hand-back** (ADDR220 to 0): the panel takes over at once. Do this before a
  long absence, or if the link is down for longer than a few minutes.
- **The mode** is kept across restarts. If Home Assistant restarts, the unit
  keeps its last command, and the first write goes out at once.

What sets what:

| Control | Effect on register 106 |
|---|---|
| Select *Operating mode* | standby sets the standby bit and keeps the rest; DHW only, heating and cooling clear standby |
| Switches *ECO*, *Night mode* | their bit |
| Climate off | heating and cooling both off (DHW only: hot water carries on) |
| Climate heat, cool | that mode, standby cleared |
| Water heater off, on | standby set, standby cleared |

Standby stops hot water too. The climate has no DHW-only mode: DHW only shows
as off, with the attribute `operating_mode: dhw_only`.

Three repair issues say when something is wrong: ADDR220 = 1 with nothing
keeping the unit fed (set ADDR220 = 0, or turn on mode control); no write for
over 255 s; the unit not holding the word written. Each says to set ADDR220 = 0
on the panel if it lasts.

The **Write mode command** action stays for research, and is refused while mode
control is active.

## How it talks to the unit

Measured on the reference unit, and enforced by the tests:

- Everything is a **holding register** (FC3). The address is the Olimpia
  parameter number. FC4 is not supported.
- A read that spans an address the unit does not have is **refused**. Inside a
  run of answering registers any length works, up to the longest run (65
  registers). The integration reads whole runs, polls on five tiers (10 s to
  1 h), and makes 6 requests per 10 s cycle.
- Counters are 32-bit, **high word first**.
- The unit needs **60 ms** between frames. After a failed exchange the link is
  reset and left quiet for a second, because RTU has no transaction id and a
  late reply must not be taken as the next answer.

## Raw reads

The admin action **Read registers** returns raw register words through the
integration's own connection, with Home Assistant running. Without an address
it reads every register the unit is known to answer. `tools/mode_research.py`
snapshots and diffs them, to find what an undocumented register does by
changing one thing on the panel at a time.

## Probe

`tools/probe_sherpa.py` is a standalone, standard-library-only script (Python
3.11+). It captures a unit's register map and read rules into the JSON the
tests are built on. It never writes to the unit, and it will not talk while
another master is active. (Writes are verified through the integration instead,
see [Writes](#writes).) See [docs/probe_runbook.md](docs/probe_runbook.md).

## Development

```bash
uv venv --python 3.14 .venv && uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest          # integration (HA 2026.8.2) + probe + fixtures
.venv/bin/ruff check custom_components tools tests
docker compose up -d                # a dev Home Assistant against a simulated unit
.venv/bin/python tools/gen_translations.py   # strings.json + en/uk from one table
.venv/bin/python tools/export_entities.py    # entities.json, the entity manifest
```

- `tests/integration`: the integration against a fake built from the reference
  unit's capture.
- `tests/probe`: the probe, against a simulated unit on a pseudo-terminal and
  on TCP.
- `docs/p0_findings.md`: what the evidence showed, and the decisions taken from
  it.
