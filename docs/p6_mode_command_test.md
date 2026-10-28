# P6: testing the mode command (register 106)

**Question.** Can Home Assistant set the operating mode through register 106,
and what happens when it stops writing?

**Source.** Olimpia's *RDE448, Modbus communication, Sherpa S2 Aquadue heat
pumps* (rev. 0, 2022-09-29), received 2026-10-28. It is Olimpia's property and
is not in this repository. What it says, and what the test relies on:

- Register 106, "working mode setting", is R/W. Bit 0 standby, bit 1 ECO, bit 2
  cooling, bit 3 heating, bit 4 night/silent. Heating and cooling both clear
  means DHW only.
  - Values used here: 1 standby, 8 heating, 10 heating + ECO, 24 heating +
    night, 4 cooling, 0 DHW only.
- With the unit set to take commands over RS-485 (ADDR220 = 1), **E09 follows
  if nothing is written for 255 s**. "To prevent alarm 09, periodically write
  ADDR106."
- Addresses from 200 up are EEPROM, with a limited number of writes. 106 is
  below that: rewriting it costs nothing.

This fits P5 (`docs/p5_mode_research.md`): 106 read 0 in every snapshot. With
ADDR220 = 1, 0 means DHW only, which is why the status stayed 0 and the
compressor stayed off when 220 was set to 1 with heating selected.

## What the test answers

1. With ADDR220 = 0, does the unit ignore 106? If it does, the panel stays in
   charge as long as 220 = 0.
2. With ADDR220 = 1, does the status word follow 106 for standby, heating,
   heating + ECO, heating + night and DHW only? ECO cannot be seen over Modbus,
   so the panel has to say whether ECO is on.
3. How long after the last write does E09 come, and what does the unit do in
   E09? Does heating stop, and does the tank still heat?
4. Does the next write clear E09, or does it need the panel?

Answer 3 decides the most. If E09 stops the heating, every Home Assistant outage
longer than about 4 minutes stops it too.

## What it uses

- **`olimpia_sherpa_modbus.write_mode_command`**, an admin action. It writes 106
  (FC6), then reads back 106, the status word, outputs, alarms, inputs and
  ADDR220, and returns them.
  - It needs *Allow writes*.
  - It refuses heating and cooling together, and any bit above 4.
  - It writes even when 106 already holds the value, because the rewrite is the
    keep-alive. The EEPROM rate limits don't apply.
  - It never writes anything but 106. ADDR220 stays forbidden: only a person
    changes it, on the panel.
  - Every write fires `olimpia_sherpa_modbus_parameter_written` (key
    `mode_command`) and is listed in the diagnostics.
- **`tools/mode_command_test.py`** runs the steps below through that action and
  `read_registers`. There is one master on the wire, and Home Assistant keeps
  running. Each step samples the unit every 5 s (0.5 s in the watchdog's
  silence), prints what it sees and saves everything to
  `research/mode_command/NN-<step>.json`. A refused step leaves a record too.

## Before the day

1. Install a build with the *Write mode command* action (0.6.0 or later)
   through HACS, or copy `custom_components/olimpia_sherpa_modbus` into Home
   Assistant's `config/custom_components/`, then restart Home Assistant.

2. Check that *Allow writes* is on (*Settings → Devices & services → Sherpa →
   Configure*). Check that *Write mode command* is listed in *Developer tools →
   Actions*.
3. Run `status` once. It only reads. It should show identify 1134, ADDR220 = 0
   and 106 = 0.

## On the day

You need:
- one person at the panel, who can open the SERVICE screen to change ADDR220 and
  select modes;
- one person at the laptop, or a phone line between the two;
- about 30 minutes;
- a time when heating can be off for a few minutes, with a warm tank.

Tell anyone at home that an alarm will show on purpose. The alarm relay (output
bit 8) closed with every E07 so far, so if anything is wired to it, it will
fire.

```bash
T="--ha http://homeassistant.local:8123 --token-file ~/.ha-token"
python3 tools/mode_command_test.py $T status
```

| # | At the panel | At the laptop | Takes |
|---|---|---|---|
| 0 | Note the selected mode, ECO and night, to restore later. Select **standby** | `status` | 1 min |
| 1 | Nothing: ADDR220 stays 0, standby stays | `panel` | 1.5 min |
| 2 | Set **ADDR220 = 1**. Watch the display at each value; note whether ECO and night show | `serial` | 5.5 min |
| 3 | Watch for **E09**: note the clock time it shows and how long, and whether the pump and compressor stop | `watchdog` | 11–30 min |
| 4 | Set **ADDR220 = 0**. Select the mode noted in step 0. Clear E09 if it's still shown | `restore` | 1 min |

- **Step 1** writes 8 (heating), watches 60 s and puts 106 back. It refuses
  unless ADDR220 reads 0 and the panel is on standby, so a change would show.
- **Step 2** writes 1, 8, 10, 24 and 0, each for 60 s, and rewrites the value
  every 60 s within a hold. It refuses unless ADDR220 reads 1.
  - `--hold 120` gives the compressor more time to start.
  - Cooling is left out. Add it with `--cooling` only when cooling water is
    safe for the installation, not in the heating season.
- **Step 3** writes 8, then waits, still writing every 60 s, until the unit
  heats without a DHW cycle. A DHW cycle sets the heating bit and would hide
  what E09 does to heating. The wait is up to 20 min (`--settle`).
  - Then it writes nothing for 600 s, two 255 s periods, sampling every 0.5 s.
    It records each E09 episode and every change of status, outputs or 106.
  - Then it writes 8 again. If E09 is still up, it times how long it takes to
    clear.
  - Start it right after step 2. Any delay is covered: it writes first.
- **Step 4** refuses until ADDR220 reads 0 again, then writes back the value
  that `status` found (0).
  - Do it promptly after step 3: from then on nothing writes 106, and E09
    returns within 255 s while 220 = 1.

**To stop at any point:**
1. Press Ctrl-C. `panel` puts 106 back; `serial` and `watchdog` write standby.
2. Set ADDR220 = 0 on the panel.
3. Run `restore`.

If Home Assistant or the laptop is unreachable, setting ADDR220 = 0 alone is
enough: the panel is in charge again (if step 1 found the unit ignores 106).

## Results

Unit: SHERPA S2 BIG + SHERPA S2 14T, identify code 1134, firmware 0.57.
Integration 0.5.1 plus this build. Run on 2026-10-28, 08:54–09:13 UTC, with
records `research/mode_command/00`–`13`.

| Question | Result | Record |
|---|---|---|
| 106 with ADDR220 = 0 | **Ignored.** 106 took 8 and held it for 60 s, but the status stayed 0 (standby on the panel). 106 was put back to 0 | `06-panel` |
| 1 standby | **Followed** within 5 s. The DHW cycle that was running stopped: status 102 → 0, outputs 17 → 0 | `10-serial` |
| 8 heating | **Taken**, but hidden at first. A DHW cycle started at once (status 6/102, pump + 3-way valve). Space heating showed when that cycle ended at 09:12:19 (status 2, then 98; pump only) | `10-serial`, `11-watchdog` |
| 10 heating + ECO | Nothing on Modbus (status 6), as expected: ECO is not visible there. Panel: not noted | `10-serial` |
| 24 heating + night | **Followed** at once: status bit 7 (6 → 134) | `10-serial` |
| 0 DHW only | **Consistent**: the DHW cycle carried on (status 6) | `10-serial` |
| E09 after the last write | **Shown on the panel for about a second, then cleared by itself.** Register 100 never showed it: the step sampled every 10.5 s | `11-watchdog` |
| The unit in E09 | No change in 431 s without a write: status 6, pump + 3-way valve, 106 = 8 throughout. A DHW cycle ran the whole time, so what E09 does to **space heating is still open** | `11-watchdog` |
| E09 clears on the next write | Not needed: it cleared by itself | panel |
| Back to the panel | ADDR220 = 0, then 106 = 0 at 09:13:33. The panel's mode was reselected by hand | `13-restore` |

Notes:
- **Standby stops DHW too.** "Off" in Home Assistant should therefore be DHW
  only (106 = 0), with standby as a separate choice. The unit was also seen
  making hot water on 106 = 0 alone (`07`–`09`, status 102).
- **106 keeps a value written while ADDR220 = 0.** When 220 is switched to 1,
  the unit acts on whatever 106 holds, so the integration has to write it first.
- The first version of the step had a bug: `cleared_after_write_s` (61.6) in
  `11-watchdog.json` was taken when its 60 s watch ended, not when E09 cleared.
  E09 was never seen in that record, so the value means nothing. Fixed.
- `06-panel` was stopped with Ctrl-C 13 s into its last watch, after 106 was
  already back to 0. The stop wrote 0 once more. Its verdict was not saved; the
  samples above are the result.

### What E09 does to heating (watchdog, second run)

Run on 2026-10-28 with the reworked step, recorded in `16-watchdog`.
- The step wrote 8 at 09:28:22 UTC and the unit was heating
  by its next sample, 30 s later, with no DHW cycle. The step wrote 8 again at
  09:28:53.
- Then came 600 s without a write, sampled every 0.5 s (about every 0.8 s in
  practice).
- The DHW setpoint had been lowered on the panel beforehand, so no DHW cycle
  could start. On the panel, not over Modbus, so the timing is unaffected.

| Question | Result |
|---|---|
| E09 episodes, s after the last write | **253.6 to 254.4, and 509.4 to 510.2.** E09 comes every 255 s for as long as nothing is written. Each time the bit was up for under 1.6 s: it was not up at the samples just before and after |
| The unit through E09 | **About 2.5 s off, then back on its own, on the last command.** The alarm relay closed and the pump stopped (outputs 1 → 256). The status dropped to 0 (standby) for one sample. Then status 98 (heating + pending) and the pump came back, with 106 = 8 throughout. The same happened both times |
| E09 clears on the next write | Not needed: it clears itself within about a second |
| Home Assistant's own sensors | `sensor.sherpa_error_code` stayed `none`: the 10 s poll misses an E09 this short |
| Compressor at the time | **Not running.** The runtime counter rose only from 11:29 to 11:30 (62 s), then stood still past 11:45. So whether E09 stops a running compressor, and makes it wait out its restart delay, is still open |

From 557.9 s the status went to 96, then 0, with the pump off: ADDR220 had been
set back to 0 on the panel, with the panel on standby. The final write (8, at
633 s) went to a unit with 220 = 0, so 106 was left holding 8 until `restore`.

## Built as

Mode control, `docs/p6_mode_control.md`. It follows from these results:

- The unit follows 106 only with ADDR220 = 1 and holds a value written at 220 =
  0, so nothing is written at 220 = 0 and the first write after a hand-over is
  immediate.
- E09 does not stop the heating (seen with the compressor idle), but it pulses
  the alarm relay and stops the pump for about 2.5 s every 255 s. So 106 is
  written every 60 s, and a repair issue appears when it has not been written
  for over 255 s.
- Standby stops hot water too. So standby is a flag of its own (the select, the
  water heater's off), and climate OFF is heating and cooling both off, which
  leaves hot water running.
- The test action stays, and is refused while mode control is active.

## Compressor during E09

The one question left open. Run it when space heating really runs:

```bash
python3 tools/mode_command_test.py $T watchdog --need-compressor
```

- It writes 8, waits (writing every 60 s) for the unit to heat without a DHW
  cycle, and then requires the compressor's runtime counter (registers
  270–271) to rise across two samples 10 s apart, immediately before the
  final write, within `--compressor-window` (180 s). A compressor that rose
  earlier and has stopped does not count. If it doesn't rise, the tool writes
  standby and stops, with no silence started. The two samples are saved as
  `compressor_confirmed`.
- Then 600 s without a write, as before, with the counter sampled every 0.5 s.
  The record has `compressor_through_e09` per episode and
  `compressor_kept_rising`. "Rising" means the counter gained at least half a
  second per second from just before the episode to 15 s after it.
- **Warning.** If E09 stops a running compressor, it may wait out its restart
  delay, twice in 600 s. Do it when a few minutes of heating are not needed.
- Turn mode control off in the options first: the test action is refused while
  it runs.

Result: not run yet. Add it here, with the record number in
`research/mode_command/`.
