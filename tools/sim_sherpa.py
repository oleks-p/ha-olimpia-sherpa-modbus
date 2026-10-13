#!/usr/bin/env python3
"""A simulated Sherpa on an RS-485 line, for tests and for a dev Home Assistant.

``FakeSherpa`` answers Modbus requests from a register map and can misbehave on
demand: stalls, corrupted CRCs, late replies, silent addresses. The servers put
it behind a real byte stream. ``PtyServer`` uses a pseudo-terminal, so the
probe's termios code runs exactly as it does against a USB adapter.
``TcpServer`` uses a socket in either MBAP or raw-RTU framing.

Serve the reference unit's capture to a dev Home Assistant (no hardware):

    python3 tools/sim_sherpa.py --capture tests/fixtures/sherpa_s2_big_14t_fw057.json \
        --listen 0.0.0.0:5020 --framer rtu

then add the integration with transport "RTU over TCP", host = this machine,
port 5020, address 201.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import select
import socket
import struct
import threading
import time
import tty

try:
    import probe_sherpa as probe  # tools/ on sys.path (tests, or run from tools/)
except ImportError:                # run as tools/sim_sherpa.py from the repo root
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import probe_sherpa as probe


def _w(value: int) -> int:
    return value & 0xFFFF


def reference_registers() -> dict[int, int]:
    """Raw words modelled on the reference unit (its display and live reads)."""
    regs: dict[int, int] = {
        0: 260, 1: 251, 2: 221, 3: 110,              # T1-T4, x0.1 degC
        4: _w(-1), 5: _w(-1), 6: _w(-501), 7: _w(-501),  # absent probes
        8: 895, 9: 0, 10: 0, 11: 0, 12: 2,
        99: 0, 100: 0, 101: 0, 102: 0, 103: 0, 104: 0, 105: 0x0011, 106: 0,
        193: 0, 197: 57, 198: 57, 199: 1134,
    }
    service = {
        200: 0, 206: 150, 207: 180, 208: 350, 209: 300, 210: 500, 211: 1, 212: 1, 213: 750,
        217: 1, 219: 20, 220: 0, 221: 1, 222: 72, 223: 30, 224: 0, 225: 0, 226: 0, 227: 20,
        228: 2, 229: 2, 230: 0, 231: 60, 232: 650, 233: 30, 234: 0, 235: 15, 236: 30, 237: 0,
        238: 100, 239: 200, 240: 180, 241: 400, 242: 150, 243: _w(-50), 244: 350, 245: 200,
        246: 300, 247: 201, 248: 400, 249: 2, 250: 1, 251: 72, 252: 30, 253: 50, 254: 100,
        255: 350, 256: 2, 257: 0, 258: 0, 259: 0, 260: 10, 261: 30, 262: 20,
        263: 0, 266: 0, 269: 0,
        270: 0, 271: 24517, 272: 1, 273: 52170, 274: 1, 275: 52170,
        276: 0, 277: 0, 278: 0, 279: 0, 280: 1300, 281: 0, 285: 60,
        291: 0, 292: 1, 293: 12, 294: 34, 295: 56, 296: 0, 334: 0, 341: 0,
        347: _w(-20), 348: 50, 349: 100, 366: 0, 367: 0, 368: 0, 369: 0,
        370: 2, 371: 14, 372: 1, 388: 1, 401: 1,
    }
    regs.update(service)
    regs.update({a: 0 for a in range(201, 206)})
    regs.update({a: 0 for a in range(297, 327)})
    regs.update({a: 75 for a in range(321, 327)})
    regs.update({a: 0 for a in range(343, 347)})
    regs.update({a: 0 for a in range(350, 366)})
    regs.update(dict(zip(range(380, 388), (5, 20, 30, 50, 60, 70, 70, 70), strict=True)))
    regs.update({561 + i: min(24 + 2 * i, 78) for i in range(32)})
    regs.update({593 + i: min(24 + 3 * i, 92) for i in range(32)})
    return regs


class FakeSherpa:
    """A Modbus slave with the Sherpa's register map and configurable quirks."""

    def __init__(self, registers: dict[int, int] | None = None, slave: int = 201, *,
                 undefined: str = "exception", max_count: int = 125,
                 atomic_u32: tuple[int, ...] = (), fc4: str = "exception"):
        self.registers = dict(reference_registers() if registers is None else registers)
        self.slave = slave
        self.undefined = undefined      # "exception" | "silent" | "zero"
        self.max_count = max_count
        self.atomic_u32 = set(atomic_u32)
        self.fc4 = fc4                  # "exception" | "mirror"
        self.silent: set[int] = set()
        self.requests: list[tuple[int, int, int, int]] = []
        self._lock = threading.Lock()
        self._stall_left = 0
        self._stall_on: dict[int, int] = {}
        self._corrupt_left = 0
        self._delay_next = 0.0
        #: How the unit treats an FC6 write, per address: "accept" (default for
        #: an address it has), "refuse" (exception 2), "ignore" (acknowledged,
        #: not applied) or "revert" (applied, then the controller puts its own
        #: value back after one more read).
        self.write_mode: dict[int, str] = {}
        self.writes: list[tuple[int, int]] = []
        self._revert: dict[int, tuple[int, int]] = {}

    # -- fault injection ----------------------------------------------------

    def stall(self, requests: int) -> None:
        """Ignore the next ``requests`` requests, as the bus does during a stall."""
        with self._lock:
            self._stall_left = requests

    def stall_on(self, address: int, requests: int) -> None:
        """Start a stall the first time ``address`` is requested."""
        with self._lock:
            self._stall_on[address] = requests

    def corrupt(self, replies: int = 1) -> None:
        with self._lock:
            self._corrupt_left = replies

    def delay(self, seconds: float) -> None:
        with self._lock:
            self._delay_next = seconds

    def take_faults(self) -> tuple[float, bool]:
        with self._lock:
            delay, self._delay_next = self._delay_next, 0.0
            corrupt = self._corrupt_left > 0
            if corrupt:
                self._corrupt_left -= 1
        return delay, corrupt

    @classmethod
    def from_capture(cls, path: str | os.PathLike, **kwargs) -> FakeSherpa:
        """A fake with exactly the registers a probe capture found answering."""
        with open(path, encoding="utf-8") as fh:
            sweep = json.load(fh)["sweep"]["registers"]
        answering = {int(a): v["raw"] for a, v in sweep.items() if v["status"] == "OK"}
        return cls(answering, **kwargs)

    @property
    def write_requests(self) -> list[tuple[int, int, int, int]]:
        return [r for r in self.requests if r[1] not in probe.ALLOWED_FUNCTION_CODES]

    # -- protocol -----------------------------------------------------------

    def read(self, unit: int, fc: int, address: int, count: int) -> list[int] | int | None:
        """Registers, a Modbus exception code, or None for silence.

        The single source of the device's rules. ``respond`` wraps it in PDUs
        for the byte-stream servers; the integration tests' fake pymodbus
        client calls it directly.
        """
        with self._lock:
            self.requests.append((unit, fc, address, count))
            if address in self._stall_on:
                self._stall_left = self._stall_on.pop(address)
            if self._stall_left > 0:
                self._stall_left -= 1
                return None
        if unit != self.slave:
            return None
        if fc not in probe.ALLOWED_FUNCTION_CODES:
            return 1
        if fc == probe.FC_READ_INPUT and self.fc4 == "exception":
            return 1
        if not 1 <= count <= 125 or count > self.max_count:
            return 3
        span = range(address, address + count)
        if any(a in self.silent for a in span):
            return None
        self._settle(span)
        for first in self.atomic_u32:
            if (first in span) != (first + 1 in span):
                return 2
        words = []
        for a in span:
            if a in self.registers:
                words.append(self.registers[a])
            elif self.undefined == "zero":
                words.append(0)
            elif self.undefined == "silent":
                return None
            else:
                return 2
        return words

    def write(self, unit: int, address: int, value: int) -> int | bool | None:
        """FC6: True when acknowledged, an exception code, or None for silence."""
        with self._lock:
            self.requests.append((unit, 6, address, 1))
            if self._stall_left > 0:
                self._stall_left -= 1
                return None
        if unit != self.slave:
            return None
        mode = self.write_mode.get(address, "accept" if address in self.registers else "refuse")
        if mode == "refuse":
            return 2
        self.writes.append((address, value))
        if mode == "accept":
            self.registers[address] = value
        elif mode == "revert":
            self._revert[address] = (self.registers[address], 1)
            self.registers[address] = value
        return True

    def _settle(self, span: range) -> None:
        """Run any pending revert: the controller restoring its own value."""
        for address in span:
            if address in self._revert:
                original, reads_left = self._revert[address]
                if reads_left > 0:
                    self._revert[address] = (original, reads_left - 1)
                else:
                    self.registers[address] = original
                    del self._revert[address]

    def respond(self, unit: int, pdu: bytes) -> bytes | None:
        """Response PDU for a request PDU, or None for silence."""
        fc = pdu[0]
        address, count = struct.unpack(">HH", pdu[1:5])
        if fc == 6:
            outcome = self.write(unit, address, count)   # for FC6 the second word is the value
            if outcome is None:
                return None
            if outcome is True:
                return pdu[:5]                           # FC6 echoes the request
            return bytes([fc | 0x80, outcome])
        result = self.read(unit, fc, address, count)
        if result is None:
            return None
        if isinstance(result, int):
            return bytes([fc | 0x80, result])
        return bytes([fc, 2 * count]) + struct.pack(f">{count}H", *result)


def rtu_frame(slave: int, pdu: bytes) -> bytes:
    frame = bytes([slave]) + pdu
    return frame + probe.crc16(frame)


def _request_length(buf: bytes) -> int | None:
    if len(buf) < 2:
        return None
    if buf[1] in (15, 16):
        return 9 + buf[6] if len(buf) >= 7 else None
    return 8


class _RtuEndpoint:
    """Shared RTU request handling for the pty and raw-TCP servers."""

    def __init__(self, fake: FakeSherpa, echo: bool = False):
        self.fake, self.echo = fake, echo

    def handle(self, buf: bytes, send) -> bytes:
        while (n := _request_length(buf)) is not None and len(buf) >= n:
            frame, buf = buf[:n], buf[n:]
            if probe.crc16(frame[:-2]) != frame[-2:]:
                continue
            if self.echo:
                send(frame)
            reply = self.fake.respond(frame[0], frame[1:-2])
            if reply is None:
                continue
            out = rtu_frame(frame[0], reply)
            delay, corrupt = self.fake.take_faults()
            if corrupt:
                out = out[:-1] + bytes([out[-1] ^ 0xFF])
            if delay:
                time.sleep(delay)
            send(out)
        return buf


class PtyServer(_RtuEndpoint):
    """The fake behind a pseudo-terminal; ``path`` is what the probe opens."""

    # Another master polling register 0 of slave 201.
    CHATTER = rtu_frame(201, struct.pack(">BHH", 3, 0, 1))

    def __init__(self, fake: FakeSherpa, *, echo: bool = False, chatter: bool = False):
        super().__init__(fake, echo)
        self.chatter = chatter
        self.master, self._slave_fd = os.openpty()
        tty.setraw(self._slave_fd)  # no echo or line editing before the probe opens it
        self.path = os.ttyname(self._slave_fd)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _send(self, data: bytes) -> None:
        os.write(self.master, data)

    def _run(self) -> None:
        buf = b""
        last_chatter = 0.0
        while not self._stop.is_set():
            if self.chatter and time.monotonic() - last_chatter > 0.2:
                self._send(self.CHATTER)
                last_chatter = time.monotonic()
            readable, _w, _x = select.select([self.master], [], [], 0.05)
            if not readable:
                continue
            try:
                data = os.read(self.master, 512)
            except OSError:
                return
            if self.chatter:
                continue  # a real second master would collide; just keep talking
            buf = self.handle(buf + data, self._send)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        for fd in (self.master, self._slave_fd):
            with contextlib.suppress(OSError):
                os.close(fd)


class TcpServer(_RtuEndpoint):
    """The fake behind a TCP socket, as a Modbus-TCP gateway or a raw RTU server."""

    def __init__(self, fake: FakeSherpa, framer: str = "mbap", *, echo: bool = False,
                 bind: tuple[str, int] = ("127.0.0.1", 0)):
        super().__init__(fake, echo)
        self.framer = framer
        self.sock = socket.create_server(bind)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def _accept(self) -> None:
        self.sock.settimeout(0.1)
        while not self._stop.is_set():
            try:
                conn, _addr = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            worker = threading.Thread(target=self._serve, args=(conn,), daemon=True)
            self._workers.append(worker)
            worker.start()

    def _serve(self, conn: socket.socket) -> None:
        buf = b""
        with conn:
            conn.settimeout(0.1)
            while not self._stop.is_set():
                try:
                    data = conn.recv(512)
                except TimeoutError:
                    continue
                except OSError:
                    return
                if not data:
                    return
                buf += data
                if self.framer == "rtu":
                    buf = self.handle(buf, conn.sendall)
                    continue
                while len(buf) >= 7:
                    tid, _pid, length, unit = struct.unpack(">HHHB", buf[:7])
                    if len(buf) < 6 + length:
                        break
                    pdu, buf = buf[7:6 + length], buf[6 + length:]
                    reply = self.fake.respond(unit, pdu)
                    if reply is None:
                        continue
                    delay, _corrupt = self.fake.take_faults()
                    if delay:
                        time.sleep(delay)
                    conn.sendall(struct.pack(">HHHB", tid, 0, len(reply) + 1, unit) + reply)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        for worker in self._workers:
            worker.join(timeout=2)
        with contextlib.suppress(OSError):
            self.sock.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture", required=True, help="probe capture to serve")
    ap.add_argument("--listen", default="127.0.0.1:5020", help="HOST:PORT")
    ap.add_argument("--framer", choices=("rtu", "mbap"), default="rtu",
                    help="rtu: transparent serial server; mbap: Modbus-TCP gateway")
    ap.add_argument("--slave", type=int, default=201)
    ap.add_argument("--write-mode", action="append", default=[], metavar="ADDR=MODE",
                    help="how FC6 to ADDR is treated: accept, refuse, ignore or revert "
                         "(repeatable; default accept)")
    args = ap.parse_args(argv)
    host, _, port = args.listen.rpartition(":")
    fake = FakeSherpa.from_capture(args.capture, slave=args.slave)
    for item in args.write_mode:
        address, _, mode = item.partition("=")
        if mode not in ("accept", "refuse", "ignore", "revert") or not address.isdigit():
            ap.error(f"--write-mode {item!r}: expected ADDR=accept|refuse|ignore|revert")
        fake.write_mode[int(address)] = mode
    server = TcpServer(fake, args.framer, bind=(host or "127.0.0.1", int(port)))
    print(f"serving {len(fake.registers)} registers as slave {args.slave} on "
          f"{host}:{server.port} ({args.framer}); Ctrl-C to stop")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
