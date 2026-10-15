# Changelog

## 0.5.1 — 2026-10-15

- The integration ships its icon, Olimpia Splendid's "OS" mark, in `brand/`
  (256 px and 512 px). Home Assistant 2026.x serves a custom integration's icon
  from there. The integrations page, Repairs and HACS showed "icon not
  available" without it.

## 0.5.0 — 2026-10-13

Lovelace cards, built in (P7).

- **Sherpa schematic** (`custom:sherpa-schematic-card`). It draws the outdoor
  unit, the indoor unit, the three-way valve, the heating or cooling circuit and
  the hot-water tank.
  - The live water route is coloured and animates while the pump runs.
  - The route follows the unit's mode, not the valve output, because ADDR259
    can invert the valve's polarity.
  - It shows the compressor, the pump, EH1/EH2 and K5, defrost and night, the
    water temperatures on the pipes they measure, the tank against its setpoint,
    and faults with their descriptions.
- **Sherpa status and setpoints** (`custom:sherpa-control-card`).
  - The mode is shown as the panel has it, and is read-only.
  - The water is shown against its target.
  - The climatic curve is drawn with today's operating point.
  - The hot-water tank is shown against its setpoint.
  - Setpoints get a stepper only where the verified number entity exists, and a
    lock elsewhere. Taps are collected for 1.5 s and sent as one write, which
    respects the integration's limit of one write per register every 10 s.
- English and Ukrainian, following the user's language. A `labels:` option
  overrides single strings.
- The integration serves the bundle itself and adds it to the Lovelace
  resources (`?v=<version>`). An older release's entry is repointed rather than
  duplicated, and YAML-mode dashboards are left to their owner. A failure here
  never affects the entities.
- The climate entity now carries both climatic curves as attributes, for the
  cards; their sensors are disabled by default.
- The cards follow the another integration cards' design tokens. The schematic always draws
  on the dark ground, and its readouts scale with
  the card width.

## 0.4.0 — 2026-10-13

A read-only climate entity, from what the P5 mode research found
(`docs/p5_mode_research.md`).

- `climate.<prefix>_heat_pump` shows:
  - the mode selected on the panel: heating, cooling or off;
  - what the unit is doing: heating, cooling, idle, defrosting or off. A DHW
    cycle reads as idle, because the compressor is serving the tank, not the
    rooms;
  - the supply water temperature.
  It offers only the mode the unit is in, and no target to set: Modbus has no
  mode command while the panel is in control (ADDR220 = 0).
- During a DHW or legionella cycle, the selection stays what it was before the
  cycle, because the unit sets the heating bit for every DHW cycle.
- `sensor.<prefix>_water_target` (calculated). It is the climatic curve's
  water temperature at the current outdoor temperature, or the fixed setpoint
  while the curve is off. The unit does not report its target. ECO and the
  water setpoint correction cannot be seen over Modbus, so they are not
  included.

## 0.3.0 — 2026-10-13

For the mode research (P5).

- New admin action **Read registers** (`olimpia_sherpa_modbus.read_registers`).
  It returns raw holding registers through the integration's own connection:
  one master on the bus, and Home Assistant keeps running.
  - Without an address it takes a snapshot of every register the unit is known
    to answer.
  - Ranges the unit refuses are listed, not raised as errors.
  - It only ever reads (FC3), and it does not need *Allow writes*.
- `tools/mode_research.py` takes labelled snapshots through that action and
  diffs them. Registers that also change on their own are kept apart, so the
  register that follows the panel stands out.

## 0.2.0 — 2026-10-13

Opt-in writes, and the write check that has to pass before any.

- New option **Allow writes**, off by default. With it off nothing changes:
  no number or switch entities, and nothing is ever written.
- New admin action **Verify write** (`olimpia_sherpa_modbus.verify_write`).
  It proves that one register can be written on this unit:
  - it writes the register's own value back, then a value one step away;
  - it reads that test value at once and again after a hold;
  - it always writes the original back.
  Results are `roundtrip_ok`, `ignored`, `reverted`, `refused` or
  `unverifiable`. They are stored per unit, identify code and firmware, so a
  firmware update voids them. See `docs/write_check.md`.
- A restore the check still owes (a restart during the hold, or a failed
  restore) is saved before the test value goes out, and finished at the next
  setup. A failed restore raises a persistent repair issue.
- Number entities for 17 setpoints and climatic-curve points, and switches for
  the two curve enables. Each appears only after its check passes.
- Every write is checked for range and step, skipped if the unit already holds
  the value, rate-limited, read back, shown at once and fired as
  `olimpia_sherpa_modbus_parameter_written`. Writes and checks on one unit run
  one at a time.
- `dashboards/sherpa_service.yaml`, an installer board for the writable
  parameters. `tools/verify_writes.py` runs the check over the REST API, safest
  register first.
- `entities.json` lists the number and switch entities (`writable: true`).
- The read-only sensors are unchanged. Entity ids, units and state classes are
  the same as in 0.1.0.
- Shown as **Olimpia Splendid Sherpa (Modbus)**, without "S2". The domain
  `olimpia_sherpa_modbus` is unchanged, so nothing migrates. Which units are
  supported is still decided by the identify code; see the README.

## 0.1.0 — 2026-10-13

First release. Read-only.

- Config flow for a USB/RS-485 adapter, an RTU-over-TCP serial server or a
  Modbus TCP gateway. Identity check (identify code 1134); other layouts are
  refused with a repair issue.
- Reconfigure (move the unit to another port) and an option for how long the
  link may fail before entities go unavailable.
- Entities for the temperatures, the mode (enum, translated), status, output and
  fault bits, error and override codes, runtime counters, setpoints, service
  parameters and link health. English and Ukrainian.
- Entity ids, units and state classes match a YAML modbus setup with the same names, so
  history and long-term statistics carry over at the cutover. Deliberate
  changes from that setup:
  - `sensor.sherpa_mode` states are now translation keys: `domestic hot water`
    is now `domestic_hot_water`, and `anti-legionella` is now `anti_legionella`.
  - `pump_duty`, `water_delta` and `error` are unknown rather than 0 or false
    when their inputs are unknown.
  - An implausible all-zero inputs word is held over rather than decoded.
- Reads whole runs of answering registers on five poll tiers. A refused block
  falls back to single reads, and normal RTU stalls are ridden out.
- Diagnostics with the raw register words.
