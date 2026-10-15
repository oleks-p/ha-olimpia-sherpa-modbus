#!/usr/bin/env python3
"""Read-only Modbus probe for Olimpia Splendid Sherpa heat pumps.

Establishes, on one unit and firmware, which holding registers answer, how the
controller treats multi-register reads, and how the RS-485 link behaves over
time. Emits ``sherpa_observed_<timestamp>.json``, which becomes the
integration's test fixture after ``--sanitize``.

Standard library only, Python 3.11+, so it runs on the Home Assistant host as-is:

    python3 probe_sherpa.py --serial /dev/serial/by-id/usb-FTDI_..._port0 \\
        --i-stopped-home-assistant
    python3 probe_sherpa.py --tcp 192.0.2.20:502                 # Modbus-TCP gateway
    python3 probe_sherpa.py --tcp 192.0.2.20:4196 --rtu-over-tcp  # transparent server
    python3 probe_sherpa.py --sanitize sherpa_observed_*.json tests/fixtures/x.json

The probe cannot write. It only ever sends function codes 3 and 4; anything else
raises before a byte leaves the host. Write verification is a separate, later
step (phase P4) with its own allow-list.

RS-485 has exactly one master. If Home Assistant -- or anything else -- is still
polling the unit, two masters collide and the heat pump raises E09. Stop Home
Assistant first. On a shared bus the probe refuses to start until you say you
have, then listens before it talks and aborts if anything else is on the line.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import json
import os
import re
import select
import socket
import struct
import sys
import time
from dataclasses import dataclass, field

PROBE_VERSION = "0.1.0"

FC_READ_HOLDING = 3
FC_READ_INPUT = 4
# The only function codes this tool can emit. P0 gathers evidence; no code path
# here can change a parameter on the unit, and a test pins that.
ALLOWED_FUNCTION_CODES = frozenset({FC_READ_HOLDING, FC_READ_INPUT})

EXCEPTIONS = {
    1: "ILLEGAL_FUNCTION",
    2: "ILLEGAL_DATA_ADDRESS",
    3: "ILLEGAL_DATA_VALUE",
    4: "SLAVE_DEVICE_FAILURE",
    5: "ACKNOWLEDGE",
    6: "SLAVE_DEVICE_BUSY",
    8: "MEMORY_PARITY_ERROR",
    10: "GATEWAY_PATH_UNAVAILABLE",
    11: "GATEWAY_TARGET_NO_RESPONSE",
}

OK = "OK"
EXCEPTION = "EXCEPTION"
TIMEOUT = "TIMEOUT"
CRC = "CRC"
MISMATCH = "MISMATCH"
DROPPED = "DROPPED"
# Sweep-only classification: the link was demonstrably alive, this address never
# answered. Different from TIMEOUT, which says nothing about the address.
NO_RESPONSE = "NO_RESPONSE"
TRANSIENT = frozenset({TIMEOUT, CRC, MISMATCH, DROPPED})

EXIT_OK, EXIT_LINK, EXIT_GUARD, EXIT_IDENTITY, EXIT_INTERRUPTED = 0, 1, 2, 3, 130

# The reference unit (SHERPA S2 BIG + S2 14T, firmware 0.57) reports 1134 here.
# Olimpia's SiOS Control manual lists 1026 for the original Sherpa and 1061 for
# Aquadue, so this register tells register layouts apart.
EXPECTED_IDENTIFY = 1134

# Manual 262860B, appendix X-3 (ADDR370 / ADDR371).
IDU_MODELS = {
    0: "SHERPA S2 SMALL", 1: "SHERPA S2 3W SMALL", 2: "SHERPA S2 BIG", 3: "SHERPA S2 3W BIG",
    4: "AQUADUE S2 SMALL", 5: "AQUADUE S2 BIG", 6: "AQUADUE TOWER S2 SMALL",
    7: "AQUADUE TOWER S2 BIG", 8: "SHERPA TOWER S2 SMALL", 9: "SHERPA TOWER S2 BIG",
}
ODU_MODELS = {
    0: "SHERPA 24", 1: "SHERPA 36", 2: "SHERPA 48", 3: "SHERPA 48 T", 4: "SHERPA 60",
    5: "SHERPA 60 T", 6: "SHERPA S2 E 4", 7: "SHERPA S2 E 6", 8: "SHERPA S2 E 8",
    9: "SHERPA S2 E 10", 10: "SHERPA S2 12", 11: "SHERPA S2 14", 12: "SHERPA S2 16",
    13: "SHERPA S2 12T", 14: "SHERPA S2 14T", 15: "SHERPA S2 16T",
}

# Read one at a time before anything else. 220/228/229 are not identity, but a
# later write-verification step needs to know what they were at capture time.
IDENTITY_REGISTERS = (
    (197, "fw_197"),          # the System screen shows display- and power-board
    (198, "fw_198"),          # versions; which register is which is unconfirmed
    (199, "identify_code"),
    (370, "idu_model"),
    (371, "odu_model"),
    (247, "modbus_address"),
    (401, "protocol"),        # 0 = ASCII, 1 = RTU
    (220, "remote_controls"),  # 0 display only, 1 serial, 2 free contacts
    (228, "dhw_source"),
    (229, "legionella_mode"),
)

# A register that is always defined (T1 water in). Used to tell "this address is
# silent" from "the whole link is stalled".
LIVENESS_ADDRESS = 0
# Consecutive transient failures before the sweep asks whether the link is alive.
STALL_RUN = 5

# Block-read rules. Ascending counts, one attempt each, never bisected: on
# devices like this the accepted counts are not monotonic, and a binary search
# lands on the wrong answer.
BLOCK_COUNTS = (2, 3, 4, 6, 8, 10, 13, 16, 20, 25, 32, 40, 50, 64, 80, 100, 120, 125)
MAX_READ = 125  # the Modbus limit for one FC3 request
# Where the count ladder runs when no sweep says where the registers are.
DEFAULT_LADDER_START = 0
# Holding registers expected to be constant for the length of a probe run. A
# block read that disagrees with the sweep on one of these is decoding garbage.
STABLE_ADDRESSES = frozenset(
    set(range(200, 263)) | set(range(370, 373)) | set(range(380, 388))
    | {9, 99, 103, 104, 106, 193, 197, 198, 199, 263, 266, 269, 296, 297, 401}
)

# Watch cadence mirrors the integration's poll tiers. Counters are read as pairs:
# reading the two halves of a u32 separately can tear across a carry.
WATCH_TIERS = (
    ("control", 10.0, ((8, 1), (12, 1), (100, 1), (101, 1), (102, 1), (105, 1), (388, 1))),
    ("process", 30.0, tuple((address, 1) for address in range(8))),
    ("counter", 60.0, ((270, 2), (272, 2), (274, 2))),
)

_BAUD_RATES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)


def crc16(data: bytes) -> bytes:
    """Modbus RTU CRC-16 (poly 0xA001, init 0xFFFF), low byte first on the wire."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def i16(raw: int) -> int:
    return raw - 0x10000 if raw & 0x8000 else raw


def parse_framing(framing: str) -> tuple[str, int]:
    """'8N1' -> ('N', 1). RTU requires 8 data bits, so only parity/stop vary."""
    text = framing.upper()
    if len(text) != 3 or text[0] != "8" or text[1] not in "NEO" or text[2] not in "12":
        raise ValueError(f"unsupported framing {framing!r}; expected 8N1, 8E1, 8O1 or 8N2")
    return text[1], int(text[2])


def split_hostport(text: str, default_port: int) -> tuple[str, int]:
    host, sep, port = text.rpartition(":")
    if not sep:
        return text, default_port
    return host, int(port)


def ranges(addresses) -> list[list[int]]:
    """[1, 2, 3, 7, 9, 10] -> [[1, 3], [7, 7], [9, 10]]."""
    out: list[list[int]] = []
    for address in sorted(addresses):
        if out and address == out[-1][1] + 1:
            out[-1][1] = address
        else:
            out.append([address, address])
    return out


def find_rtu_frame(buf: bytes) -> dict | None:
    """Return the first CRC-valid RTU request or response found in ``buf``.

    Used by the listen guard to say *what* it heard. Only plausible frame
    lengths are tried at each offset, so it stays cheap on a few hundred bytes.
    """
    for i in range(len(buf) - 4):
        fc = buf[i + 1]
        lengths = [5] if fc & 0x80 else [8]
        if fc in (FC_READ_HOLDING, FC_READ_INPUT) and i + 2 < len(buf):
            lengths.append(5 + buf[i + 2])  # a response: byte count follows the fc
        for length in lengths:
            frame = buf[i:i + length]
            if len(frame) == length and crc16(frame[:-2]) == frame[-2:]:
                return {"slave": frame[0], "fc": fc, "length": length, "hex": frame.hex()}
    return None


# --------------------------------------------------------------------------
# transports -- byte streams only; Modbus framing lives in Client
# --------------------------------------------------------------------------


class LinkDropped(Exception):
    """The byte stream ended: TCP peer closed, USB adapter unplugged."""


class SerialLink:
    """An RS-485 adapter driven through termios in raw mode."""

    kind = "serial"
    framer = "rtu"

    def __init__(self, path: str, baud: int = 9600, framing: str = "8N1"):
        if baud not in _BAUD_RATES:
            raise ValueError(f"unsupported baud rate {baud}")
        self.path, self.baud, self.framing = path, baud, framing
        self.parity, self.stopbits = parse_framing(framing)
        self.fd: int | None = None
        self.exclusive = False

    @property
    def is_open(self) -> bool:
        return self.fd is not None

    def open(self) -> None:
        import fcntl
        import termios

        fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            # Exclusive mode makes a later open() of this tty fail with EBUSY --
            # for non-root processes. Root ignores it, and the HA container runs
            # as root, so this complements the listen guard rather than
            # replacing it.
            with contextlib.suppress(OSError, AttributeError):
                fcntl.ioctl(fd, termios.TIOCEXCL)
                self.exclusive = True
            attrs = termios.tcgetattr(fd)
            cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
            if self.parity in "EO":
                cflag |= termios.PARENB
            if self.parity == "O":
                cflag |= termios.PARODD
            if self.stopbits == 2:
                cflag |= termios.CSTOPB
            speed = getattr(termios, f"B{self.baud}")
            cc = attrs[6]
            cc[termios.VMIN] = 0
            cc[termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, [0, 0, cflag, 0, speed, speed, cc])
            termios.tcflush(fd, termios.TCIOFLUSH)
        except BaseException:
            self._release(fd)
            os.close(fd)
            raise
        self.fd = fd

    def _release(self, fd: int) -> None:
        """Give exclusive mode back before closing.

        macOS clears it on close, but Linux keeps it on the tty while anything
        else holds it open -- a pty's other end, say -- so the next open() of
        the same port, even by this tool, fails with EBUSY.
        """
        if self.exclusive:
            import fcntl
            import termios

            with contextlib.suppress(OSError, AttributeError):
                fcntl.ioctl(fd, termios.TIOCNXCL)
            self.exclusive = False

    def close(self) -> None:
        if self.fd is not None:
            self._release(self.fd)
            with contextlib.suppress(OSError):
                os.close(self.fd)
            self.fd = None

    def send(self, data: bytes) -> None:
        import termios

        assert self.fd is not None
        view = memoryview(data)
        while view:
            _r, writable, _x = select.select([], [self.fd], [], 1.0)
            if not writable:
                raise LinkDropped("serial port not writable")
            try:
                view = view[os.write(self.fd, view):]
            except OSError as exc:
                raise LinkDropped(str(exc)) from exc
        # Half-duplex: return once the frame has left the UART, so the response
        # timeout starts when the slave can actually answer.
        with contextlib.suppress(termios.error):
            termios.tcdrain(self.fd)

    def recv(self, timeout: float) -> bytes:
        assert self.fd is not None
        readable, _w, _x = select.select([self.fd], [], [], max(0.0, timeout))
        if not readable:
            return b""
        try:
            data = os.read(self.fd, 512)
        except BlockingIOError:
            return b""
        except OSError as exc:  # EIO when the adapter or a pty master goes away
            raise LinkDropped(str(exc)) from exc
        if not data:
            # A tty in non-canonical mode reads 0 bytes on hangup; don't spin.
            time.sleep(0.01)
        return data

    def flush_input(self) -> None:
        import termios

        if self.fd is not None:
            with contextlib.suppress(termios.error):
                termios.tcflush(self.fd, termios.TCIFLUSH)

    def describe(self) -> dict:
        return {"transport": self.kind, "path": self.path, "baud": self.baud,
                "framing": self.framing, "exclusive": self.exclusive}


class TcpLink:
    """A TCP stream: a Modbus-TCP gateway (MBAP) or a transparent serial server (RTU)."""

    def __init__(self, host: str, port: int, framer: str, connect_timeout: float = 5.0):
        self.host, self.port, self.framer = host, port, framer
        self.kind = "rtu_over_tcp" if framer == "rtu" else "tcp"
        self.connect_timeout = connect_timeout
        self.sock: socket.socket | None = None

    @property
    def is_open(self) -> bool:
        return self.sock is not None

    def open(self) -> None:
        self.close()
        self.sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def close(self) -> None:
        if self.sock is not None:
            with contextlib.suppress(OSError):
                self.sock.close()
            self.sock = None

    def send(self, data: bytes) -> None:
        assert self.sock is not None
        try:
            self.sock.sendall(data)
        except OSError as exc:
            raise LinkDropped(str(exc)) from exc

    def recv(self, timeout: float) -> bytes:
        assert self.sock is not None
        self.sock.settimeout(max(timeout, 0.001))
        try:
            data = self.sock.recv(512)
        except TimeoutError:
            return b""
        except OSError as exc:
            raise LinkDropped(str(exc)) from exc
        if not data:
            raise LinkDropped("connection closed by peer")
        return data

    def flush_input(self) -> None:
        if self.sock is None:
            return
        self.sock.setblocking(False)
        try:
            while self.sock.recv(4096):
                pass
        except (BlockingIOError, OSError):
            pass
        finally:
            self.sock.setblocking(True)

    def describe(self) -> dict:
        return {"transport": self.kind, "host": self.host, "port": self.port}


# --------------------------------------------------------------------------
# Modbus client
# --------------------------------------------------------------------------


@dataclass
class Result:
    status: str
    words: list[int] | None = None
    code: int | None = None
    detail: str | None = None
    latency_ms: float | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK


@dataclass
class Stats:
    counts: dict[str, int] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)
    echo_frames: int = 0
    stale_frames: int = 0

    def record(self, result: Result) -> None:
        self.counts[result.status] = self.counts.get(result.status, 0) + 1
        if result.latency_ms is not None and result.ok:
            self.latencies_ms.append(result.latency_ms)

    def summary(self) -> dict:
        lat = sorted(self.latencies_ms)

        def pct(p: float) -> float | None:
            return lat[round(p / 100 * (len(lat) - 1))] if lat else None

        return {
            "requests": sum(self.counts.values()),
            "by_status": dict(sorted(self.counts.items())),
            "latency_ms": {"p50": pct(50), "p95": pct(95), "max": lat[-1] if lat else None,
                           "n": len(lat)},
            "echo_frames": self.echo_frames,
            "stale_frames": self.stale_frames,
        }


class Client:
    """Modbus master for one slave on one link. Reads only.

    Every request waits out a quiet gap after the previous exchange (the Sherpa
    needs about 60 ms between frames). After any failed exchange the client
    waits ``resync_s`` and discards whatever arrived: RTU has no transaction id,
    so a late reply left in the buffer would otherwise be read as the answer to
    the *next* request.
    """

    def __init__(self, link, slave: int, *, timeout: float = 3.0, gap_ms: float = 60.0,
                 resync_s: float = 1.0, echo_check: bool = True):
        self.link, self.slave = link, slave
        self.timeout, self.gap_s, self.resync_s = timeout, gap_ms / 1000.0, resync_s
        self.echo_check = echo_check
        self.stats = Stats()
        self._quiet_until = 0.0
        self._tid = 0
        self._rx = b""

    def read(self, address: int, count: int = 1, *, fc: int = FC_READ_HOLDING,
             timeout: float | None = None) -> Result:
        if not 0 <= address <= 0xFFFF or not 1 <= count <= 125 or address + count > 0x10000:
            raise ValueError(f"invalid read {address}+{count}")
        pdu = struct.pack(">BHH", fc, address, count)
        return self._transact(pdu, count, self.timeout if timeout is None else timeout)

    def _transact(self, pdu: bytes, count: int, timeout: float) -> Result:
        if pdu[0] not in ALLOWED_FUNCTION_CODES:
            raise ValueError(f"function code {pdu[0]} refused: this probe is read-only")
        delay = self._quiet_until - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        started = time.monotonic()
        try:
            if not self.link.is_open:
                self.link.open()
            if self.link.framer == "rtu":
                result = self._rtu(pdu, count, timeout)
            else:
                result = self._mbap(pdu, count, timeout)
        except (LinkDropped, OSError) as exc:
            self.link.close()
            result = Result(DROPPED, detail=f"{type(exc).__name__}: {exc}")
        if result.ok or result.status == EXCEPTION:
            result.latency_ms = round((time.monotonic() - started) * 1000, 1)
        else:
            self._resync()
        self._quiet_until = time.monotonic() + self.gap_s
        self.stats.record(result)
        return result

    def _resync(self) -> None:
        time.sleep(self.resync_s)
        self._rx = b""
        with contextlib.suppress(OSError, LinkDropped):
            self.link.flush_input()

    # -- RTU ----------------------------------------------------------------

    def _rtu(self, pdu: bytes, count: int, timeout: float) -> Result:
        frame = bytes([self.slave]) + pdu
        frame += crc16(frame)
        self.link.flush_input()
        self.link.send(frame)
        deadline = time.monotonic() + timeout
        buf = b""
        echo_checked = not self.echo_check
        while True:
            if not echo_checked and len(buf) >= len(frame):
                echo_checked = True
                if buf.startswith(frame):
                    # Some adapters hear their own transmission; drop it.
                    buf = buf[len(frame):]
                    self.stats.echo_frames += 1
            need = None
            if len(buf) >= 3:
                need = 5 if buf[1] & 0x80 else 5 + buf[2]
            maybe_echo = not echo_checked and frame.startswith(buf)
            if need is not None and len(buf) >= need and not maybe_echo:
                return self._rtu_decode(buf[:need], pdu[0], count)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if need is not None and len(buf) >= need:
                    return self._rtu_decode(buf[:need], pdu[0], count)
                return Result(TIMEOUT, detail=f"{len(buf)} bytes" if buf else "no response")
            buf += self.link.recv(remaining)

    def _rtu_decode(self, frame: bytes, fc: int, count: int) -> Result:
        if crc16(frame[:-2]) != frame[-2:]:
            return Result(CRC, detail=frame.hex())
        slave, rfc = frame[0], frame[1]
        if slave != self.slave or rfc & 0x7F != fc:
            return Result(MISMATCH, detail=f"reply from slave {slave} fc {rfc}")
        if rfc & 0x80:
            code = frame[2]
            return Result(EXCEPTION, code=code, detail=EXCEPTIONS.get(code, f"exception_{code}"))
        if frame[2] != 2 * count:
            return Result(MISMATCH, detail=f"{frame[2]} data bytes for {count} registers")
        return Result(OK, words=list(struct.unpack(f">{count}H", frame[3:3 + 2 * count])))

    # -- MBAP (Modbus TCP) ---------------------------------------------------

    def _recv_exact(self, n: int, deadline: float) -> bytes | None:
        while len(self._rx) < n:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._rx += self.link.recv(remaining)
        data, self._rx = self._rx[:n], self._rx[n:]
        return data

    def _mbap(self, pdu: bytes, count: int, timeout: float) -> Result:
        self._tid = (self._tid + 1) & 0xFFFF
        self.link.send(struct.pack(">HHHB", self._tid, 0, len(pdu) + 1, self.slave) + pdu)
        deadline = time.monotonic() + timeout
        while True:
            header = self._recv_exact(7, deadline)
            if header is None:
                return Result(TIMEOUT, detail="no response")
            tid, _pid, length, _unit = struct.unpack(">HHHB", header)
            body = self._recv_exact(length - 1, deadline) if length > 1 else b""
            if body is None:
                return Result(TIMEOUT, detail="truncated frame")
            if tid != self._tid:
                self.stats.stale_frames += 1  # a late reply to an earlier request
                continue
            if not body:
                return Result(MISMATCH, detail="empty pdu")
            rfc = body[0]
            if rfc & 0x7F != pdu[0]:
                return Result(MISMATCH, detail=f"fc {rfc}")
            if rfc & 0x80:
                code = body[1] if len(body) > 1 else 0
                return Result(EXCEPTION, code=code,
                              detail=EXCEPTIONS.get(code, f"exception_{code}"))
            if len(body) < 2 or body[1] != 2 * count or len(body) < 2 + 2 * count:
                return Result(MISMATCH, detail=f"bad length for {count} registers")
            return Result(OK, words=list(struct.unpack(f">{count}H", body[2:2 + 2 * count])))


def entry(result: Result) -> dict:
    if result.ok and result.words is not None:
        if len(result.words) == 1:
            return {"status": OK, "raw": result.words[0]}
        return {"status": OK, "words": result.words}
    if result.status == EXCEPTION:
        return {"status": EXCEPTION, "code": result.code, "detail": result.detail}
    return {"status": result.status, "detail": result.detail}


# --------------------------------------------------------------------------
# stage 0: single-master guard
# --------------------------------------------------------------------------

REFUSE_UNCONFIRMED = """\
refusing to start: this link reaches the RS-485 bus directly.

RS-485 allows one master. If Home Assistant is still polling the heat pump, the
two masters collide and the unit raises E09. Stop it first, e.g. on the host:

    sudo docker compose -f /path/to/docker-compose.yml stop homeassistant

then re-run with --i-stopped-home-assistant, and start it again afterwards with
the same -f ... start homeassistant. Always name the compose file: run from the
wrong directory, compose can pick another project and report success while
starting nothing. tools/pi_probe_run.sh does all of this and checks the result."""


def preflight(args, link_kind: str, out: dict, log=print) -> int:
    """Checks that need no open link. Returns an exit code (0 = go)."""
    guard = out.setdefault("guard", {})
    guard["operator_confirmed"] = bool(args.i_stopped_home_assistant)
    shared_bus = link_kind in ("serial", "rtu_over_tcp")
    if shared_bus and not args.i_stopped_home_assistant:
        guard["refused"] = "operator did not confirm Home Assistant is stopped"
        log(REFUSE_UNCONFIRMED)
        return EXIT_GUARD
    if not shared_bus and not args.i_stopped_home_assistant:
        log("note: a Modbus-TCP gateway serialises its clients, so a running Home Assistant\n"
            "      will not collide on the bus -- but its polls will interleave with the probe.")
    if link_kind == "serial" and not args.no_ha_check:
        host, port = split_hostport(args.ha_check, 8123)
        try:
            with socket.create_connection((host, port), timeout=1.0):
                pass
        except OSError:
            guard["ha_check"] = f"{host}:{port} not answering"
        else:
            guard["refused"] = f"Home Assistant is answering on {host}:{port}"
            log(f"refusing to start: something is answering on {host}:{port}, which looks like\n"
                "a running Home Assistant. Stop it first (or pass --no-ha-check if that port\n"
                "is not Home Assistant).")
            return EXIT_GUARD
    return EXIT_OK


def listen_before_talk(link, seconds: float, out: dict, log=print) -> int:
    """Stay silent for ``seconds`` and refuse if anything else is on the line.

    Home Assistant's control tier polls every 10 s, so the 15 s default always
    spans at least one of its requests and the unit's reply.
    """
    guard = out.setdefault("guard", {})
    guard["listen_seconds"] = seconds
    if seconds <= 0 or link.kind == "tcp":
        guard["listened"] = False
        return EXIT_OK
    log(f"listening {seconds:.0f}s for other bus traffic before sending anything ...")
    link.flush_input()
    deadline = time.monotonic() + seconds
    heard = b""
    first_byte_at = None
    while (remaining := deadline - time.monotonic()) > 0:
        heard += link.recv(min(remaining, 0.5))
        if heard and first_byte_at is None:
            first_byte_at = time.monotonic()
        # Keep listening a moment after the first byte so a whole frame lands.
        if first_byte_at is not None and time.monotonic() - first_byte_at > 1.0:
            break
        if len(heard) > 512:
            break
    guard["listened"] = True
    guard["bytes_heard"] = len(heard)
    if not heard:
        return EXIT_OK
    frame = find_rtu_frame(heard)
    guard["frame_heard"] = frame
    guard["sample_hex"] = heard[:64].hex()
    guard["refused"] = "traffic on the bus"
    if frame is not None:
        what = (f"a Modbus frame (slave {frame['slave']}, function {frame['fc']}): "
                "another master is polling")
    else:
        what = ("unframed bytes: line noise, or another master at a different baud rate"
                " or framing")
    log(f"refusing to start: heard {len(heard)} bytes on the bus -- {what}.\n"
        f"  first bytes: {heard[:32].hex(' ')}\n"
        "Make sure Home Assistant (and any other controller on this RS-485 pair) is stopped.")
    return EXIT_GUARD


# --------------------------------------------------------------------------
# stage 1: identity
# --------------------------------------------------------------------------


def firmware_text(raw: int | None) -> str | None:
    """57 -> '0.57', matching how the reference unit's firmware is quoted."""
    return None if raw is None else f"{raw // 100}.{raw % 100:02d}"


def stage_identity(client: Client, out: dict, *, force: bool = False, log=print) -> int:
    log("\n== identity ==")
    ident: dict = {"reads": {}}
    for address, key in IDENTITY_REGISTERS:
        result = client.read(address)
        if result.status in TRANSIENT:
            result = client.read(address)  # one retry: short stalls are normal here
        ident["reads"][str(address)] = entry(result)
        ident[key] = result.words[0] if result.ok else None
    ident["firmware_197"] = firmware_text(ident["fw_197"])
    ident["firmware_198"] = firmware_text(ident["fw_198"])
    ident["idu_model_name"] = IDU_MODELS.get(ident["idu_model"])
    ident["odu_model_name"] = ODU_MODELS.get(ident["odu_model"])
    ident["expected_identify"] = EXPECTED_IDENTIFY
    out["identity"] = ident

    for address, key in IDENTITY_REGISTERS:
        value = ident[key]
        shown = value if value is not None else ident["reads"][str(address)]["status"]
        extra = ""
        if key == "idu_model":
            extra = f"  ({ident['idu_model_name']})"
        elif key == "odu_model":
            extra = f"  ({ident['odu_model_name']})"
        elif key.startswith("fw_"):
            extra = f"  ({firmware_text(value)})"
        log(f"  {address:4} {key:16} = {shown}{extra}")

    code = ident["identify_code"]
    if code is None:
        log("  !! cannot read the identify register (199); is this a Sherpa, and is the slave "
            f"address right (--slave {client.slave})?")
        return EXIT_LINK
    if code != EXPECTED_IDENTIFY:
        ident["identify_mismatch"] = True
        log(f"  !! identify code {code} is not the reference unit's {EXPECTED_IDENTIFY}: the "
            "register layout may differ.")
        if not force:
            log("     Stopping here. Re-run with --force to sweep it anyway.")
            return EXIT_IDENTITY
    if ident["modbus_address"] not in (None, client.slave):
        log(f"  !! ADDR247 says {ident['modbus_address']} but we addressed {client.slave}")
    return EXIT_OK


# --------------------------------------------------------------------------
# stage 2: sweep
# --------------------------------------------------------------------------


def _alive(client: Client) -> bool:
    return client.read(LIVENESS_ADDRESS).ok


def _wait_for_link(client: Client, limit_s: float, poll_s: float, at: int, log) -> dict | None:
    started = time.monotonic()
    log(f"  !! link stalled near register {at}; waiting up to {limit_s:.0f}s for it to return")
    while time.monotonic() - started < limit_s:
        time.sleep(poll_s)
        if _alive(client):
            duration = round(time.monotonic() - started, 1)
            log(f"     link back after {duration}s")
            return {"at": at, "waited_s": duration, "failures_before_detection": STALL_RUN}
    return None


def stage_sweep(client: Client, out: dict, first: int, last: int, *, timeout: float = 1.0,
                stall_limit_s: float = 120.0, stall_poll_s: float = 3.0, log=print) -> None:
    """Read every holding register in [first, last] with count = 1.

    RTU stalls of 10-30 s are normal for this unit, so a run of timeouts is not
    taken at face value: the sweep checks a known-good register to decide
    between "these addresses are silent" and "the link is stalled", waits out a
    stall, and re-reads what it lost. Anything still failing gets one more try
    at the end before it is recorded as NO_RESPONSE.
    """
    total = last - first + 1
    est = total * (client.gap_s + 0.05)
    log(f"\n== sweep: holding {first}..{last} ({total} reads, roughly {est / 60:.1f} min "
        "if every address answers) ==")
    regs: dict[str, dict] = {}
    stalls: list[dict] = []
    sweep = {"first": first, "last": last, "timeout_s": timeout, "registers": regs,
             "stalls": stalls}
    out["sweep"] = sweep
    started = time.monotonic()
    run: list[int] = []
    aborted = False
    for address in range(first, last + 1):
        result = client.read(address, timeout=timeout)
        regs[str(address)] = entry(result)
        if result.status not in TRANSIENT:
            run.clear()
        else:
            run.append(address)
            if len(run) >= STALL_RUN:
                if _alive(client):
                    run.clear()  # address-specific silence; retried in the final pass
                else:
                    stall = _wait_for_link(client, stall_limit_s, stall_poll_s, address, log)
                    if stall is None:
                        sweep["aborted_at"] = address
                        log(f"  !! link did not come back within {stall_limit_s:.0f}s; "
                            "stopping the sweep")
                        aborted = True
                        break
                    stalls.append(stall)
                    for lost in run:
                        regs[str(lost)] = entry(client.read(lost, timeout=timeout))
                    run.clear()
        done = address - first + 1
        if done % 100 == 0 or address == last:
            log(f"  {done:4}/{total} read, {time.monotonic() - started:5.0f}s elapsed")

    if not aborted:
        for key, value in list(regs.items()):
            if value["status"] in TRANSIENT:
                result = client.read(int(key))
                if result.ok or result.status == EXCEPTION:
                    regs[key] = entry(result)
                else:
                    regs[key] = {"status": NO_RESPONSE, "last": result.status}

    by_status: dict[str, list[int]] = {}
    for key, value in regs.items():
        by_status.setdefault(value["status"], []).append(int(key))
    sweep["summary"] = {
        "duration_s": round(time.monotonic() - started, 1),
        "by_status": {status: len(addrs) for status, addrs in sorted(by_status.items())},
        "ranges": {status: ranges(addrs) for status, addrs in sorted(by_status.items())},
    }
    for status, addrs in sorted(by_status.items()):
        shown = ", ".join(f"{a}-{b}" if a != b else f"{a}" for a, b in ranges(addrs)[:12])
        more = " ..." if len(ranges(addrs)) > 12 else ""
        log(f"  {status:12} {len(addrs):4}  {shown}{more}")
    print_highlights(regs, log)


def print_highlights(regs: dict[str, dict], log=print) -> None:
    """The values worth checking against the unit's own display, right now."""

    def raw(address: int) -> int | None:
        value = regs.get(str(address))
        return value["raw"] if value and value["status"] == OK and "raw" in value else None

    def temp(address: int) -> str:
        value = raw(address)
        return "-" if value is None else f"{i16(value) / 10:.1f}"

    def u32(address: int) -> str:
        hi, lo = raw(address), raw(address + 1)
        return "-" if hi is None or lo is None else str((hi << 16) | lo)

    def word(address: int) -> str:
        value = raw(address)
        return "-" if value is None else f"{value} (0x{value:04x})"

    log("\n  compare with the display (system temperatures / service parameters):")
    log(f"    T1 water in {temp(0)}  T2 water out {temp(1)}  T3 DHW tank {temp(2)}  "
        f"T4 outdoor {temp(3)} degC")
    log(f"    setpoints 206-210: {temp(206)} / {temp(207)} / {temp(208)} / {temp(209)} / "
        f"{temp(210)} degC")
    log(f"    status {word(12)}  outputs {word(105)}  override {word(102)}  "
        f"alarms {word(100)} / {word(101)}")
    log(f"    counters (s): compressor {u32(270)}  pump {u32(272)}  filter {u32(274)}  "
        f"pump step {word(388)}")


# --------------------------------------------------------------------------
# stage 3: device rules
# --------------------------------------------------------------------------


def _differs_from_sweep(sweep_regs: dict[str, dict], start: int, words: list[int]) -> list[int]:
    out = []
    for offset, value in enumerate(words):
        address = start + offset
        seen = sweep_regs.get(str(address))
        if (address in STABLE_ADDRESSES and seen and seen.get("status") == OK
                and seen.get("raw") != value):
            out.append(address)
    return out


def _gap_targets(sweep_regs: dict[str, dict]) -> list[tuple[str, int, int]]:
    """First gap of each kind with answering neighbours: (kind, start, count)."""
    statuses = {int(k): v["status"] for k, v in sweep_regs.items()}
    found: dict[str, tuple[str, int, int]] = {}
    addresses = sorted(statuses)
    i = 0
    while i < len(addresses):
        address = addresses[i]
        status = statuses[address]
        if status in (EXCEPTION, NO_RESPONSE) and status not in found:
            j = i
            while j + 1 < len(addresses) and statuses[addresses[j + 1]] == status:
                j += 1
            low, high = address - 1, addresses[j] + 1
            span = high - low + 1
            if statuses.get(low) == OK and statuses.get(high) == OK and span <= 125:
                found[status] = (status, low, span)
            i = j + 1
            continue
        i += 1
    return list(found.values())


def _answering_runs(sweep_regs: dict[str, dict]) -> list[list[int]]:
    return ranges(int(k) for k, v in sweep_regs.items() if v.get("status") == OK)


def stage_rules(client: Client, out: dict, log=print) -> None:
    """Establish what the integration's block planner may do.

    With a sweep (from this run, or loaded with --sweep-from) the tests follow
    the map the sweep found:

    1. every run of answering registers, read whole (in 125-register chunks).
       These are exactly the reads a block planner would issue;
    2. a count ladder at the start of the longest run, which finds the device's
       per-request limit if it is shorter than the run;
    3. one read across each kind of gap, the u32 halves, and FC4.

    Without a sweep the ladder starts at register 0. Single attempts only, and
    each finding keeps the raw response so a surprising one can be re-checked
    by hand rather than trusted.
    """
    log("\n== device rules ==")
    sweep_regs = out.get("sweep", {}).get("registers", {})
    runs = _answering_runs(sweep_regs)
    rules: dict = {}

    run_reads = []
    for first, last in runs:
        for start in range(first, last + 1, MAX_READ):
            count = min(MAX_READ, last - start + 1)
            if count < 2:
                continue
            result = client.read(start, count)
            item = {"start": start, "count": count, "status": result.status}
            if result.ok and result.words is not None:
                item["differs_from_sweep"] = _differs_from_sweep(sweep_regs, start, result.words)
            else:
                item["detail"] = result.detail
            run_reads.append(item)
    rules["run_reads"] = run_reads
    failed = [(i["start"], i["count"], i["status"]) for i in run_reads if i["status"] != OK]
    if run_reads:
        log(f"  whole-run reads: {len(run_reads) - len(failed)}/{len(run_reads)} OK"
            + (f"; failed {failed}" if failed else ""))

    if runs:
        first, last = max(runs, key=lambda r: (r[1] - r[0], -r[0]))
        ladder_start, ladder_limit = first, min(MAX_READ, last - first + 1)
    else:
        ladder_start, ladder_limit = DEFAULT_LADDER_START, MAX_READ
    counts = [c for c in BLOCK_COUNTS if c <= ladder_limit]
    if ladder_limit >= 2 and ladder_limit not in counts:
        counts.append(ladder_limit)
    ladder = []
    largest = 0
    contiguous = True  # only counts below the first failure say what is safe
    misses = 0
    for count in counts:
        result = client.read(ladder_start, count)
        step = {"count": count, "status": result.status}
        if result.ok:
            if contiguous:
                largest = count
        else:
            step["detail"] = result.detail
            contiguous = False
        ladder.append(step)
        misses = 0 if result.ok else misses + 1
        if misses >= 2:
            break
    rules["count_ladder"] = {"start": ladder_start, "reads": ladder}
    log(f"  count ladder at {ladder_start}: largest contiguous-success count = {largest}"
        f" (tested up to {counts[-1] if counts else 0})")

    gaps = []
    for kind, start, count in _gap_targets(sweep_regs):
        result = client.read(start, count)
        gaps.append({"gap_kind": kind, "start": start, "count": count, **entry(result)})
        log(f"  read across a {kind} gap {start}..{start + count - 1}: {result.status}")
    rules["across_gaps"] = gaps

    halves = {}
    for start, count in ((270, 2), (271, 1), (271, 2), (273, 1)):
        result = client.read(start, count)
        halves[f"{start}x{count}"] = entry(result)
    rules["u32_reads"] = halves
    log("  u32 halves: " + ", ".join(f"{k}={v['status']}" for k, v in halves.items()))

    fc4 = {}
    for start, count in ((0, 1), (270, 2)):
        result = client.read(start, count, fc=FC_READ_INPUT)
        fc4[f"{start}x{count}"] = entry(result)
    rules["fc4"] = fc4
    log("  FC4 (input registers): " + ", ".join(f"{k}={v['status']}" for k, v in fc4.items()))

    inconsistent = sorted({a for b in run_reads for a in b.get("differs_from_sweep", [])})
    across = {g["gap_kind"]: g["status"] for g in gaps}
    rules["summary"] = {
        "answering_runs": len(runs),
        "whole_run_reads": len(run_reads),
        "all_runs_readable": all(i["status"] == OK for i in run_reads) if run_reads else None,
        "unreadable_runs": [list(f) for f in failed],
        "ladder_start": ladder_start,
        "ladder_tested_up_to": counts[-1] if counts else None,
        "safe_read_count": largest,
        "read_across_exception_gap": across.get(EXCEPTION, "untested"),
        "read_across_silent_gap": across.get(NO_RESPONSE, "untested"),
        "u32_half_readable": halves["271x1"]["status"] == OK,
        "fc4": {OK: "supported", EXCEPTION: "unsupported"}.get(fc4["0x1"]["status"],
                                                              fc4["0x1"]["status"]),
        "block_values_match_sweep": not inconsistent,
        "inconsistent_addresses": inconsistent,
    }
    out["rules"] = rules
    if inconsistent:
        log(f"  !! block reads disagree with single reads at {inconsistent}")


# --------------------------------------------------------------------------
# stage 4: watch
# --------------------------------------------------------------------------


def stage_watch(client: Client, out: dict, minutes: float, *, tiers=WATCH_TIERS,
                log=print) -> None:
    """Poll at the integration's cadence and keep the raw time series.

    The series feeds the derived-logic tests (status >= 96 freezing counters,
    the compressor-running estimator) and gives latency and stall statistics.
    """
    log(f"\n== watch: {minutes:g} min at the integration's poll cadence ==")
    series: list[dict] = []
    failures: list[dict] = []
    out["watch"] = {"minutes": minutes,
                    "tiers": {name: {"interval_s": interval, "reads": [list(r) for r in reads]}
                              for name, interval, reads in tiers},
                    "series": series, "failures": failures}
    t0 = time.monotonic()
    end = t0 + minutes * 60
    due = {name: t0 for name, _interval, _reads in tiers}
    while time.monotonic() < end:
        now = time.monotonic()
        for name, interval, reads in tiers:
            if now < due[name]:
                continue
            row = {}
            for address, count in reads:
                result = client.read(address, count)
                t = round(time.monotonic() - t0, 2)
                series.append({"t": t, "a": address, "s": result.status, "w": result.words})
                if not result.ok:
                    failures.append({"t": t, "a": address, "s": result.status})
                row[address] = result.words[0] if result.ok and result.words else None
            while due[name] <= now:
                due[name] += interval
            if name == tiers[0][0]:
                shown = "  ".join(f"{a}={'-' if v is None else v}" for a, v in row.items())
                log(f"  t={time.monotonic() - t0:7.1f}s  {shown}")
        wake = min(min(due.values()), end)
        time.sleep(max(0.0, wake - time.monotonic()))
    out["watch"]["samples"] = len(series)
    log(f"  {len(series)} samples, {len(failures)} failed reads")


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------


def load_sweep(path: str, out: dict, log=print) -> None:
    """Take the sweep from an earlier capture of (what should be) the same unit."""
    with open(path, encoding="utf-8") as fh:
        earlier = json.load(fh)
    if "sweep" not in earlier:
        raise SystemExit(f"{path} has no sweep")
    out["sweep"] = earlier["sweep"]
    out["sweep_source"] = {"file": os.path.basename(path),
                           "captured_at": earlier.get("captured_at")}
    then = earlier.get("identity", {}).get("identify_code")
    now = out.get("identity", {}).get("identify_code")
    if then != now:
        log(f"  !! {path} was captured from identify code {then}, this unit reports {now}")
    log(f"\nusing the sweep from {path} (captured {earlier.get('captured_at')})")


def save(out: dict, path: str) -> None:
    """Atomic write, so an interrupted run never leaves half a JSON file."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


REDACTED_PATH = "/dev/ttyUSB0"   # by-id paths carry the adapter's serial number
REDACTED_HOST = "192.0.2.10"     # RFC 5737 documentation address


def _redact(text: str, path: str | None, host: str | None) -> str:
    if path:
        text = text.replace(path, REDACTED_PATH)
    text = re.sub(r"/dev/serial/by-(?:id|path)/\S+", REDACTED_PATH, text)
    if host:
        text = text.replace(host, REDACTED_HOST)
    return re.sub(r"/home/[^/\s]+/|/Users/[^/\s]+/", "~/", text)


def sanitize(src: str, dst: str) -> int:
    """Strip site-identifying details so the capture can live in the repo."""
    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)
    clean = copy.deepcopy(data)
    link = clean.get("link", {})
    path, host = link.get("path"), link.get("host")
    if "path" in link:
        link["path"] = REDACTED_PATH
    if "host" in link:
        link["host"] = REDACTED_HOST
    # The command line repeats the path or host, and may name home directories.
    clean["argv"] = [_redact(arg, path, host) for arg in clean.get("argv", [])]
    guard = clean.get("guard", {})
    guard.pop("ha_check", None)
    clean["sanitized"] = True
    save(clean, dst)
    print(f"wrote {dst}")
    return EXIT_OK


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="probe_sherpa.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--serial", metavar="PATH", help="RS-485 adapter device path")
    where.add_argument("--tcp", metavar="HOST[:PORT]", help="gateway address (port 502)")
    where.add_argument("--sanitize", nargs=2, metavar=("IN", "OUT"),
                       help="redact a capture for use as a test fixture, then exit")
    ap.add_argument("--rtu-over-tcp", action="store_true",
                    help="with --tcp: the server passes raw RTU frames (no MBAP header)")
    ap.add_argument("--slave", type=int, default=201, help="Modbus address, ADDR247 (201)")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--framing", default="8N1", help="8N1, 8E1, 8O1 or 8N2")
    ap.add_argument("--timeout", type=float, default=3.0, help="response timeout, seconds")
    ap.add_argument("--gap-ms", type=float, default=60.0,
                    help="quiet time between frames; the unit needs about 60 ms")
    ap.add_argument("--resync-seconds", type=float, default=1.0,
                    help="pause after a failed exchange before the buffer is discarded")
    ap.add_argument("--stages", default="sweep,rules",
                    help="comma list from sweep,rules,watch (identity always runs)")
    ap.add_argument("--sweep-from", metavar="CAPTURE",
                    help="reuse the sweep of an earlier capture, so --stages rules can run "
                         "without re-sweeping (shorter downtime)")
    ap.add_argument("--first", type=int, default=0, help="first register to sweep")
    ap.add_argument("--last", type=int, default=999, help="last register to sweep")
    ap.add_argument("--sweep-timeout", type=float, default=1.0,
                    help="per-register timeout during the sweep")
    ap.add_argument("--stall-limit", type=float, default=120.0,
                    help="give up when the link stays silent this long, seconds")
    ap.add_argument("--watch-minutes", type=float, default=0.0,
                    help="poll at the integration's cadence this long (adds the watch stage)")
    ap.add_argument("--listen-seconds", type=float, default=15.0,
                    help="silence required on the bus before the first request")
    ap.add_argument("--i-stopped-home-assistant", action="store_true",
                    help="confirm nothing else is polling this bus")
    ap.add_argument("--ha-check", default="127.0.0.1:8123",
                    help="refuse a serial run while this address answers (Home Assistant)")
    ap.add_argument("--no-ha-check", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="continue past an unexpected identify code")
    ap.add_argument("--out", default=None,
                    help="capture file (default: sherpa_observed_<UTC timestamp>.json)")
    ap.add_argument("--overwrite", action="store_true",
                    help="allow --out to replace an existing file")
    return ap


def parse_args(argv=None) -> argparse.Namespace:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.sanitize:
        return args
    if not args.serial and not args.tcp:
        ap.error("one of --serial, --tcp or --sanitize is required")
    if args.rtu_over_tcp and not args.tcp:
        ap.error("--rtu-over-tcp needs --tcp")
    if not 1 <= args.slave <= 247:
        ap.error("--slave must be 1..247")
    if not 0 <= args.first <= args.last <= 0xFFFF:
        ap.error("need 0 <= --first <= --last <= 65535")
    stages = {s.strip() for s in args.stages.split(",") if s.strip()}
    unknown = stages - {"sweep", "rules", "watch"}
    if unknown:
        ap.error(f"unknown stage(s): {', '.join(sorted(unknown))}")
    if args.watch_minutes > 0:
        stages.add("watch")
    elif "watch" in stages:
        ap.error("the watch stage needs --watch-minutes")
    args.stage_set = stages
    if args.sweep_from:
        if "sweep" in stages:
            ap.error("--sweep-from replaces the sweep stage; drop 'sweep' from --stages")
        if not os.path.exists(args.sweep_from):
            ap.error(f"{args.sweep_from} does not exist")
    if args.out is None:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        args.out = f"sherpa_observed_{stamp}.json"
    elif os.path.exists(args.out) and not args.overwrite:
        # A capture costs Home Assistant downtime; never clobber one by accident.
        ap.error(f"{args.out} exists; pass --overwrite or choose another --out")
    try:
        parse_framing(args.framing)
    except ValueError as exc:
        ap.error(str(exc))
    return args


def make_link(args):
    if args.serial:
        return SerialLink(args.serial, args.baud, args.framing)
    host, port = split_hostport(args.tcp, 502)
    return TcpLink(host, port, "rtu" if args.rtu_over_tcp else "mbap")


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.sanitize:
        return sanitize(*args.sanitize)

    link = make_link(args)
    client = Client(link, args.slave, timeout=args.timeout, gap_ms=args.gap_ms,
                    resync_s=args.resync_seconds)
    out: dict = {
        "probe_version": PROBE_VERSION,
        "captured_at": now_iso(),
        "link": {**link.describe(), "slave": args.slave, "timeout_s": args.timeout,
                 "gap_ms": args.gap_ms},
        "stages": ["identity", *sorted(args.stage_set)],
        "argv": sys.argv[1:] if argv is None else list(argv),
    }

    rc = preflight(args, link.kind, out)
    if rc:
        return rc
    try:
        link.open()
    except OSError as exc:
        print(f"cannot open {link.describe()}: {exc}", file=sys.stderr)
        return EXIT_LINK
    out["link"].update(link.describe())

    rc = EXIT_OK
    try:
        rc = listen_before_talk(link, args.listen_seconds, out)
        if rc == EXIT_OK:
            rc = stage_identity(client, out, force=args.force)
            save(out, args.out)
        if rc == EXIT_OK and args.sweep_from:
            load_sweep(args.sweep_from, out)
        if rc == EXIT_OK and "sweep" in args.stage_set:
            stage_sweep(client, out, args.first, args.last, timeout=args.sweep_timeout,
                        stall_limit_s=args.stall_limit)
            save(out, args.out)
        if rc == EXIT_OK and "rules" in args.stage_set:
            stage_rules(client, out)
            save(out, args.out)
        if rc == EXIT_OK and "watch" in args.stage_set:
            stage_watch(client, out, args.watch_minutes)
    except KeyboardInterrupt:
        out["aborted"] = "interrupted"
        print("\ninterrupted; saving what was captured", file=sys.stderr)
        rc = EXIT_INTERRUPTED
    except LinkDropped as exc:  # only the listen stage reads the link directly
        out["aborted"] = f"link dropped: {exc}"
        print(f"link dropped: {exc}", file=sys.stderr)
        rc = EXIT_LINK
    finally:
        link.close()
        out["finished_at"] = now_iso()
        out["timing"] = client.stats.summary()
        save(out, args.out)
    timing = out["timing"]
    print(f"\n{timing['requests']} requests {timing['by_status']}; latency p50 "
          f"{timing['latency_ms']['p50']} ms, p95 {timing['latency_ms']['p95']} ms")
    print(f"wrote {args.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
