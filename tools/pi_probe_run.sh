#!/usr/bin/env bash
# Run tools/probe_sherpa.py on the Home Assistant host with HA stopped, and
# always bring HA back -- however the probe ends.
#
#   scp tools/probe_sherpa.py tools/pi_probe_run.sh user@pi:~/
#   ssh user@pi 'setsid nohup bash ~/pi_probe_run.sh > ~/probe_run.log 2>&1 < /dev/null &'
#   ssh user@pi 'tail -f ~/probe_run.log'          # until "running" or "STILL DOWN"
#
# Extra arguments go to the probe (e.g. --stages rules --sweep-from FILE).
# Detached with setsid so a dropped ssh session cannot leave HA down; the probe
# is capped at MAX_DOWNTIME_S and interrupted (it saves what it has) after that.
#
# The compose file is passed explicitly. On the reference Pi an old, unused
# ~/compose.yml defines a *different* project with a homeassistant service, so
# a bare `docker compose start` from the wrong directory finds "no container to
# start" -- and exits 0. That happened on 2026-10-13; HA stayed down until it
# was started by hand. Hence: explicit -f, and success judged by container
# state, never by exit code.
set -u

COMPOSE_FILE=${COMPOSE_FILE:-/home/user/homeassistant/docker-compose.yml}
SERVICE=${HA_SERVICE:-homeassistant}
# The RS-485 adapter: SHERPA_SERIAL, or the only device under /dev/serial/by-id.
SERIAL=${SHERPA_SERIAL:-}
if [ -z "$SERIAL" ]; then
  shopt -s nullglob
  adapters=(/dev/serial/by-id/*)
  if [ "${#adapters[@]}" -ne 1 ]; then
    echo "found ${#adapters[@]} serial adapters; set SHERPA_SERIAL to the one on the Sherpa's AB terminal"
    exit 1
  fi
  SERIAL=${adapters[0]}
fi
PROBE=${PROBE:-$HOME/probe_sherpa.py}
MAX_DOWNTIME_S=${MAX_DOWNTIME_S:-1200}

compose() { sudo -n docker compose -f "$COMPOSE_FILE" "$@"; }
stamp() { date -u +%T; }
ha_running() { [ -n "$(compose ps -q --status running "$SERVICE" 2>/dev/null)" ]; }
ha_port_open() { (exec 3<>/dev/tcp/127.0.0.1/8123) 2>/dev/null; }

start_ha() {
  echo "[$(stamp)] starting $SERVICE"
  compose start "$SERVICE"
  for _ in $(seq 1 30); do
    if ha_running; then echo "[$(stamp)] $SERVICE running"; return; fi
    sleep 1
  done
  echo "[$(stamp)] !! $SERVICE not running after 'start'; trying 'up -d'"
  compose up -d "$SERVICE"
  if ha_running; then
    echo "[$(stamp)] $SERVICE running"
  else
    echo "[$(stamp)] !! $SERVICE STILL DOWN -- start it by hand: sudo docker compose -f $COMPOSE_FILE up -d $SERVICE"
  fi
}

[ -f "$COMPOSE_FILE" ] || { echo "no compose file at $COMPOSE_FILE"; exit 1; }
[ -f "$PROBE" ] || { echo "no probe at $PROBE"; exit 1; }
[ -e "$SERIAL" ] || { echo "no serial adapter at $SERIAL"; exit 1; }
sudo -n true 2>/dev/null || { echo "needs passwordless sudo for docker"; exit 1; }
ha_running || { echo "$SERVICE is not running now; refusing (this script would start it afterwards)"; exit 1; }

trap start_ha EXIT
echo "[$(stamp)] stopping $SERVICE"
compose stop "$SERVICE" || exit 1
for _ in $(seq 1 30); do
  if ! ha_running && ! ha_port_open; then break; fi
  sleep 1
done
if ha_running || ha_port_open; then
  echo "[$(stamp)] !! $SERVICE did not stop; not probing"
  exit 1
fi
echo "[$(stamp)] $SERVICE stopped; running probe"
timeout -k 30 --signal=INT "$MAX_DOWNTIME_S" \
  python3 -u "$PROBE" --serial "$SERIAL" --i-stopped-home-assistant "$@"
echo "[$(stamp)] probe rc=$?"
