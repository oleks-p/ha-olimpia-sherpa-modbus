# P6: mode control

Home Assistant sets the Sherpa's operating mode through register 106, opt-in,
and keeps the unit fed while it does. Facts: Olimpia's *RDE448, Modbus
communication* (not in this repository) and the test on the reference unit
(`docs/p6_mode_command_test.md`). Code: `mode_control.py`.

## Switching it on

1. *Allow writes* and *Mode control* in the options. Mode control without
   *Allow writes* is refused.
2. On the panel, set **ADDR220 = 1**. Only a person does this. The integration
   never writes ADDR220, or any register in `FORBIDDEN_WRITES`.

## States

The controller reports one of four states (climate attribute `mode_control`):

| State | When | What it does |
|---|---|---|
| `off` | the option is off | Nothing. If ADDR220 = 1, a repair issue says nothing keeps the unit fed |
| `inactive` | ADDR220 is 0, 2 or unknown | Watches the panel. Writes nothing |
| `active` | ADDR220 = 1 | Writes 106 every 60 s |
| `stalled` | ADDR220 = 1, no fresh read for 60 s | Keeps trying to write. Entities keep their last values |

## Register 106

| Bit | Value | Meaning |
|---|---|---|
| 0 | 1 | Standby (STB) |
| 1 | 2 | ECO |
| 2 | 4 | Cooling (CLG) |
| 3 | 8 | Heating (HTG) |
| 4 | 16 | Night |

Heating and cooling both clear is DHW only. Heating and cooling together are
never written. 106 is RAM, so there is no write limit on it.

**Standby is a flag beside the mode.** Setting it keeps the mode bit, ECO and
night. Leaving it restores them, and the ECO and night switches stay truthful
meanwhile. A word such as 9 (STB + HTG) has not been tried on the unit; it must
behave as standby (status 0, outputs 0). That is acceptance step 3.

| Control | Change |
|---|---|
| Select `standby` | set STB |
| Select `dhw_only` | clear STB, HTG, CLG |
| Select `heating`, `cooling` | clear STB, set that bit, clear the other |
| Climate OFF | clear HTG and CLG, keep STB, ECO, night |
| Climate HEAT, COOL | set that bit, clear the other, clear STB |
| Water heater off, on | set STB, clear STB |
| ECO, night switch | that bit |

## What the entities show

With ADDR220 = 1, 106 is the truth, read back from the unit. The status word
follows 106 except for heating: a DHW cycle sets the heating bit, so the status
word alone can't tell heating from a DHW cycle.

| 106 | Climate | `operating_mode` | `hvac_action` |
|---|---|---|---|
| STB set | OFF | `standby` | off |
| STB clear, HTG | HEAT | `heating` | from the status word and outputs |
| STB clear, CLG | COOL | `cooling` | same |
| STB clear, neither | OFF | `dhw_only` | idle |

- **OFF = standby or DHW only.** A climate has no DHW-only mode. The select is
  the exact control, and `operating_mode` says which one it is.
- **Water heater** `hot_water`: on is STB clear, off is STB set. Without mode
  control it shows on when the status word shows heating, cooling or a DHW
  cycle, and unknown when the status is 0 (standby and DHW only look alike).
  Its setpoint is the DHW setpoint (register 210) and is settable only once its
  write check has passed.
- The select, the switches and the water heater's on/off are unavailable unless
  the state is `active`. A call then fails with `mode_control_inactive`.

## Keep-alive

With ADDR220 = 1 the unit raises E09 255 s after the last write of 106 (RDE448;
measured 253.6 to 254.4 s), and again every 254 s. Each time the alarm relay closes and the pump stops for about
2.5 s, then the unit returns to its last command on its own. A read is no
keep-alive.

| What | Value |
|---|---|
| Controller tick | 10 s, its own timer (the poll stops on an outage, which is when this matters) |
| Write every | 60 s |
| E09 after | 255 s documented, 253.6–254.4 s measured |
| A gap counts as a miss over | 250 s (repair issue, `late_events`) |
| Writes that can fail in a row | three |
| Stall treated as normal | 10–30 s |
| Unavailable (entities) | 120 s (option) |

- A keep-alive write is **silent**: no event, no log entry, no entity update.
  A change is not: a user command, a hand-over, or a word the unit did not
  hold. It fires `olimpia_sherpa_modbus_parameter_written` and is listed in the
  diagnostics.
- **ADDR220 is read from the unit before every write**, inside the write
  lock, and nothing is written unless it reads 1. The cache can be old during a
  link stall, and a person may have set ADDR220 = 0 meanwhile. This holds for
  the keep-alive, user commands and the last write at unload. The bus itself
  refuses any register in `FORBIDDEN_WRITES` (ADDR220 above all).
- A write counts as sent when the unit acknowledges it, even if the read-back
  then fails (it is tried once more first): the unit got the word, so its E09
  clock restarted. A failed write is retried every tick.
- A user command is all or nothing: set, write, read back. If the write fails or
  the unit doesn't hold it, the previous mode is back and the call raises. The
  timer never retries something that was refused. A hand-over that arrived
  meanwhile is not undone.
- The write path is the write gate's lock and the bus's frame lock: one master.
- ADDR220 is read every 10 s for every entry, mode control or not.

## Hand-over

- While ADDR220 is 0 or 2, the controller records the panel's selection (off,
  heating or cooling, from the status word) and night, but only from a poll
  that follows another one at 0: this link has glitched reads, and a glitched 0
  would carry the status word of ADDR220 = 1, which follows 106, not the panel.
- When ADDR220 turns to 1 after at least two polls at 0, while Home Assistant
  is running, the desired mode is that snapshot, if it is under a minute old
  (otherwise the stored mode stands, or 106 as read if nothing is stored). A
  single poll at 0 between two at 1 is no hand-over. The mode is: heating or cooling, or standby if the panel was off; night as
  it was; ECO from the store (it can't be seen at ADDR220 = 0). It is written at
  once, stored, and announced.
- DHW only is never inferred: the status word reads 0 for it and for standby.
- The unit acts on a stale 106 for up to one poll (10 s) after the flip. 106 is
  RAM, so after a unit reboot that value is 0, DHW only, which is safe.

At setup:

| Situation | Winner |
|---|---|
| ADDR220 = 1, a stored mode | The stored mode, written at once. A differing 106 is logged once |
| ADDR220 = 1, nothing stored | 106 as read, stored. The first keep-alive follows within a tick |
| ADDR220 = 0 or 2 | Nothing written. The panel snapshot starts |
| ADDR220 unknown | Wait |

The desired mode is in a Home Assistant `Store`, not in an entity: three
entities share it, and the keep-alive needs it before any entity exists. It
holds the mode, standby, ECO and night, and is forgotten when the entry is
removed.

## Unload and stop

- Unloading the entry (an options change reloads it) first lets a write in
  flight finish, refuses new commands, then writes once more, so the unit starts
  the restart with a full 255 s. It does not write standby. Nothing writes after
  it returns, so the next controller (a reload) has the bus alone.
- Home Assistant stopping does the same.
- If setup fails after the controller started, it is stopped too.
- A restart of 1–2 minutes never reaches 255 s. The first tick after setup
  writes at once.

## Repair issues

None is fixable from Home Assistant. Each is cleared when the cause is.

| Issue | Raised when | Do |
|---|---|---|
| `serial_control_unmanaged` | ADDR220 = 1 for over 60 s and mode control (or *Allow writes*) is off | Set ADDR220 = 0 on the panel, or turn on mode control |
| `mode_keepalive_lost` | ADDR220 = 1, controller on, no write sent for over 250 s | Check the link. If it lasts, set ADDR220 = 0 |
| `mode_not_applied` | The unit reads back something else than written, three writes in a row | Check for another master. If it lasts, set ADDR220 = 0 |

E09 is never detected from register 100: the bit is up for under 1.6 s and the
poll runs every 10 s.

## How to hand control back

Set **ADDR220 = 0** on the panel. The panel is in charge at once. Home Assistant
stops writing, the controls go unavailable, and the climate is read-only again.
Do it before a long absence, or whenever the link is down for more than a few
minutes.

## Open: E09 and a running compressor

On the reference unit the compressor was idle at both E09 moments, so whether
E09 stops a running compressor (and makes it wait out its restart delay) is not
known. Two ways to find out:

- **Passive.** Each write that ends a gap over 250 s is recorded in the
  diagnostics (`mode_control.late_events`): the status, outputs and compressor
  counter before and after. A log warning says E09 happened.
- **Active.** `tools/mode_command_test.py watchdog --need-compressor` (see
  `docs/p6_mode_command_test.md`). Run it before relying on mode control in
  winter.

## The research action

`write_mode_command` and `tools/mode_command_test.py` stay as the evidence
trail. The action is refused while the controller is `active` or `stalled`: two
writers of one register fight. Turn mode control off first to run the test.
