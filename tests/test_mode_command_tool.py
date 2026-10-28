"""tools/mode_command_test.py, against a unit that behaves as RDE448 says.

The script runs once, on the real unit, with someone at the panel. These check
beforehand what matters there: that it refuses a step in the wrong ADDR220,
never leaves 106 unwritten for 255 s while it is meant to be writing, reads E09
and its clearing right, and writes standby when stopped. A fake clock stands in
for the minutes of waiting.
"""

from __future__ import annotations

import json

import pytest

import mode_command_test as tool
from custom_components.olimpia_sherpa_modbus.registers import E09_BIT, MODE_COMMAND_BITS


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Unit:
    """Follows 106 only with ADDR220 = 1, and raises E09 after 255 s unwritten.

    ``e09_for`` None: E09 stays up until the next write. A number: it shows for
    that long at every 255 s without a write, then clears itself -- what the
    panel showed on the reference unit. ``dhw_until``: a DHW cycle runs until
    then, whatever 106 says (short of standby). ``compressor_from``: the
    compressor runs from then on while the unit heats or cools (None: never), and
    its runtime counter (270-271) rises one per second; ``e09_stops_it`` stops it
    at each E09 for ``restart_delay`` s, as a compressor waiting out its restart
    delay would.
    """

    def __init__(self, clock: Clock, remote_controls: int = 1, panel_status: int = 0, *,
                 e09_for: float | None = None, dhw_until: float = 0,
                 compressor_from: float | None = None, e09_stops_it: bool = False,
                 restart_delay: float = 180, compressor_until: float | None = None) -> None:
        self.clock = clock
        self.remote_controls = remote_controls
        self.panel_status = panel_status
        self.e09_for = e09_for
        self.dhw_until = dhw_until
        self.mode_command = 0
        self.last_write = clock.now
        self.writes: list[tuple[float, int]] = []
        self.interrupt_on_write: int | None = None
        self.compressor_from, self.e09_stops_it = compressor_from, e09_stops_it
        self.restart_delay = restart_delay
        self.compressor_until = compressor_until
        self.counter = 0.0
        self._at = clock.now
        self._running = False
        self._off_until = 0.0

    def _compressor(self, status: int, e09: bool) -> None:
        now = self.clock.now
        if self._running:
            end = now if self.compressor_until is None else min(now, self.compressor_until)
            self.counter += max(0.0, end - self._at)
        self._at = now
        if e09 and self.e09_stops_it and self._running:
            self._off_until = now + self.restart_delay
        self._running = (self.compressor_from is not None and now >= self.compressor_from
                         and (self.compressor_until is None or now < self.compressor_until)
                         and bool(status & 3) and not status & 4 and now >= self._off_until)

    def _state(self) -> dict:
        serial = self.remote_controls == 1
        silent = self.clock.now - self.last_write
        if self.e09_for is None:
            e09 = serial and silent > 255
        else:
            e09 = serial and silent >= 255 and silent % 255 < self.e09_for
        status = self.panel_status
        if serial:
            v = self.mode_command
            status = 0 if v & 1 else (2 if v & 8 else 1 if v & 4 else 0) | (0x80 if v & 16 else 0)
            if not v & 1 and self.clock.now < self.dhw_until:
                status |= 0x06
        self._compressor(status, e09)
        return {"inputs": 894, "status": status, "alarm_1": (1 << 8) if e09 else 0,
                "alarm_2": 0, "override": 0,
                "outputs": 17 if status & 4 else 1 if status & 3 else 0,
                "mode_command": self.mode_command, "remote_controls": self.remote_controls}

    def sample(self, quick: bool = False, counter: bool = False) -> dict:
        state = self._state()
        return {**state, "compressor_seconds": int(self.counter)} if counter else state

    def identity(self) -> dict:
        return {"identify": 1134, "firmware": "0.57"}

    def command(self, value: int) -> dict:
        if self.interrupt_on_write is not None and len(self.writes) == self.interrupt_on_write:
            self.interrupt_on_write = None
            raise KeyboardInterrupt
        before = self.mode_command
        self.mode_command, self.last_write = value, self.clock.now
        self.writes.append((self.clock.now, value))
        state = self._state()
        return {"written": value, "before": before, "read_back": value, **{
            k: state[k] for k in ("status", "outputs", "alarm_1", "alarm_2", "override",
                                  "inputs", "remote_controls")}}


@pytest.fixture
def clock(monkeypatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(tool, "time", clock)
    return clock


@pytest.fixture
def run_tool(monkeypatch, tmp_path, clock):
    token = tmp_path / "token"
    token.write_text("secret\n")

    def run(unit: Unit, *args: str) -> tuple[int, dict]:
        monkeypatch.setattr(tool, "Api", lambda *_: unit)
        code = tool.main(["--token-file", str(token), "--dir", str(tmp_path / "rec"), *args])
        records = sorted((tmp_path / "rec").glob("*.json"))
        return code, json.loads(records[-1].read_text()) if records else {}

    return run


def _gaps(writes: list[tuple[float, int]]) -> list[float]:
    return [b[0] - a[0] for a, b in zip(writes, writes[1:], strict=False)]


def test_serial_runs_the_sequence_and_the_unit_follows(run_tool, clock):
    unit = Unit(clock)
    code, record = run_tool(unit, "serial")
    assert code == 0
    values = [v for _, v in unit.writes]
    assert [v for i, v in enumerate(values) if i == 0 or v != values[i - 1]] == \
        list(tool.SERIAL_STEPS)
    assert max(_gaps(unit.writes)) < 255                     # never long enough for E09
    assert [row["follows"] for row in record["verdict"]] == ["yes"] * len(tool.SERIAL_STEPS)


def test_serial_keeps_a_long_hold_alive(run_tool, clock):
    unit = Unit(clock)
    run_tool(unit, "serial", "--hold", "600", "--steps", "8")
    assert len(unit.writes) >= 10 and max(_gaps(unit.writes)) <= 65


def test_serial_refuses_without_serial_control(run_tool, clock):
    unit = Unit(clock, remote_controls=0)
    with pytest.raises(SystemExit, match="ADDR220 reads 0"):
        run_tool(unit, "serial")
    assert unit.writes == []


def test_serial_refuses_heating_and_cooling_together(run_tool, clock):
    with pytest.raises(SystemExit):
        run_tool(Unit(clock), "serial", "--steps", "12")


def test_panel_finds_106_ignored_and_puts_it_back(run_tool, clock):
    unit = Unit(clock, remote_controls=0)
    code, record = run_tool(unit, "panel")
    assert code == 0
    assert [v for _, v in unit.writes] == [tool.HEATING, 0]
    assert record["verdict"] == {"followed": False, "held": True}


def test_panel_needs_the_panel_on_standby(run_tool, clock):
    unit = Unit(clock, remote_controls=0, panel_status=2)          # heating selected
    with pytest.raises(SystemExit, match="select standby"):
        run_tool(unit, "panel")
    assert unit.writes == []


def test_watchdog_waits_out_a_dhw_cycle_then_times_each_e09(run_tool, clock):
    # As seen on 2026-10-28: a DHW cycle running, and E09 showing for about a second.
    unit = Unit(clock, dhw_until=300, e09_for=1.0)
    code, record = run_tool(unit, "watchdog")
    assert code == 0
    verdict = record["verdict"]
    assert verdict["status_at_start"] == 2                     # heating, no DHW cycle
    settle = [w for w in unit.writes if w[0] <= 300]
    assert max(_gaps(settle)) <= 60 + 30                       # kept alive while waiting
    assert [(e["up_s"], e["down_s"]) for e in verdict["e09"]] == [(255.0, 256.0), (510.0, 511.0)]
    assert verdict["changes"] == []
    assert _gaps(unit.writes)[-1] >= 600                       # the silence was real


def test_watchdog_sees_e09_stay_and_clear_on_the_rewrite(run_tool, clock):
    unit = Unit(clock)
    code, record = run_tool(unit, "watchdog", "--settle", "0")
    assert code == 0
    verdict = record["verdict"]
    assert [(e["up_s"], e["down_s"]) for e in verdict["e09"]] == [(255.5, None)]
    assert verdict["e09_up_at_rewrite"] and verdict["cleared_after_rewrite_s"] == 0.5


def test_watchdog_gives_up_waiting_and_writes_standby(run_tool, clock):
    unit = Unit(clock, dhw_until=10**6)
    code, record = run_tool(unit, "watchdog", "--settle", "120")
    assert code == 2 and "no heating without a DHW cycle" in record["stopped"]
    assert unit.writes[-1][1] == tool.STANDBY
    assert max(_gaps(unit.writes)) < 255


def test_need_compressor_refuses_to_start_the_silence_without_a_rising_counter(
        run_tool, clock):
    unit = Unit(clock)                                         # heating, but the compressor idles
    code, record = run_tool(unit, "watchdog", "--settle", "0", "--need-compressor",
                            "--compressor-window", "90")
    assert code == 2 and "did not rise" in record["stopped"]
    assert unit.writes[-1][1] == tool.STANDBY                  # the safe restore
    assert max(_gaps(unit.writes)) < 255                       # and no silence was started
    assert "verdict" not in record


def test_need_compressor_will_not_start_after_the_compressor_has_stopped(run_tool, clock):
    # It ran at the start and stopped 3 s later: a counter that merely rose once, a
    # while ago, is not a compressor running now.
    unit = Unit(clock, compressor_from=0, compressor_until=3)
    code, record = run_tool(unit, "watchdog", "--settle", "0", "--need-compressor",
                            "--compressor-window", "120")
    assert code == 2 and "did not rise" in record["stopped"]
    assert unit.writes[-1][1] == tool.STANDBY
    assert max(_gaps(unit.writes)) < 255
    assert "compressor_confirmed" not in record


def test_need_compressor_records_the_two_samples_before_the_final_write(run_tool, clock):
    unit = Unit(clock, compressor_from=0)
    _, record = run_tool(unit, "watchdog", "--settle", "0", "--need-compressor")
    confirmed = record["compressor_confirmed"]
    assert confirmed["counter_b"] - confirmed["counter_a"] >= tool.CONFIRM_RISE
    assert confirmed["t_b"] - confirmed["t_a"] >= tool.CONFIRM_GAP
    # the final write follows at once: the samples are the last events before it
    events = record["events"]
    last_write = min(i for i, e in enumerate(events) if e["kind"] == "write"
                     and e["t"] >= confirmed["t_b"])
    assert events[last_write - 1]["t"] == confirmed["t_b"]


def test_need_compressor_says_the_counter_kept_rising_through_each_e09(run_tool, clock):
    unit = Unit(clock, e09_for=1.0, compressor_from=0)
    code, record = run_tool(unit, "watchdog", "--settle", "0", "--need-compressor")
    assert code == 0
    verdict = record["verdict"]
    assert [c["rising"] for c in verdict["compressor_through_e09"]] == [True, True]
    assert verdict["compressor_kept_rising"] is True
    assert _gaps(unit.writes)[-1] >= 600
    assert any("compressor_seconds" in e for e in record["events"] if e["kind"] == "sample")


def test_need_compressor_notices_a_compressor_that_e09_stops(run_tool, clock):
    unit = Unit(clock, e09_for=1.0, compressor_from=0, e09_stops_it=True)
    code, record = run_tool(unit, "watchdog", "--settle", "0", "--need-compressor")
    assert code == 0
    verdict = record["verdict"]
    assert [c["rising"] for c in verdict["compressor_through_e09"]] == [False, False]
    assert verdict["compressor_kept_rising"] is False


def test_without_the_option_the_counter_is_not_read(run_tool, clock):
    unit = Unit(clock, e09_for=1.0, compressor_from=0)
    _, record = run_tool(unit, "watchdog", "--settle", "0")
    assert "compressor_kept_rising" not in record["verdict"]
    assert not any("compressor_seconds" in e for e in record["events"])


def test_the_counter_is_read_as_a_u32_high_word_first():
    assert tool.counter_value({"270": 1, "271": 2}) == 65538
    assert tool.counter_value({"270": 1}) is None


def test_ctrl_c_writes_standby(run_tool, clock):
    unit = Unit(clock)
    unit.interrupt_on_write = 2                                # during the third value
    code, record = run_tool(unit, "serial")
    assert code == 130
    assert unit.writes[-1][1] == tool.STANDBY
    assert record["stopped"] == "interrupted"


def test_restore_puts_back_what_status_found(run_tool, clock):
    unit = Unit(clock, remote_controls=0)
    unit.mode_command = 0
    run_tool(unit, "status")
    unit.mode_command = 8                                      # left over from the test
    code, _ = run_tool(unit, "restore")
    assert code == 0 and unit.writes[-1][1] == 0


def test_restore_waits_for_the_panel(run_tool, clock):
    unit = Unit(clock, remote_controls=1)
    with pytest.raises(SystemExit, match="set it back"):
        run_tool(unit, "restore")
    assert unit.writes == []


@pytest.mark.parametrize(("value", "status", "verdict"), [
    (1, 0, "yes"), (8, 0x62, "yes"), (8, 0, "no"), (8, 0x06, "dhw"), (10, 0x02, "yes"),
    (24, 0x82, "yes"), (24, 0x02, "no"), (4, 0x61, "yes"), (0, 0x06, "yes"), (0, 0x02, "no"),
])
def test_the_status_word_is_read_as_the_integration_reads_it(value, status, verdict):
    assert tool.follows(value, status) == verdict


def test_the_tool_agrees_with_the_register_map():
    assert {1 << bit: name for bit, name in MODE_COMMAND_BITS.items()} == tool.COMMAND_BITS
    assert tool.E09 == 1 << E09_BIT
    assert not [v for v in tool.SERIAL_STEPS if v & tool.HEATING and v & tool.COOLING]
    assert tool.command_name(0) == "dhw-only" and tool.command_name(10) == "heating+eco"
