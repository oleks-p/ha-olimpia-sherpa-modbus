# Probe runbook: capturing a Sherpa on the Raspberry Pi

`tools/probe_sherpa.py` reads the heat pump's holding registers over RS-485 and
writes a JSON capture. The capture becomes the integration's test fixture, so
the block planner and decoders are built on how this unit really behaves.

The probe is **read-only by construction**. It can only send function codes 3
and 4, and anything else raises before a byte is sent. It changes nothing on the
unit.

## Why Home Assistant must be stopped

RS-485 allows **one master**. Home Assistant polls the Sherpa every 10 s. If the
probe talks at the same time, the frames collide and the unit raises **E09**. The
probe protects against this in three ways:

1. On a serial link it refuses to start without `--i-stopped-home-assistant`.
2. It refuses while anything answers on `127.0.0.1:8123`. HA uses host
   networking on the Pi, so a running HA always answers there.
3. It listens for 15 s before sending anything, and aborts if it hears a single
   byte. HA's 10 s poll always falls inside that window.

The port is also opened in exclusive mode (`TIOCEXCL`). That stops non-root
processes, but **not** the HA container, which runs as root. Treat it as a
backstop, not the guard.

While HA is stopped the heat pump keeps running on its own controller. What
pauses: dashboards, lighting automations, Futura control from HA. Mosquitto
keeps running.

## How long it takes

| Stage | Time |
|---|---|
| Listen guard | 15 s |
| Identity (10 registers) | ~1 s |
| Sweep 0–999, one register per read | 96 s at uahs01 (36 ms per read; undefined addresses answer with an exception at once) |
| Device rules (whole-run reads, count ladder, gaps, u32 halves, FC4) | a few seconds |
| Watch (optional, `--watch-minutes N`) | N minutes; HA stays down the whole time |

The default run at uahs01 took HA down for **2 min 26 s**, from stop to healthy.
A rules-only re-run with `--sweep-from` took **32 s**.

## Steps

Use the wrapper. It stops HA, runs the probe, and **always** starts HA again,
however the probe ends:
- the compose file is named explicitly, and success is judged by container
  state, not by exit code;
- the run is capped at 20 minutes;
- it is detached, so a dropped ssh session cannot leave HA down.

From the repo on the Mac:

```bash
scp tools/probe_sherpa.py tools/pi_probe_run.sh user@192.168.30.141:~/
ssh user@192.168.30.141 'setsid nohup bash ~/pi_probe_run.sh > ~/probe_run.log 2>&1 < /dev/null &'
ssh user@192.168.30.141 'tail -f ~/probe_run.log'   # ends with "homeassistant running"
```

Arguments after `pi_probe_run.sh` go to the probe. For example, to re-run only
the block-read rules against an earlier sweep (about 20 s of downtime):

```bash
ssh user@192.168.30.141 'setsid nohup bash ~/pi_probe_run.sh --stages rules \
  --sweep-from ~/sherpa_observed_<timestamp>.json > ~/probe_run.log 2>&1 < /dev/null &'
```

By hand instead, always name the compose file:

```bash
sudo docker compose -f ~/homeassistant/docker-compose.yml stop homeassistant
python3 ~/probe_sherpa.py --serial /dev/serial/by-id/usb-FTDI_...-port0 \
  --i-stopped-home-assistant
sudo docker compose -f ~/homeassistant/docker-compose.yml start homeassistant
sudo docker compose -f ~/homeassistant/docker-compose.yml ps   # check it says running
```

> **Why `-f`:** the Pi has an old, unused `~/compose.yml` that defines a
> different project with its own `homeassistant` service. On 2026-10-13 a
> restart issued from `~` printed `service "homeassistant" has no container to
> start` and still **exited 0**, so HA stayed down until it was started by hand.
> The container itself was intact.

When the sweep finishes, the probe prints the values worth comparing with the
unit's own display:
- T1–T4 against the **system temperatures** screen
- setpoints 206–210 against **parameters [SERVICE]**
- the counters against **Counters**

Note anything that disagrees.

Back on the Mac:

```bash
scp 'user@192.168.30.141:~/sherpa_observed_*.json' .
python3 tools/probe_sherpa.py --sanitize sherpa_observed_<timestamp>.json \
  tests/fixtures/sherpa_s2_big_14t_fw057.json
```

Commit the sanitized fixture only. Raw captures are gitignored because the by-id
path contains the adapter's serial number.

## After the run

- The heat pump display shows no E09.
- In HA, `sensor.sherpa_water_in` updates again within 30 s.
- The probe's last line shows the request count, the status breakdown and the
  p50/p95 latency. Note them in the commit message.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Capture complete | Sanitize and commit |
| 1 | Link problem: port won't open, or 199 unreadable | Check the adapter path, `--slave` (ADDR247 = 201) and wiring on terminal AB |
| 2 | Guard refused: unconfirmed, HA answering, or bus traffic | Stop whatever else is talking. The message says what was heard. |
| 3 | Identify code is not 1134 | A different register layout; re-run with `--force` only to collect a capture for a new profile |
| 130 | Interrupted (Ctrl-C) | Whatever was captured is saved |

If the listen guard reports **unframed bytes** rather than a Modbus frame, the
bus may simply be noisy (missing bias resistors) instead of having a second
master. Check that before reaching for `--listen-seconds 0`.

## Options worth knowing

- `--stages sweep,rules` (default), or just `rules` for a quick block-read check
  when a sweep already exists.
- `--first/--last` narrow the sweep. The default 0–999 matters: undocumented
  registers, such as the mode-command register for phase P5, only show up in a
  full sweep.
- `--watch-minutes 10` records a time series at the integration's poll cadence.
  **Not needed at uahs01:** `tools/legacy_snapshot.py` exported 57 days of the
  same registers from HA's recorder with no downtime (see `docs/p0_findings.md`).
  Use the watch stage only on a site with no recorder history.
- `--tcp HOST[:PORT]` for a Modbus-TCP gateway, plus `--rtu-over-tcp` for a
  transparent serial server. Customer sites without a USB adapter use these.
