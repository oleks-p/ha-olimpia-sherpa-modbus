# The write check

From 0.2.0 the integration can write a small set of setpoints, but a register is
writable only after it has passed the **write check on that very unit**. This is
how a register earns that, and how to run the check on a live installation.

## What gates a write

Every one of these must hold, every time:

1. The entry's **Allow writes** option is on. It is off by default; with it
   off, no number or switch entity exists and the check refuses to run.
2. The register is a **write candidate** (`registers.WRITE_SPECS`, 19 of them:
   17 numbers, 2 switches). A register in `FORBIDDEN_WRITES` can never be one;
   an import-time assertion and a test hold that.
3. The write check **passed for it on this unit and firmware**. The result is
   stored with the unit's identify code and firmware; a firmware update voids it.
4. The value is **in range and on the step** of its spec.
5. It **differs** from what the unit holds now, read fresh from the unit (no write
   when it already matches).
6. The **rate limits** allow it: one write per register per 10 s, and 50 per unit
   in any 24 hours (counted since Home Assistant started).

Then the write goes out (FC6), is **read back**, and the entities show the
read-back value at once. A value the unit did not take is an error, and the
entity keeps showing what the unit really holds. Each write fires
`olimpia_sherpa_modbus_parameter_written` (old, new, read-back, user) and is
listed in the diagnostics.

## What the check does

`olimpia_sherpa_modbus.verify_write` (admin only), for one register:

1. reads the current value; if it is outside the spec, stops: **unverifiable**,
   nothing written;
2. writes that same value back: a Modbus exception here means **refused**;
3. records the restore it now owes (in `.storage/olimpia_sherpa_modbus.write_checks`);
4. writes **one step away** (up, or down at the top of the range; a switch flips),
   reads at once and again after the hold (default 5 s):
   - unchanged at once → **ignored**: the unit acknowledged but did not apply it;
   - changed, then back → **reverted**: the controller put its own value back;
   - changed and still changed → **roundtrip_ok**;
5. always writes the original back and reads it, up to three tries.

If the restore fails, the action fails, a persistent **repair issue** names the
register and the value to set on the panel, and the owed restore stays on
record. The next setup of the entry finishes it: if the register still holds the
test value, the original goes back; if it holds anything else (set by hand
since), nothing is written and the issue clears. With writes switched off in
between, nothing is written and the issue stays.

Writes and checks on one unit run one at a time, so a write made during a
check's hold waits for the restore and then stands.

## Running it on a live unit

Needs 0.2.0 installed, **Allow writes** on (*Settings → Devices & services →
Sherpa → Configure*), and an admin token. Home Assistant keeps running: the
check uses the integration's own connection, so there is still one master on
the bus.

```bash
python3 tools/verify_writes.py --ha http://homeassistant.local:8123 \
    --token-file ~/.ha-token --only heating_eco_setpoint
```

- `--list` prints the order without writing anything.
- Without `--only` it walks every candidate, **safest first**. ECO and cooling
  parameters come first; while the curves run heating they cannot affect the
  plant. The curve enables come last.
- It stops at the first result that is not `roundtrip_ok`: something about the
  unit is not as expected, and that is worth a look before more writes.
- `--out results.json` keeps the full step-by-step results.

The same action is in *Developer tools → Actions* ("Verify write"), with the
response shown in place.

### Reading the results

| Result | Meaning | Next |
|---|---|---|
| `roundtrip_ok` | Applied and held | Its number/switch entity appears (service dashboard) |
| `ignored` | Acknowledged, not applied | Leave it read-only. Not seen on the reference unit, even with ADDR220 = 0 (see below) |
| `reverted` | Applied, then undone by the controller | Leave it read-only; note which register |
| `refused` | Modbus exception | Leave it read-only |
| `unverifiable` | Current value outside the spec | Widen the spec only with evidence from the manual or the panel's limits |

**ADDR220 (remote controls)** is 0 on the reference unit: display only. The
manual suggests a unit in that mode might ignore serial writes. The reference
unit does not, at least for setpoints: it applied a serial write and held it,
with 220 = 0. So setpoints need no change to 220. Setting 220 = 1 would hand
control to RS-485, but it also disables the display's mode and timer settings.
Whether mode commands need it is a question for the mode-research phase (P5).
The integration never changes 220 itself: it is forbidden.

**Persistence.** A `roundtrip_ok` shows the value applied and held for the hold;
it does not show the value survives a power cycle (EEPROM). Note the value of a
verified register before the next power outage, and check it afterwards.

## Results on the reference unit

Unit: SHERPA S2 BIG + SHERPA S2 14T, identify code 1134, firmware 0.57, site
the reference unit. Integration 0.2.0, ADDR220 = 0 (display only), both climatic curves on,
the unit in standby.

| Date (local time) | Register | Steps (write -> read) | Hold | Result |
|---|---|---|---|---|
| 2026-10-13 16:27 | 209 `heating_eco_setpoint` | 30.0 -> 30.0; 30.5 -> 30.5, 30.5 after 5 s; restored 30.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:32 | 207 `cooling_eco_setpoint` | 18.0 -> 18.0; 18.5 -> 18.5, 18.5 after 5 s; restored 18.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:32 | 206 `cooling_setpoint` | 15.0 -> 15.0; 15.5 -> 15.5, 15.5 after 5 s; restored 15.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:32 | 239 `cooling_curve_max_water_outdoor` | 20.0 -> 20.0; 20.5 -> 20.5, 20.5 after 5 s; restored 20.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:32 | 240 `cooling_curve_max_water` | 18.0 -> 18.0; 18.5 -> 18.5, 18.5 after 5 s; restored 18.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:33 | 241 `cooling_curve_min_water_outdoor` | 40.0 -> 40.0; 40.5 -> 40.5, 40.5 after 5 s; restored 40.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:33 | 242 `cooling_curve_min_water` | 15.0 -> 15.0; 15.5 -> 15.5, 15.5 after 5 s; restored 15.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:33 | 233 `legionella_duration` | 30 min -> 30 min; 40 min -> 40 min, 40 min after 5 s; restored 30 min | 5 s | `roundtrip_ok` |
| 2026-10-13 16:33 | 232 `legionella_setpoint` | 65.0 -> 65.0; 66.0 -> 66.0, 66.0 after 5 s; restored 65.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:33 | 238 `dhw_hysteresis` | 10.0 -> 10.0; 10.5 -> 10.5, 10.5 after 5 s; restored 10.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:33 | 210 `dhw_setpoint` | 50.0 -> 50.0; 50.5 -> 50.5, 50.5 after 5 s; restored 50.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:33 | 208 `heating_setpoint` | 35.0 -> 35.0; 35.5 -> 35.5, 35.5 after 5 s; restored 35.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:35 | 369 `water_setpoint_correction` | 0.0 -> 0.0; 0.5 -> 0.5, 0.5 after 5 s; restored 0.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:35 | 243 `heating_curve_max_water_outdoor` | -5.0 -> -5.0; -4.5 -> -4.5, -4.5 after 5 s; restored -5.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:35 | 244 `heating_curve_max_water` | 35.0 -> 35.0; 35.5 -> 35.5, 35.5 after 5 s; restored 35.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:35 | 245 `heating_curve_min_water_outdoor` | 20.0 -> 20.0; 20.5 -> 20.5, 20.5 after 5 s; restored 20.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:35 | 246 `heating_curve_min_water` | 28.0 -> 28.0; 28.5 -> 28.5, 28.5 after 5 s; restored 28.0 | 5 s | `roundtrip_ok` |
| 2026-10-13 16:35 | 211 `cooling_curve_enabled` | on -> on; off -> off, off after 5 s; restored on | 5 s | `roundtrip_ok` |
| 2026-10-13 16:36 | 212 `heating_curve_enabled` | on -> on; off -> off, off after 5 s; restored on | 5 s | `roundtrip_ok` |

All 19 candidates pass: they are applied, and they hold, with ADDR220 = 0. The
checks ran in three runs (16:27, 16:32-16:33, 16:35-16:36). After each run,
every register read its original value again. The unit stayed in standby with
no error, and there were no repair issues and no link failures.

Still open:
- Persistence over a power cycle (EEPROM) is not checked for any register.
