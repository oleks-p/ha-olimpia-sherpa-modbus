# Changelog

## 0.2.0 — unreleased

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

## 0.1.0 — unreleased

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
