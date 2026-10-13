"""The probe against simulated units: framing, fault handling, guards, stages.

Most tests drive the real ``SerialLink`` through a pseudo-terminal, so the
termios setup, select loop and CRC handling run exactly as on the Pi.
"""
from __future__ import annotations

import json
import socket
import struct

import pytest

import probe_sherpa as probe
from tests.sim import FakeSherpa, PtyServer, TcpServer, rtu_frame

FAST = ["--gap-ms", "0", "--timeout", "0.3", "--sweep-timeout", "0.15",
        "--resync-seconds", "0.02", "--listen-seconds", "0.3"]


def quiet(*_args, **_kwargs) -> None:
    pass


def client_for(link, **overrides) -> probe.Client:
    options = {"timeout": 0.3, "gap_ms": 0, "resync_s": 0.02}
    options.update(overrides)
    return probe.Client(link, 201, **options)


@pytest.fixture
def fake() -> FakeSherpa:
    return FakeSherpa()


@pytest.fixture
def pty_server(fake):
    server = PtyServer(fake)
    yield server
    server.close()


@pytest.fixture
def serial_link(pty_server):
    link = probe.SerialLink(pty_server.path)
    link.open()
    yield link
    link.close()


@pytest.fixture
def serial_client(serial_link) -> probe.Client:
    return client_for(serial_link)


def run(tmp_path, *args: str) -> tuple[int, dict | None]:
    out = tmp_path / "capture.json"
    rc = probe.main([*args, *FAST, "--out", str(out)])
    return rc, json.loads(out.read_text()) if out.exists() else None


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def test_crc16_matches_the_modbus_reference_vector():
    # The canonical example from the Modbus serial line spec: 01 03 00 00 00 0A -> C5 CD.
    assert probe.crc16(bytes.fromhex("01030000000A")) == bytes.fromhex("C5CD")


def test_parse_framing():
    assert probe.parse_framing("8n1") == ("N", 1)
    assert probe.parse_framing("8E1") == ("E", 1)
    assert probe.parse_framing("8N2") == ("N", 2)
    for bad in ("7E1", "8X1", "8N3", "8N"):
        with pytest.raises(ValueError):
            probe.parse_framing(bad)


def test_ranges_compress_addresses():
    assert probe.ranges([9, 1, 2, 3, 7, 10]) == [[1, 3], [7, 7], [9, 10]]
    assert probe.ranges([]) == []


def test_find_rtu_frame_names_what_it_heard():
    heard = b"\x00\xff" + PtyServer.CHATTER
    assert probe.find_rtu_frame(heard) == {
        "slave": 201, "fc": 3, "length": 8, "hex": PtyServer.CHATTER.hex()}
    reply = rtu_frame(201, bytes([3, 2, 0x01, 0x04]))
    assert probe.find_rtu_frame(reply)["length"] == 7
    assert probe.find_rtu_frame(b"\x00\x00\x00\x00\x00\x00") is None


# --------------------------------------------------------------------------
# read-only by construction
# --------------------------------------------------------------------------


def test_only_read_function_codes_exist():
    assert sorted(probe.ALLOWED_FUNCTION_CODES) == [3, 4]


@pytest.mark.parametrize("fc", [5, 6, 15, 16, 0x41])
def test_client_refuses_any_other_function_code(serial_client, fake, fc):
    with pytest.raises(ValueError, match="read-only"):
        serial_client.read(206, 1, fc=fc)
    assert fake.requests == []


# --------------------------------------------------------------------------
# RTU over a serial port
# --------------------------------------------------------------------------


def test_serial_reads_single_and_paired_registers(serial_client):
    assert serial_client.read(0).words == [260]
    assert serial_client.read(270, 2).words == [0, 24517]
    assert serial_client.read(4).words == [0xFFFF]   # -1: an absent-probe sentinel
    result = serial_client.read(0)
    assert result.ok and result.latency_ms is not None


def test_serial_exception_response(serial_client):
    result = serial_client.read(13)
    assert result.status == probe.EXCEPTION
    assert result.code == 2 and result.detail == "ILLEGAL_DATA_ADDRESS"


def test_timeout_then_recovery(serial_client, fake):
    fake.stall(1)
    assert serial_client.read(0).status == probe.TIMEOUT
    assert serial_client.read(0).words == [260]


def test_corrupted_crc_is_detected_not_decoded(serial_client, fake):
    fake.corrupt(1)
    assert serial_client.read(0).status == probe.CRC
    assert serial_client.read(0).words == [260]


def test_late_reply_is_never_taken_as_the_next_answer(serial_link, fake):
    # The reply to register 0 arrives after the timeout; the resync pause must
    # discard it, or register 1 would read 260 instead of 251.
    client = client_for(serial_link, timeout=0.1, resync_s=0.4)
    fake.delay(0.25)
    assert client.read(0).status == probe.TIMEOUT
    assert client.read(1).words == [251]


def test_adapter_echo_is_stripped(fake):
    server = PtyServer(fake, echo=True)
    link = probe.SerialLink(server.path)
    link.open()
    try:
        client = client_for(link)
        assert client.read(0).words == [260]
        assert client.read(208).words == [350]
        assert client.stats.echo_frames == 2
    finally:
        link.close()
        server.close()


# --------------------------------------------------------------------------
# TCP gateways
# --------------------------------------------------------------------------


def test_modbus_tcp_gateway(fake):
    server = TcpServer(fake, "mbap")
    link = probe.TcpLink("127.0.0.1", server.port, "mbap")
    try:
        client = client_for(link)
        assert client.read(0).words == [260]
        assert client.read(13).status == probe.EXCEPTION
        assert fake.requests[0][0] == 201  # the unit id carries the slave address
    finally:
        link.close()
        server.close()


def test_modbus_tcp_skips_a_stale_reply(fake):
    server = TcpServer(fake, "mbap")
    link = probe.TcpLink("127.0.0.1", server.port, "mbap")
    try:
        client = client_for(link, timeout=0.1, resync_s=0.0)
        fake.delay(0.25)
        assert client.read(0).status == probe.TIMEOUT
        assert client.read(1, timeout=1.0).words == [251]
        assert client.stats.stale_frames == 1
    finally:
        link.close()
        server.close()


def test_rtu_over_tcp(fake):
    server = TcpServer(fake, "rtu")
    link = probe.TcpLink("127.0.0.1", server.port, "rtu")
    try:
        client = client_for(link)
        assert client.read(0).words == [260]
        assert client.read(370, 2).words == [2, 14]
    finally:
        link.close()
        server.close()


# --------------------------------------------------------------------------
# single-master guard
# --------------------------------------------------------------------------


def test_serial_run_requires_confirmation(pty_server, fake, tmp_path):
    rc, data = run(tmp_path, "--serial", pty_server.path, "--no-ha-check")
    assert rc == probe.EXIT_GUARD
    assert data is None            # nothing captured, nothing written
    assert fake.requests == []     # and not a byte sent


def test_serial_run_refuses_while_home_assistant_answers(pty_server, fake, tmp_path):
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]
        rc, data = run(tmp_path, "--serial", pty_server.path, "--i-stopped-home-assistant",
                       "--ha-check", f"127.0.0.1:{port}")
    assert rc == probe.EXIT_GUARD
    assert data is None
    assert fake.requests == []


def test_listen_guard_detects_another_master(fake, tmp_path):
    server = PtyServer(fake, chatter=True)
    try:
        rc, data = run(tmp_path, "--serial", server.path, "--i-stopped-home-assistant",
                       "--no-ha-check")
    finally:
        server.close()
    assert rc == probe.EXIT_GUARD
    assert data["guard"]["refused"] == "traffic on the bus"
    assert data["guard"]["frame_heard"]["slave"] == 201
    assert "identity" not in data


def test_tcp_gateway_needs_no_confirmation(fake, tmp_path):
    server = TcpServer(fake, "mbap")
    try:
        rc, data = run(tmp_path, "--tcp", f"127.0.0.1:{server.port}", "--stages", "rules")
    finally:
        server.close()
    assert rc == probe.EXIT_OK
    assert data["identity"]["identify_code"] == 1134
    assert data["guard"]["listened"] is False


def test_existing_capture_is_never_overwritten(pty_server, tmp_path):
    out = tmp_path / "capture.json"
    out.write_text("{}")
    with pytest.raises(SystemExit):
        probe.main(["--serial", pty_server.path, "--out", str(out)])
    assert out.read_text() == "{}"


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------


def test_unexpected_identify_code_stops_before_the_sweep(pty_server, fake, tmp_path):
    fake.registers[199] = 1026  # the original Sherpa, a different layout
    rc, data = run(tmp_path, "--serial", pty_server.path, "--i-stopped-home-assistant",
                   "--no-ha-check")
    assert rc == probe.EXIT_IDENTITY
    assert data["identity"]["identify_mismatch"] is True
    assert "sweep" not in data


def test_force_continues_past_an_unexpected_identify_code(pty_server, fake, tmp_path):
    fake.registers[199] = 1026
    rc, data = run(tmp_path, "--serial", pty_server.path, "--i-stopped-home-assistant",
                   "--no-ha-check", "--force", "--last", "20", "--stages", "sweep")
    assert rc == probe.EXIT_OK
    assert data["sweep"]["registers"]["0"] == {"status": "OK", "raw": 260}


# --------------------------------------------------------------------------
# full run
# --------------------------------------------------------------------------


def test_full_run_produces_a_fixture(pty_server, fake, tmp_path):
    rc, data = run(tmp_path, "--serial", pty_server.path, "--i-stopped-home-assistant",
                   "--no-ha-check", "--last", "420")
    assert rc == probe.EXIT_OK

    ident = data["identity"]
    assert ident["identify_code"] == 1134
    assert ident["idu_model_name"] == "SHERPA S2 BIG"
    assert ident["odu_model_name"] == "SHERPA S2 14T"
    assert ident["firmware_197"] == "0.57"
    assert ident["remote_controls"] == 0 and ident["legionella_mode"] == 2

    regs = data["sweep"]["registers"]
    assert len(regs) == 421
    assert regs["0"] == {"status": "OK", "raw": 260}
    assert regs["243"] == {"status": "OK", "raw": 0xFFCE}   # -5.0 degC curve point
    assert regs["13"]["status"] == "EXCEPTION" and regs["13"]["code"] == 2
    defined = sum(1 for a in fake.registers if a <= 420)
    assert data["sweep"]["summary"]["by_status"]["OK"] == defined
    assert data["sweep"]["stalls"] == []

    summary = data["rules"]["summary"]
    # The fake answers in 15 runs up to 420; 8 are longer than one register:
    # 0-12, 99-106, 197-213, 219-263, 269-281, 291-326, 343-372, 380-388.
    assert summary["answering_runs"] == 15
    assert summary["whole_run_reads"] == 8 and summary["all_runs_readable"] is True
    assert summary["ladder_start"] == 219 and summary["ladder_tested_up_to"] == 45
    assert summary["safe_read_count"] == 45
    assert summary["read_across_exception_gap"] == "EXCEPTION"
    assert summary["read_across_silent_gap"] == "untested"
    assert summary["u32_half_readable"] is True
    assert summary["fc4"] == "unsupported"
    assert summary["block_values_match_sweep"] is True

    assert data["timing"]["by_status"]["OK"] > defined
    assert fake.write_requests == []

    clean = tmp_path / "fixture.json"
    assert probe.main(["--sanitize", str(tmp_path / "capture.json"), str(clean)]) == 0
    fixture = json.loads(clean.read_text())
    assert fixture["sanitized"] is True
    assert fixture["link"]["path"] == "/dev/ttyUSB0"
    assert fixture["sweep"] == data["sweep"]
    assert pty_server.path not in clean.read_text()   # not in argv either


def test_sanitize_scrubs_the_command_line(tmp_path):
    raw = tmp_path / "raw.json"
    by_id = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_X1234567-if00-port0"
    raw.write_text(json.dumps({
        "link": {"transport": "serial", "path": by_id},
        "argv": ["--serial", by_id, "--sweep-from", "/home/someone/old.json",
                 "--out", "/Users/someone/cap.json"],
        "guard": {"ha_check": "127.0.0.1:8123 not answering"},
    }))
    clean = tmp_path / "clean.json"
    assert probe.sanitize(str(raw), str(clean)) == 0
    data = json.loads(clean.read_text())
    assert data["argv"] == ["--serial", "/dev/ttyUSB0", "--sweep-from", "~/old.json",
                            "--out", "~/cap.json"]
    assert "X1234567" not in clean.read_text() and "someone" not in clean.read_text()
    assert "ha_check" not in data["guard"]


def _rules_on(fake, sweep_range=None) -> dict:
    server = PtyServer(fake)
    link = probe.SerialLink(server.path)
    link.open()
    try:
        client = client_for(link)
        out: dict = {}
        if sweep_range:
            probe.stage_sweep(client, out, *sweep_range, timeout=0.1, log=quiet)
        probe.stage_rules(client, out, log=quiet)
        return out["rules"]
    finally:
        link.close()
        server.close()


def test_rules_keep_only_the_contiguous_successes(fake):
    # Pairs 10/11 and 12/13 may not be split. On the ladder at 0, 13 registers
    # split the 12/13 pair and fail; 16 succeed again, but a planner may only
    # rely on counts below the first failure.
    fake.undefined, fake.max_count, fake.atomic_u32 = "zero", 64, {10, 12}
    rules = _rules_on(fake)
    assert [r["status"] for r in rules["count_ladder"]["reads"]][:8] == [
        "OK", "OK", "OK", "OK", "OK", "OK", "EXCEPTION", "OK"]
    assert rules["summary"]["safe_read_count"] == 10


def test_rules_find_a_device_limit_shorter_than_a_run(fake):
    fake.max_count = 20
    rules = _rules_on(fake, (190, 330))
    summary = rules["summary"]
    assert summary["all_runs_readable"] is False
    assert summary["unreadable_runs"] == [[219, 45, "EXCEPTION"], [291, 36, "EXCEPTION"]]
    assert summary["ladder_start"] == 219 and summary["safe_read_count"] == 20


def test_rules_without_a_sweep_ladder_from_zero(fake):
    fake.undefined, fake.max_count, fake.atomic_u32 = "zero", 64, {270, 272, 274}
    summary = _rules_on(fake)["summary"]
    assert summary["whole_run_reads"] == 0 and summary["all_runs_readable"] is None
    assert summary["ladder_start"] == 0 and summary["safe_read_count"] == 64
    assert summary["read_across_exception_gap"] == "untested"
    assert summary["u32_half_readable"] is False


def test_rules_can_reuse_an_earlier_sweep(pty_server, fake, tmp_path):
    first = tmp_path / "first.json"
    assert probe.main(["--serial", pty_server.path, "--i-stopped-home-assistant",
                       "--no-ha-check", "--last", "300", "--stages", "sweep",
                       *FAST, "--out", str(first)]) == 0
    sweeps_before = sum(1 for r in fake.requests if r[3] == 1)
    rc, data = run(tmp_path, "--serial", pty_server.path, "--i-stopped-home-assistant",
                   "--no-ha-check", "--stages", "rules", "--sweep-from", str(first))
    assert rc == probe.EXIT_OK
    assert data["sweep_source"]["file"] == "first.json"
    # up to 300: 0-12, 99-106, 197-213, 219-263, 269-281, 291-300
    assert data["rules"]["summary"]["whole_run_reads"] == 6
    # identity (10 single reads), u32 halves and FC4 -- but no second sweep
    singles = sum(1 for r in fake.requests if r[3] == 1) - sweeps_before
    assert singles < 20


def test_sweep_from_and_a_sweep_stage_are_exclusive(pty_server, tmp_path):
    earlier = tmp_path / "earlier.json"
    earlier.write_text("{}")
    with pytest.raises(SystemExit):
        probe.main(["--serial", pty_server.path, "--stages", "sweep,rules",
                    "--sweep-from", str(earlier), "--out", str(tmp_path / "x.json")])


# --------------------------------------------------------------------------
# sweep resilience
# --------------------------------------------------------------------------


def test_sweep_waits_out_a_stall_and_rereads(serial_client, fake):
    fake.stall_on(206, 8)  # five reads, the liveness check and two polls go unanswered
    out: dict = {}
    probe.stage_sweep(serial_client, out, 200, 230, timeout=0.1, stall_limit_s=5,
                      stall_poll_s=0.05, log=quiet)
    regs = out["sweep"]["registers"]
    assert len(out["sweep"]["stalls"]) == 1
    assert regs["206"] == {"status": "OK", "raw": 150}
    assert regs["210"] == {"status": "OK", "raw": 500}
    assert "NO_RESPONSE" not in out["sweep"]["summary"]["by_status"]


def test_silent_addresses_are_not_mistaken_for_a_stall(serial_client, fake):
    fake.silent = set(range(220, 227))
    out: dict = {}
    probe.stage_sweep(serial_client, out, 215, 230, timeout=0.1, stall_limit_s=5,
                      stall_poll_s=0.05, log=quiet)
    sweep = out["sweep"]
    assert sweep["stalls"] == []
    assert sweep["registers"]["220"] == {"status": "NO_RESPONSE", "last": "TIMEOUT"}
    assert sweep["registers"]["227"] == {"status": "OK", "raw": 20}
    assert sweep["summary"]["ranges"]["NO_RESPONSE"] == [[220, 226]]


def test_sweep_gives_up_when_the_link_stays_down(serial_client, fake):
    fake.stall(10_000)
    out: dict = {}
    probe.stage_sweep(serial_client, out, 200, 260, timeout=0.05, stall_limit_s=0.3,
                      stall_poll_s=0.05, log=quiet)
    assert out["sweep"]["aborted_at"] == 204
    assert len(out["sweep"]["registers"]) == 5


# --------------------------------------------------------------------------
# watch
# --------------------------------------------------------------------------


def test_watch_records_a_time_series(serial_client):
    tiers = (("control", 0.1, ((12, 1), (105, 1))), ("counter", 0.25, ((270, 2),)))
    out: dict = {}
    probe.stage_watch(serial_client, out, 0.6 / 60, tiers=tiers, log=quiet)
    watch = out["watch"]
    assert watch["failures"] == []
    assert watch["samples"] == len(watch["series"]) > 4
    counters = [s for s in watch["series"] if s["a"] == 270]
    assert counters and counters[0]["w"] == [0, 24517]
    assert [s["t"] for s in watch["series"]] == sorted(s["t"] for s in watch["series"])


def test_reply_parsing_rejects_a_wrong_byte_count(serial_client):
    # A frame that claims 4 data bytes for a 1-register read is not an answer.
    bogus = rtu_frame(201, bytes([3, 4]) + struct.pack(">HH", 1, 2))
    result = serial_client._rtu_decode(bogus, 3, 1)
    assert result.status == probe.MISMATCH


def test_rules_plan_on_the_reference_units_map(tmp_path):
    """The rules stage, driven by the real unit's sweep, against a fake with its map."""
    import pathlib

    capture = pathlib.Path(__file__).parents[1] / "fixtures" / "sherpa_s2_big_14t_fw057.json"
    fake = FakeSherpa.from_capture(capture)
    server = PtyServer(fake)
    try:
        rc, data = run(tmp_path, "--serial", server.path, "--i-stopped-home-assistant",
                       "--no-ha-check", "--stages", "rules", "--sweep-from", str(capture))
    finally:
        server.close()
    assert rc == probe.EXIT_OK
    summary = data["rules"]["summary"]
    assert summary["answering_runs"] == 21 and summary["whole_run_reads"] == 17
    assert summary["ladder_start"] == 217 and summary["ladder_tested_up_to"] == 65
    assert summary["all_runs_readable"] is True and summary["block_values_match_sweep"] is True
    assert data["timing"]["requests"] < 60   # a short second HA outage
