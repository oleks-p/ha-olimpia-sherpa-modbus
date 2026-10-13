# P0 findings: what the reference site's history shows

Evidence from `tests/fixtures/legacy_entities.json` and
`tests/fixtures/history_uahs01.json`. Both were captured on 2026-10-13 by
`tools/legacy_snapshot.py` from site uahs01: Sherpa S2 BIG + S2 14T, firmware
0.57, HA 2026.8.2.

The recorder keeps 90 days. The Sherpa entities date from **2026-08-17**, so the
capture covers 57 days of summer:
- covered: cooling, DHW and legionella cycles, and E07 episodes
- not covered yet: heating season and defrost

The register probe ran on 2026-10-13: a full run at 09:09 UTC, then a
rules-only run at 09:22 UTC. The merged, sanitized capture is
`tests/fixtures/sherpa_s2_big_14t_fw057.json`. Results are in the first section
below.

## Register probe (2026-10-13)

**Identity matches the reference exactly:**
- firmware 197/198 = 57/57 ("0.57"), identify code 199 = 1134
- IDU model 370 = 2 (SHERPA S2 BIG), ODU model 371 = 14 (SHERPA S2 14T)
- Modbus address 247 = 201, protocol 401 = RTU
- remote controls 220 = 0, DHW source 228 = 2, legionella mode 229 = 2

**The link is clean and fast:**
- 1,046 requests: 0 timeouts, 0 CRC errors, 0 stalls, no echo
- latency p50 35.9 ms, p95 36.0 ms, max 51.9 ms (60 ms frame gap)
- the 0–999 sweep took 96 s
- the 10–30 s stalls in the platform profile did not occur in this run

**The register map:**
- 284 addresses answer.
- The other 716 return exception 2 (ILLEGAL_DATA_ADDRESS) **at once**, never a
  timeout, so a gap costs no time.

  | | Ranges |
  |---|---|
  | Answering | 0–9, 12, 99–102, 105–106, 193–195, 197–200, 206–213, 217–281, 285, 290–334, 337–341, 343–372, 380–388, 401–408, 500–507, 561–624, 900, 910–914, 951–955, 961–965, 999 |
  | Not answering, notable | 10–11, 103–104, **201–205**, 214–216, 282–284, 286–289, 335–336, 342, 373–379 |

**Rules for the block planner:**
- **A read that spans an undefined address fails**, even a 4-register read across
  the 10–11 gap. Blocks must be contiguous runs of answering registers.
  - Register 200 can only be read alone.
  - Mid-run block reads returned the same values as the single reads.
- **u32 halves can be read separately** (271 alone is OK). Read each counter
  pair in one request anyway, so a carry cannot tear it.
- **FC4 (input registers) is unsupported.** Everything is holding.
- **Every answering run reads whole in one request.** A second, rules-only run
  at 09:22 UTC used `--sweep-from`, with 32 s of downtime:
  - all 17 multi-register runs read whole, the longest being 217–281
    (65 registers) and 561–624 (64);
  - a count ladder at 217 succeeded at every step from 2 to 65;
  - block values matched the sweep everywhere.
  - Nothing longer than 65 registers was tested, and nothing needs to be:
    blocks cannot span a gap anyway.
  - Reads get slower with size: a 65-register read takes about 180 ms (p95 for
    the block reads), against 36 ms for a single register.
- **What this means for the poll plan:** each tier becomes a handful of
  whole-run reads. For example, the control tier is 8, 12, 100–102, 105 and 388:
  five requests, because 8 and 12 sit in different runs.

**Undocumented registers that answer (76).** These are the candidates for the
mode-command search in P5:

| Registers | Value now | Note |
|---|---|---|
| 9, 99, 106 | 0 | |
| 193 / 194 / 195 | 991 / 0 / 0 | 193 is the profile's "static" register |
| 218 | 1 | |
| 263–269 | 10, 2, 0, 20, 5, 10, 150 | |
| 290 | 0 | |
| 300–318 | 0 | the cascade capacity and hour counters for heat pumps 4–6, as predicted |
| 327–333 | 5 ×6, 1 | |
| 337–340 | 25, 50, 70, 100 | |
| 402–408 | 0, 0, 0, 100, 0, 5, 0 | |
| 500–507 | 0 | |
| 900, 999 | 0 | |
| 910–914 | 45693, 0, 249, 59169, 13476 | |
| 951–955 | 33692, 0, 0, 33692, 0 | |
| 961–965 | 0 | |

**201–205 do not exist**, so the plan's guess that the mode-command register is
there is wrong. The candidates are the zero-valued registers above, especially
9, 99, 106, 290, 402–408 and 500–507.

**Absent probes:** registers 4–7 read −1, −501, −501, −1. These are T5–T8
(T8 solar = −0.1 °C on the display, T6/T7 = −50.1 °C), matching the profile's
sentinels.

**Curve tables:** 561–592 run 24 → 78 and 593–624 run 24 → 92, both flat-topped,
as the profile describes.

**Eight service parameters differ from the 12 Aug display photos.** Someone
changed them on the unit in the meantime:

| ADDR | Parameter | Photo | Now |
|---|---|---|---|
| 230 | legionella interval | 0 d | **14 d**; explains the 14-day legionella cycles |
| 246 | heating curve min water | 30.0 | **28.0 °C** |
| 248 | DHW limit for ACS_A | 40.0 | **50.0 °C** |
| 253 / 254 | min / max T4 for DHW_A auto | 5.0 / 10.0 | **10.0 / 25.0 °C**, the manual's defaults |
| 292 | heat pumps count | 1 | **0** |
| 334 | cascade circulator behaviour | 0 | **2** |
| 349 | FTV DHW delta | 10.0 | **2.5 °C** |

**Incident:** HA was down 2 min 26 s, from 09:09:09 to 09:11:35 UTC. About 15 s
of that came from a failed restart. The probe's wrapper restarted it from the
wrong directory, and an old `~/compose.yml` there
made `docker compose start` find nothing and still exit 0. HA was started by
hand at 09:11:20 and was healthy at 09:11:35, with no E09 afterwards. The fix is
`tools/pi_probe_run.sh`: it names the compose file explicitly and checks the
container's state.

## Legacy entity set: what the cutover must preserve

- **52 entities.** Every entity id is already `sensor.sherpa_<key>` or
  `binary_sensor.sherpa_<key>`.
  - 51 are in the registry.
  - `binary_sensor.sherpa_compressor_running` is not: the `threshold` platform
    takes no unique_id. It has history (1,550 records) but nothing to remove at
    cutover.
- **20 carry long-term statistics.** Their unit and state class must not change,
  or HA raises "unit changed" repairs and the statistics break.

  | Kind | Entities | Unit |
  |---|---|---|
  | sum (`total_increasing`) | compressor/pump/filter seconds | s |
  | sum (`total_increasing`) | compressor/pump hours | h |
  | mean (`measurement`) | water_in, water_out, dhw_tank, outdoor_air, water_delta | °C |
  | mean (`measurement`) | cooling/cooling_eco/heating/heating_eco/dhw setpoints, dhw_hysteresis, legionella_setpoint | °C |
  | mean (`measurement`) | pump_duty | % |
  | mean (`measurement`) | compressor_rate | s/min |
  | mean (`measurement`) | pump_step | **none**, keep it unitless |

- **Live definitions:**
  - The generated `packages/plant.yaml` loads first. It supplies 38 entities:
    the Modbus hub and the bit-decoding binary sensors, which carry `has_value`
    availability guards.
  - The hand-written `packages/sherpa.yaml` supplies the derived entities only:
    mode, error_code, pump_duty, hours, water_delta, legionella_start, power,
    error, warning, compressor_rate and compressor_running.
  - Its Modbus hub is rejected as a duplicate, which is why `identify_code` and
    `pump_step` have been unavailable since 2026-10-12.
- **Legacy vocabulary:**
  - `sensor.sherpa_mode` ∈ {`standby`, `cooling`, `heating`, `domestic hot water`,
    `anti-legionella`}.
  - `sensor.sherpa_error_code` is `none` or a comma-joined list such as `E07`.
  - `sensor.sherpa_legionella_start` is `HH:MM`.
- **Replay check.** The Python versions of the legacy templates in
  `tests/legacy.py` reproduce every recorded state of mode, error_code,
  mode_pending, mode_dhw, power, error, warning and defrost from the raw words:
  3,354 comparisons, 0 mismatches.

## Register behaviour seen in history

**Status (register 12).** Values seen: 0, 1, 6, 9, 96, 97, 98, 102.

| Value | Bits | Reading |
|---|---|---|
| 0 | – | standby |
| 1 | cooling | cooling selected; compressor usually idle (setpoint satisfied) |
| 6 | heating + DHW | DHW production: the circuit runs in heating to make hot water |
| 9 | cooling + legionella | legionella cycle; the cooling bit stays set and EH1 does the work |
| 96 | pending | pending with no mode |
| 97 / 98 / 102 | pending + 1 / 2 / 6 | the pending pattern on top of a mode; 97 is about as common as 1 |

**The status word does not tell you the compressor is running.**
`0 < status < 96` agrees with the legacy compressor-running sensor in only 47.6 %
of 30 s samples.

| Status | Running | Idle |
|---|---|---|
| 1 | 618 | 74,268 |
| 6 | 1,704 | 291 |
| 97 | 1,855 | 15,281 |
| 102 | 402 | 1,205 |

So the integration keeps the counter-derivative estimate. The history fixture
has 3,367 compressor-counter records and the legacy estimate's 1,550
transitions to test an improved estimator against.

**Override (register 102).**
- Only value 16 (bit 4) appeared, once, on 2026-08-22.
- With defrost known to be bit 5 (OR06 "UE defrosting cycle"), this supports
  **bit n = OR(n+1)**, so bit 4 = OR05 "UE capacity limitation".
- Defrost itself has not occurred yet (summer only).

**Alarms (registers 100/101).**
- Only E07 (register 100 = 64, "UE communication error") was seen: 11
  episodes, 2026-10-02 → 10-12.
- Every episode drove the alarm-relay output (105 = 256, alone). The relay
  never fired outside an E07 window.
- The inputs word read **0** five times. Four were within minutes of an E07
  episode but not inside one:
  - 10-06 17:46–17:57, around a one-minute E07
  - 10-08 08:55, in the minute between two episodes

  The fifth, 08-19 08:07, was not near any alarm. A 0 word decodes as every
  inverted input active at once (flow switch, TA and all contacts), which is
  implausible, so it looks like a glitch read rather than a real input state.

**Outputs (register 105).** Values seen: 0, 1, 3, 17, 21, 256.

| Value | Bits | When |
|---|---|---|
| 17 | pump + 3-way valve | DHW cycles: 37 of 45 occurrences with status 6, the other 8 during legionella (status 9) |
| 21 | pump + EH1 + 3-way valve | the four legionella cycles (EH1 + EH2 mode, ADDR229 = 2) |
| 3 | pump + DHW pump | 09-27 and 09-30, exactly 3 days apart |

No DHW pump is fitted. The 3-day spacing of value 3 matches ADDR250/251 periodic
DHW pump activation every 72 h, so the bit is driven even with no pump
connected. Keep `out_dhw_pump`, but disable it by default.

**Inputs (register 8).** 895 and 894 alternate. Only bit 0 (flow switch,
inverted) toggles, as expected.

**Pump step (register 388).** Always 1 (maximum speed) for 57 days.

**Legionella start (register 231).**
- Status 9 began at 22:00 UTC on 08-18, 08-19, 09-02 and 09-16. That is
  **01:00 Kyiv summer time**, exactly what register 231 = 60 says.
- The display photo of 2026-08-12 showed 02:00, but that predates every
  recorded cycle. The evidence now points to "minutes since local midnight".
  Confirm on the display after the DST change on 2026-10-25.
- The start drifted from 22:00 to 21:58 UTC over a month, which suggests the
  unit's clock drifts.

## Decisions this hands to P1

1. **Units and state classes:** use the 20 statistics entities' units and state
   classes verbatim, including a unitless `pump_step` with `measurement`.
2. **`sensor.sherpa_mode` becomes an enum sensor with translated states.**
   Decided 2026-10-13. Keys are snake_case throughout, HA's convention:
   `standby`, `cooling`, `heating`, `domestic_hot_water` and `anti_legionella`,
   with en and uk labels.
   - Two legacy values change: `domestic hot water` and `anti-legionella`.
   - The legacy-to-key mapping is `tests/legacy.py::MODE_KEYS`.
   - **Cutover (P3):** update the four dashboard lines that compare the old
     strings, then regenerate the plant dashboard:
     - platform `core/templates/plant_cards.yaml:660` and `:669`
     - the Pi's `dashboards/boiler.yaml:704` and `:713`
   - No automation or script uses these strings, and the entity has no long-term
     statistics. History from before the cutover keeps the old wording for those
     two states.
3. **Implausible inputs word:** treat a raw 0 in register 8 as a glitch, not as
   "all inputs active". Either hold the previous value or report unknown for
   that poll. The probe's sweep and watch can show how often it happens.
4. **Compressor running:** an estimator from the counter derivative, tested by
   replaying `history_uahs01.json` and compared with the legacy threshold
   sensor.
5. **Watch stage:** the probe's watch stage is not needed for these tests,
   because the recorder already has the series. Re-export in winter, before
   heating-season behaviour (defrost, heating with EH backup) matters.

## Publishing the history fixture

`history_uahs01.json` shows when this household's heat pump ran, made hot
water and went idle over 57 days. **Decided 2026-10-13: it stays in the
repository, including if the repository is made public.**
