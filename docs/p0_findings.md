# P0 findings: the reference unit's register map

Evidence from the register probe of 2026-10-13 on the reference unit: SHERPA S2
BIG + SHERPA S2 14T, firmware 0.57. A full run at 09:09 UTC, then a rules-only
run at 09:22 UTC. The merged, sanitized capture is
`tests/fixtures/sherpa_s2_big_14t_fw057.json`.

## Register probe (2026-10-13)

**Identity:**
- firmware 197/198 = 57/57 ("0.57"), identify code 199 = 1134
- IDU model 370 = 2 (SHERPA S2 BIG), ODU model 371 = 14 (SHERPA S2 14T)
- Modbus address 247 = 201, protocol 401 = RTU
- remote controls 220 = 0, DHW source 228 = 2, legionella mode 229 = 2

**The link is clean and fast:**
- 1,046 requests: 0 timeouts, 0 CRC errors, 0 stalls, no echo
- latency p50 35.9 ms, p95 36.0 ms, max 51.9 ms (60 ms frame gap)
- the 0–999 sweep took 96 s
- stalls of 10–30 s are known on such links; none occurred in this run

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
- **Every answering run reads whole in one request.** The rules-only run used
  `--sweep-from`, with 32 s of downtime:
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

**Undocumented registers that answer (76):**

| Registers | Value then | Note |
|---|---|---|
| 9, 99, 106 | 0 | 106 is the mode command (P6, Olimpia RDE448) |
| 193 / 194 / 195 | 991 / 0 / 0 | 193 bit 8 follows the circulation pump (P5) |
| 218 | 1 | |
| 263–269 | 10, 2, 0, 20, 5, 10, 150 | |
| 290 | 0 | |
| 300–318 | 0 | the cascade capacity and hour counters for heat pumps 4–6 |
| 327–333 | 5 ×6, 1 | |
| 337–340 | 25, 50, 70, 100 | |
| 402–408 | 0, 0, 0, 100, 0, 5, 0 | |
| 500–507 | 0 | |
| 900, 999 | 0 | |
| 910–914 | 45693, 0, 249, 59169, 13476 | |
| 951–955 | 33692, 0, 0, 33692, 0 | |
| 961–965 | 0 | |

**201–205 do not exist.**

**Absent probes:** registers 4–7 read −1, −501, −501, −1. These are T5–T8
(T8 solar = −0.1 °C on the display, T6/T7 = −50.1 °C): the sentinels for a
probe that is not fitted.

**Curve tables:** 561–592 run 24 → 78 and 593–624 run 24 → 92, both flat-topped.

## What the state words mean

**Status (register 12):**

| Value | Bits | Reading |
|---|---|---|
| 0 | – | standby |
| 1 | cooling | cooling selected; the compressor is often idle (setpoint satisfied) |
| 6 | heating + DHW | DHW production: the circuit runs in heating to make hot water |
| 9 | cooling + legionella | legionella cycle; the cooling bit stays set and EH1 does the work |
| 96 | pending | pending with no mode |
| 97 / 98 / 102 | pending + 1 / 2 / 6 | the pending pattern on top of a mode |

**The status word does not tell you the compressor is running.** In recorded
history, `0 < status < 96` agreed with the compressor running in under half of
the samples, so the integration estimates it from the runtime counter's rate.

**Override (register 102):**
- Defrost is bit 5 (OR06 "UE defrosting cycle").
- Bit 4 appeared alone, consistent with OR05 "UE capacity limitation".
- That supports **bit n = OR(n+1)**.

**Alarms (registers 100/101):**
- E07 ("UE communication error") is register 100 = 64, bit 6. That supports
  **bit n = E(n+1)**.
- An alarm drives the alarm-relay output (105 = 256).
- The inputs word sometimes reads **0**, near E07 episodes. A 0 word decodes as
  every inverted input active at once (flow switch, TA and all contacts), which
  is implausible, so it is taken as a glitch read, not a real input state.

**Outputs (register 105):**

| Value | Bits | When |
|---|---|---|
| 17 | pump + 3-way valve | DHW cycles, and legionella |
| 21 | pump + EH1 + 3-way valve | legionella cycles with EH1 + EH2 (ADDR229 = 2) |
| 3 | pump + DHW pump | the periodic DHW pump activation (ADDR250/251, every 72 h) |

The DHW pump bit is driven on schedule even with no DHW pump connected, so
`out_dhw_pump` is disabled by default.

**Inputs (register 8):** only bit 0 (flow switch, inverted) toggles in normal
running.

**Legionella start (register 231)** is minutes after local midnight: the
display shows 01:00 while 231 reads 60.

## Decisions taken from it

1. **Units and state classes** stay those of a YAML modbus setup with the same
   names, including a unitless `pump_step` with `measurement`, so history and
   long-term statistics carry over.
2. **`sensor.sherpa_mode` is an enum sensor with translated states.** Keys are
   snake_case, HA's convention: `standby`, `cooling`, `heating`,
   `domestic_hot_water` and `anti_legionella`, with en and uk labels. The YAML
   templates' `domestic hot water` and `anti-legionella` change wording.
3. **Implausible inputs word:** a raw 0 in register 8 is a glitch, not "all
   inputs active". The decoded inputs hold their previous value.
4. **Compressor running:** estimated from the runtime counter's derivative.
