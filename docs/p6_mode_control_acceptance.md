# P6 acceptance: mode control on the unit

The tests run mode control against a simulated unit. This runbook checks the
same behaviour on the real one, and the three things the simulator cannot
answer:
- what E09 does to a **running compressor**;
- whether a standby word with other bits set, such as **9 (standby + heating)**,
  behaves as standby;
- whether **cooling** follows 106 like heating.

How mode control works: `docs/p6_mode_control.md`. How the unit answered the
mode command before mode control existed: `docs/p6_mode_command_test.md`.

## Before the day

1. Install 0.6.0 or later through HACS, and restart Home Assistant.
2. Turn on *Allow writes*. Leave *Mode control* **off** for now: step A uses the
   research action, which is refused while mode control is active.
3. Optional: pass the write check for `dhw_setpoint`, so the water heater's
   setpoint can be set (*Developer tools → Actions → Verify write*).
4. Make a long-lived admin token and save it, e.g. to `~/.ha-token`, for the
   test tool.

## On the day

You need:
- one person at the panel, who can change ADDR220 on the SERVICE screen and
  select modes;
- one person at Home Assistant, or a phone line between the two;
- about 1.5 hours;
- a cold enough day for the compressor to run for space heating (step A);
- a time when heating may stop for a few minutes.

Tell anyone at home that alarms will show on purpose. In steps A and F the unit
raises E09: the alarm relay closes and the pump stops for about 2.5 s each time.

### How to look

| What | Where |
|---|---|
| 106, status, outputs, alarms, ADDR220, read from the unit | `python3 tools/mode_command_test.py $T status` (read-only) |
| Controller state, desired word, writes, gaps, issues | *Settings → Devices & services → Sherpa → ⋮ → Download diagnostics*, section `mode_control` |
| What the entities say | `climate.sherpa_heat_pump` (attributes `operating_mode`, `mode_control`), `select.sherpa_operating_mode`, `switch.sherpa_eco`, `switch.sherpa_night`, `water_heater.sherpa_hot_water` |
| Repair issues | *Settings → System → Repairs* |
| What the unit does | the panel display |

```bash
T="--ha http://homeassistant.local:8123 --token-file ~/.ha-token"
```

The words in register 106: 1 standby, 2 ECO, 4 cooling, 8 heating, 16 night,
added up. 0 is DHW only.

## Steps

### A. E09 with the compressor running (mode control off)

1. On the panel: select heating, then set **ADDR220 = 1**.
2. Run:

   ```bash
   python3 tools/mode_command_test.py $T watchdog --need-compressor
   ```

   - It writes heating and waits, still writing, for heating without a DHW
     cycle.
   - It then waits up to 180 s for the compressor's runtime counter to rise
     across two samples. If it doesn't, it writes standby and stops: try again
     on a colder day or with a higher water target.
   - Then come 600 s without a write, sampled every 0.5 s.
3. At the panel, note each E09 and whether the compressor stops.
4. Expected:
   - E09 at about 254 s and 508 s after the last write.
   - `serial_control_unmanaged` in Repairs after about 60 s. That is right:
     ADDR220 is 1 and mode control is off.
5. When it ends, set **ADDR220 = 0** on the panel within a few minutes. The
   repair issue clears.
6. Run `restore`.
7. Record from `*-watchdog.json`: `compressor_through_e09`,
   `compressor_kept_rising`, and the E09 times.

### B. Mode control on, panel in charge

1. Turn on *Mode control* (*Configure*). The entry reloads.
2. Wait 2 minutes with ADDR220 = 0.
3. Expected:
   - `mode_control` is `inactive`;
   - the select, the ECO and night switches, and the water heater's on/off are
     unavailable, and the climate is read-only;
   - in diagnostics, `writes_total` is 0, and `status` shows 106 unchanged;
   - no repair issue.

### C. Hand-over

1. On the panel: select **heating** with **night** on. Wait at least 30 s.
2. Set **ADDR220 = 1**.
3. Expected within about 20 s:
   - `mode_control` is `active`, and the controls become available;
   - `status` shows 106 = 24 (heating + night; ECO comes from the store, off on
     first use);
   - the unit carries on as the panel had it;
   - the log has "ADDR220 is now 1: taking over the panel's mode".
4. Leave it running at least 10 minutes. Expected: no E09, `max_gap_s` under
   70, `late_events` empty.

### D. Every control

One change at a time. After each, wait a minute, then check `status`, the
entities and the panel. Start from heating, ECO off, night off (106 = 8).

| # | Do | 106 | The unit |
|---|---|---|---|
| 1 | ECO on | 10 | panel shows ECO |
| 2 | ECO off | 8 | |
| 3 | Night on | 24 | status bit 7 |
| 4 | Night off | 8 | |
| 5 | Climate OFF | 0 | DHW only: status 0, or a DHW cycle (6, 102) |
| 6 | Climate HEAT | 8 | heating (status bit 1) |
| 7 | Select DHW only | 0 | as 5 |
| 8 | Select heating | 8 | as 6 |
| 9 | **Water heater off** | **9** | **standby: status 0, outputs 0 after the pump's overrun.** Never tried before |
| 10 | Water heater on | 8 | heating again |
| 11 | ECO on, night on | 26 | |
| 12 | **Water heater off** | **27** | **standby, as 9** |
| 13 | Water heater on | 26 | heating, ECO, night |
| 14 | ECO off, night off | 8 | |
| 15 | Select standby | 9 | as 9 |
| 16 | Select heating | 8 | as 6 |

Each change fires `olimpia_sherpa_modbus_parameter_written` with key
`mode_command` and is listed in diagnostics. Keep-alive writes are not.

If row 9 or 12 does **not** give standby, stop: set ADDR220 = 0 on the panel and
record what the unit did. The standby word then needs a change in
`mode_control.py`.

### E. Reload and restart at ADDR220 = 1

1. Change an option and change it back (e.g. *Unavailable after* 120 → 121 →
   120). Each change reloads the entry.
2. Restart Home Assistant (*Settings → System → Restart*).
3. Expected after each:
   - no E09 on the panel;
   - the mode unchanged, written again at the new controller's first tick.

   The panel is the only judge here. A reload or restart starts a new
   controller, whose diagnostics count from zero and know nothing of the gap.
4. Note how long the restart took. A restart takes the unit's 255 s budget from
   the last write before the stop.

### F. Link stall and outage

Interrupt the link: unplug the USB adapter, or the gateway's network cable.

1. **90 s**, then reconnect. Expected:
   - no E09;
   - no repair issue;
   - the entities stay available (the default *Unavailable after* is 120 s).
2. **5 minutes**, then reconnect. Expected:
   - E09 on the panel about 254 s after the last write, with the alarm relay
     and the pump stopping for about 2.5 s;
   - the unit then carries on with the last mode;
   - entities unavailable after 120 s;
   - `mode_keepalive_lost` in Repairs after about 250 s.
3. After reconnecting, expected:
   - the repair issue clears at the next write;
   - `late_events` has one entry with `gap_s` about 300, the status and
     outputs before and after, and the compressor counter before and after.

   Note what the unit did.

### G. Hand-back

1. With mode control on, set **ADDR220 = 0** on the panel.
2. Expected within about 10 s:
   - `inactive`;
   - the controls are unavailable;
   - the panel's selection drives the unit;
   - `writes_total` stops growing.
3. Watch 5 minutes: nothing is written, and no E09.

### H. Option off at ADDR220 = 1

1. Set **ADDR220 = 1** again (a hand-over, as in C).
2. Turn *Mode control* off.
3. Expected: `serial_control_unmanaged` in Repairs after about 60 s.
4. Set **ADDR220 = 0** within 3 minutes, before E09 comes. The issue clears.

### I. Cooling (only in a safe season)

Not in the heating season: cold water in a floor or radiator circuit can
condense.

1. With mode control on and ADDR220 = 1, select **cooling**.
2. Expected: 106 = 4, status bit 0, the panel shows cooling.
3. Note the water temperatures for 10 minutes. Then select the mode you want.

### Afterwards

- Leave ADDR220 and *Mode control* as you want them to run: 1 and on for Home
  Assistant in charge, 0 for the panel.
- Download the diagnostics and keep the `mode_control` section with the
  results.

## Results

Fill in on the day. Times in UTC, and no site details: the repository is
public.

Unit: SHERPA S2 BIG + SHERPA S2 14T, identify code 1134, firmware 0.57.
Integration version: …

| Step | Expected | Seen | OK |
|---|---|---|---|
| A | E09 at about 254 s and 508 s; the compressor kept running, or stopped and restarted (say which) | | |
| A | `serial_control_unmanaged` while the option was off, cleared at ADDR220 = 0 | | |
| B | `inactive`, controls unavailable, nothing written, no issue | | |
| C | 106 = 24 within 20 s, unit unchanged, no E09 in 10 min | | |
| D 1–8 | each word as in the table, the unit following | | |
| D 9, 12, 15 | words 9 and 27 behave as standby | | |
| D 10, 13 | leaving standby restores the mode, ECO and night | | |
| E | reload and restart without E09, mode unchanged | | |
| F 1 | 90 s stall: nothing | | |
| F 2 | 5 min outage: E09 pulses, unit carries on, issue raised and cleared, one late event | | |
| G | hand-back: `inactive`, nothing written | | |
| H | unmanaged issue after 60 s, cleared at ADDR220 = 0 | | |
| I | cooling: 106 = 4, status bit 0 | | |

## What follows from it

- **The compressor stopped at each E09:** a long Home Assistant outage at
  ADDR220 = 1 restarts it about every 4 minutes. Note this in
  `docs/p6_mode_control.md`, and tell users to set ADDR220 = 0 when Home
  Assistant will be down for long.
- **Word 9 or 27 is not standby:** standby must clear the other bits. Change
  `Desired.word` and its tests, then repeat D.
- **Cooling does not follow:** hide cooling until it does.
