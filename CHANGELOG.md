# Changelog

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
- Entity ids, units and state classes match the reference site's YAML setup, so
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
