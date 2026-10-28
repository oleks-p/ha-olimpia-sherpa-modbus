"""The transport against real pymodbus clients and a simulated unit on the wire.

Everything else in the suite uses a fake pymodbus client. These tests use the
real one: over TCP (MBAP and raw RTU) against the simulator's socket server,
and over a pseudo-terminal with pymodbus's serial client -- the code path that
talks to a USB adapter on the Home Assistant host.
"""

from __future__ import annotations

import time

import pytest

from custom_components.olimpia_sherpa_modbus.const import (
    TRANSPORT_RTU_OVER_TCP,
    TRANSPORT_SERIAL,
    TRANSPORT_TCP,
)
from custom_components.olimpia_sherpa_modbus.transport import (
    BusRegistry,
    Endpoint,
    SherpaBus,
    SherpaIllegalError,
    SherpaTransientError,
)
from tests.integration.conftest import CAPTURE
from tests.sim import FakeSherpa, PtyServer, TcpServer


@pytest.fixture
def unit() -> FakeSherpa:
    return FakeSherpa.from_capture(CAPTURE)


@pytest.fixture
def tcp_server(socket_enabled, unit, request):
    server = TcpServer(unit, request.param)
    yield server
    server.close()


@pytest.fixture
def pty_server(unit):
    server = PtyServer(unit)
    yield server
    server.close()


def _tcp_endpoint(server: TcpServer) -> Endpoint:
    transport = TRANSPORT_RTU_OVER_TCP if server.framer == "rtu" else TRANSPORT_TCP
    return Endpoint(transport, host="127.0.0.1", port=server.port)


@pytest.mark.parametrize("tcp_server", ["rtu", "mbap"], indirect=True)
async def test_reads_over_tcp(tcp_server):
    bus = SherpaBus(_tcp_endpoint(tcp_server), timeout=1.0, gap=0, resync=0)
    try:
        assert await bus.read(201, 0, 4) == [258, 251, 221, 132]
        assert await bus.read(201, 270, 2) == [2, 1886]   # 132958 s, high word first
        assert await bus.read(201, 217, 65)      # the longest run, whole
    finally:
        await bus.close()


@pytest.mark.parametrize("tcp_server", ["rtu", "mbap"], indirect=True)
async def test_a_gap_is_refused_not_a_link_failure(tcp_server):
    bus = SherpaBus(_tcp_endpoint(tcp_server), timeout=1.0, gap=0, resync=0)
    try:
        with pytest.raises(SherpaIllegalError) as err:
            await bus.read(201, 9, 4)            # 10-11 do not exist
        assert err.value.code == 2
        assert await bus.read(201, 12, 1) == [0]  # and the link is fine
        assert bus.failures == 0
    finally:
        await bus.close()


@pytest.mark.parametrize("tcp_server", ["rtu"], indirect=True)
async def test_silence_is_transient_and_the_next_read_reconnects(tcp_server, unit):
    bus = SherpaBus(_tcp_endpoint(tcp_server), timeout=0.3, gap=0, resync=0.05)
    try:
        unit.stall(1)
        with pytest.raises(SherpaTransientError):
            await bus.read(201, 0, 1)
        assert await bus.read(201, 1, 1) == [251]   # the right register, not a late reply
        assert bus.failures == 1
    finally:
        await bus.close()


@pytest.mark.parametrize("tcp_server", ["mbap"], indirect=True)
async def test_frames_keep_the_units_quiet_gap(tcp_server):
    bus = SherpaBus(_tcp_endpoint(tcp_server), timeout=1.0, gap=0.1, resync=0)
    try:
        await bus.read(201, 0, 1)
        started = time.monotonic()
        for _ in range(3):
            await bus.read(201, 0, 1)
        assert time.monotonic() - started >= 0.3
    finally:
        await bus.close()


async def test_reads_over_a_serial_port(pty_server):
    bus = SherpaBus(Endpoint(TRANSPORT_SERIAL, serial_port=pty_server.path),
                    timeout=1.0, gap=0, resync=0)
    try:
        assert await bus.read(201, 197, 3) == [57, 57, 1134]
        assert await bus.read(201, 370, 2) == [2, 14]
    finally:
        await bus.close()


@pytest.mark.parametrize("tcp_server", ["rtu", "mbap"], indirect=True)
async def test_writes_over_tcp(tcp_server, unit):
    bus = SherpaBus(_tcp_endpoint(tcp_server), timeout=1.0, gap=0, resync=0)
    try:
        await bus.write(201, 208, 355)                     # FC6, echoed
        assert unit.registers[208] == 355 and await bus.read(201, 208, 1) == [355]
        unit.write_mode[207] = "refuse"
        with pytest.raises(SherpaIllegalError) as err:
            await bus.write(201, 207, 185)
        assert err.value.code == 2 and unit.registers[207] == 180
        assert str(err.value) == "write 207=185 refused with exception 2"
        assert bus.failures == 0                           # a refusal is not a link failure
        unit.write_mode[209] = "ignore"
        await bus.write(201, 209, 305)                     # acknowledged...
        assert await bus.read(201, 209, 1) == [300]        # ...and not applied
    finally:
        await bus.close()


async def test_writes_over_a_serial_port(pty_server, unit):
    bus = SherpaBus(Endpoint(TRANSPORT_SERIAL, serial_port=pty_server.path),
                    timeout=1.0, gap=0, resync=0)
    try:
        await bus.write(201, 210, 505)
        assert unit.registers[210] == 505 and await bus.read(201, 210, 1) == [505]
    finally:
        await bus.close()


@pytest.mark.parametrize("tcp_server", ["rtu"], indirect=True)
@pytest.mark.parametrize("address", [220, 229, 247, 401, 300, 280])
async def test_a_forbidden_register_is_never_written_whatever_the_caller(
        tcp_server, unit, address):
    """Defense in depth: ADDR220 above all. Refused before any request is sent."""
    bus = SherpaBus(_tcp_endpoint(tcp_server), timeout=1.0, gap=0, resync=0)
    try:
        with pytest.raises(ValueError, match="never written"):
            await bus.write(201, address, 1)
        assert bus.requests == 0 and unit.writes == [] and unit.write_requests == []
    finally:
        await bus.close()


async def test_entries_on_one_link_share_one_bus():
    closed = []

    class Recording(SherpaBus):
        async def close(self) -> None:
            closed.append(self.endpoint.key)

    registry = BusRegistry(Recording)
    port = Endpoint(TRANSPORT_SERIAL, serial_port="/dev/ttyUSB0")
    first, second = registry.acquire(port), registry.acquire(port)
    assert first is second
    other = registry.acquire(Endpoint(TRANSPORT_TCP, host="192.0.2.1"))
    assert other is not first
    await registry.release(port)
    assert closed == [] and registry.in_use(port)       # still one user
    await registry.release(port)
    assert closed == ["serial:/dev/ttyUSB0"] and not registry.in_use(port)
