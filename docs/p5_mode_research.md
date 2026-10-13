# P5: where the operating mode lives

**Question.** Can Home Assistant see, and set, the operating mode (standby,
heating, cooling, ECO, night, DHW) over Modbus?

**Method.** 2026-10-13, 16:55-17:12 EEST, on the reference unit (SHERPA S2 BIG
+ SHERPA S2 14T, identify code 1134, firmware 0.57, uahs01). Integration 0.3.0.

- A person at the panel changed one thing at a time in the modes menu and
  confirmed it.
- After each change, `tools/mode_research.py` took a snapshot of all 284
  answering registers through the integration's `read_registers` action. Home
  Assistant kept running, with one master on the bus, and nothing was written.
- Two baseline snapshots 15 s apart marked 910, 913, 951 and 954 as noise.
- The raw snapshots are in `research/modes/`.

## What each change did

| Panel change | Registers that followed it |
|---|---|
| Standby → heating | status 12: 0 → 102 (heating, DHW request, compressor pending). Outputs 105 → 17 (pump, 3-way valve). Flow switch closed |
| ECO on / ECO off | **none**, at once or 30 s later |
| DHW setpoint 50 → 20 on the panel | 210: 500 → 200 at once. The unit left DHW for heating: status 6 → 98, the 3-way valve dropped (energised = DHW tank, here) |
| Night on / night off | status bit 7, only (98 ↔ 226) |
| DHW disabled / enabled | **none**, at once or 30 s later |
| Heating → cooling | status bit 1 → bit 0 (98 → 97); the compressor was still pending |
| → standby | status 0, outputs 0 once the pump overrun ended |
| ADDR220 0 → 1, heating selected | 220 reads 1. The status stays **0**: the panel's selection no longer drives the unit, and the compressor stays off. No register appears (below) |
| ADDR220 → 0, standby, DHW 50 | back to the baseline in every register except temperatures and counters |

Register 193 changed too (991 ↔ 735, bit 8 only), but it follows the
**circulation pump**: bit 8 clears when the pump runs, including during the
pump's overrun after standby is selected. It is not a mode register.

All 186 refused addresses near the answering ones were read one at a time:
10-11, 103-104, 196, 201-205, 214-216, 282-284, 286-289, 335-336, 342,
373-379, 389-400, 409-499 and 508-560. **All were refused with ADDR220 = 0 and
with ADDR220 = 1.** The SiOS Control command interface is not readable.

## Findings

1. **The selected mode can be seen, from the status word alone.** Bit 1 means
   heating selected and bit 0 cooling selected, including while the compressor
   is idle or pending. Status 0 means standby. Night is bit 7. DHW production is
   bit 2.
2. **ECO and "DHW disabled" cannot be seen.** No readable register follows
   them.
3. **No command register was found by reading.**
   - The manual (EN p.38): serial control is "only possible through SIOS
     CONTROL domotic", and needs ADDR220 = 1, which disables the panel's mode
     and timer.
   - With 220 = 1 nothing new answers. The commands are write-only, use another
     function code, or are SiOS's own; the Olimpia documentation available here
     does not say which.
   - Writing to unknown addresses to find out is not something to do blind.
4. **A documented control path exists without serial control.**
   - The free-contact inputs for **TA, ECO, Night and DHW are "always enabled"**
     (manual, ADDR220 note), even with ADDR220 = 0.
   - With heating or cooling selected on the panel, an open TA contact leaves
     only DHW running, so TA works as an on/off for heating and cooling.
   - TA is already observable: input word bit 7, `binary_sensor.sherpa_in_ta`.
   - Changing between heating and cooling by contact needs ADDR220 = 2.

## Consequences for P6

- A `climate` entity can **show** the operating mode, from the status word
  (standby, heating, cooling) with night as an attribute.
- It can **set** the mode only through a relay on the TA input, with the
  heat/cool choice left on the panel. Without that, it stays read-only.
- Serial mode control waits for Olimpia's SiOS Control Modbus map, and for a
  decision whether giving up the panel's mode and timer controls (ADDR220 = 1)
  is acceptable for a customer.
- ADDR220 stays forbidden to the integration.
