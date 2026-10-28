# Probe runbook: capturing a Sherpa

`tools/probe_sherpa.py` reads the heat pump's holding registers over RS-485 and
writes a JSON capture. The capture becomes the integration's test fixture, so
the block planner and decoders are built on how the unit really behaves.

The probe is **read-only by construction**. It can only send function codes 3
and 4, and anything else raises before a byte is sent. It changes nothing on the
unit.

## Why Home Assistant must be stopped

RS-485 allows **one master**. Home Assistant polls the Sherpa every 10 s. If the
probe talks at the same time, the frames collide and the unit raises **E09**. The
probe protects against this in three ways:

1. On a serial link it refuses to start without `--i-stopped-home-assistant`.
2. It refuses while anything answers on `127.0.0.1:8123`. With host networking,
   a running Home Assistant always answers there.
3. It listens for 15 s before sending anything, and aborts if it hears a single
   byte. Home Assistant's 10 s poll always falls inside that window.

The port is also opened in exclusive mode (`TIOCEXCL`). That stops non-root
processes, but **not** a Home Assistant container running as root. Treat it as
a backstop, not the guard.

While Home Assistant is stopped, the heat pump keeps running on its own
controller. Only what Home Assistant does pauses.

## How long it takes

| Stage | Time |
|---|---|
| Listen guard | 15 s |
| Identity (10 registers) | ~1 s |
| Sweep 0–999, one register per read | 96 s on the reference unit (36 ms per read; undefined addresses answer with an exception at once) |
| Device rules (whole-run reads, count ladder, gaps, u32 halves, FC4) | a few seconds |
| Watch (optional, `--watch-minutes N`) | N minutes; Home Assistant stays down the whole time |

A full run takes Home Assistant down for 2–3 minutes, from stop to healthy. A
rules-only re-run with `--sweep-from` takes about 30 s.

## Steps

On the Home Assistant host, with the adapter on terminal AB. The example
assumes Home Assistant runs under Docker Compose; stop and start it however
your installation does.

```bash
sudo docker compose -f /path/to/docker-compose.yml stop homeassistant
python3 probe_sherpa.py --serial /dev/serial/by-id/usb-FTDI_...-port0 \
  --i-stopped-home-assistant
sudo docker compose -f /path/to/docker-compose.yml start homeassistant
sudo docker compose -f /path/to/docker-compose.yml ps   # check it says running
```

- **Always name the compose file.** Run from the wrong directory, compose can
  pick another project, report success, and start nothing.
- **Judge success by the container's state**, not by the exit code.
- **Run it detached** (`setsid nohup ... &`) over ssh, so a dropped session
  cannot leave Home Assistant down.

To re-run only the block-read rules against an earlier sweep (about 20 s of
downtime), add `--stages rules --sweep-from sherpa_observed_<timestamp>.json`.

When the sweep finishes, the probe prints the values worth comparing with the
unit's own display:
- T1–T4 against the **system temperatures** screen
- setpoints 206–210 against **parameters [SERVICE]**
- the counters against **Counters**

Note anything that disagrees. Then sanitize the capture:

```bash
python3 tools/probe_sherpa.py --sanitize sherpa_observed_<timestamp>.json \
  tests/fixtures/<model>_fw<firmware>.json
```

Commit the sanitized fixture only. Raw captures are gitignored because the by-id
path contains the adapter's serial number.

## After the run

- The heat pump display shows no E09.
- In Home Assistant, `sensor.sherpa_water_in` updates again within 30 s.
- The probe's last line shows the request count, the status breakdown and the
  p50/p95 latency. Note them in the commit message.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Capture complete | Sanitize and commit |
| 1 | Link problem: port won't open, or 199 unreadable | Check the adapter path, `--slave` (ADDR247) and wiring on terminal AB |
| 2 | Guard refused: unconfirmed, Home Assistant answering, or bus traffic | Stop whatever else is talking. The message says what was heard. |
| 3 | Identify code is not 1134 | A different register layout; re-run with `--force` only to collect a capture for a new profile |
| 130 | Interrupted (Ctrl-C) | Whatever was captured is saved |

If the listen guard reports **unframed bytes** rather than a Modbus frame, the
bus may simply be noisy (missing bias resistors) instead of having a second
master. Check that before reaching for `--listen-seconds 0`.

## Options worth knowing

- `--stages sweep,rules` (default), or just `rules` for a quick block-read check
  when a sweep already exists.
- `--first/--last` narrow the sweep. The default 0–999 matters: undocumented
  registers only show up in a full sweep.
- `--watch-minutes 10` records a time series at the integration's poll cadence.
  Home Assistant's recorder usually has the same series with no downtime, so use
  the watch stage only where there is no recorder history.
- `--tcp HOST[:PORT]` for a Modbus-TCP gateway, plus `--rtu-over-tcp` for a
  transparent serial server, where there is no USB adapter.
