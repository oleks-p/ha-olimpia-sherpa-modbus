"""Home Assistant fixtures: the integration against a fake reference unit.

The fake is built from the probe's capture of the real unit -- the same 284
answering registers, the same "a read across a gap is refused" rule -- so the
block planner, the decoders and the entity set are exercised against what the
hardware actually does, not against what the code assumes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from pymodbus.exceptions import ConnectionException, ModbusIOException
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.olimpia_sherpa_modbus.const import (
    CONF_BAUDRATE,
    CONF_ENTITY_PREFIX,
    CONF_SERIAL_PORT,
    CONF_SLAVE,
    CONF_TRANSPORT,
    DOMAIN,
    TRANSPORT_SERIAL,
)
from tests.sim import FakeSherpa

CAPTURE = Path(__file__).parents[1] / "fixtures" / "sherpa_s2_big_14t_fw057.json"
TRANSPORT = "custom_components.olimpia_sherpa_modbus.transport"

SERIAL_DATA = {
    CONF_TRANSPORT: TRANSPORT_SERIAL,
    CONF_SERIAL_PORT: "/dev/ttyUSB0",
    CONF_BAUDRATE: 9600,
    CONF_SLAVE: 201,
    CONF_ENTITY_PREFIX: "sherpa",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


class FakeResponse:
    def __init__(self, registers: list[int] | None = None, code: int | None = None) -> None:
        self.registers = registers or []
        self.exception_code = code

    def isError(self) -> bool:  # noqa: N802 - pymodbus spelling
        return self.exception_code is not None


class FakeModbusClient:
    """The slice of pymodbus the transport uses, answering from a FakeSherpa."""

    def __init__(self, fake: FakeSherpa, *args, **kwargs) -> None:
        self.fake = fake
        self.args, self.kwargs = args, kwargs
        self.connected = False
        self.closes = 0

    async def connect(self) -> bool:
        if getattr(self.fake, "offline", False):
            return False
        self.connected = True
        return True

    def close(self) -> None:
        self.connected = False
        self.closes += 1

    async def read_holding_registers(self, address, *, count=1, device_id=1,
                                     no_response_expected=False):
        if not self.connected:
            raise ConnectionException("not connected")
        result = self.fake.read(device_id, 3, address, count)
        if result is None:
            raise ModbusIOException("no response")
        if isinstance(result, int):
            return FakeResponse(code=result)
        return FakeResponse(registers=result)


@pytest.fixture
def fake() -> FakeSherpa:
    return FakeSherpa.from_capture(CAPTURE)


@pytest.fixture
def modbus_clients(fake):
    """Every pymodbus client the integration creates, in order."""
    clients: list[FakeModbusClient] = []

    def factory(*args, **kwargs):
        client = FakeModbusClient(fake, *args, **kwargs)
        clients.append(client)
        return client

    with (
        patch(f"{TRANSPORT}.AsyncModbusSerialClient", side_effect=factory),
        patch(f"{TRANSPORT}.AsyncModbusTcpClient", side_effect=factory),
        patch(f"{TRANSPORT}.FRAME_GAP", 0),
        patch(f"{TRANSPORT}.RESYNC_DELAY", 0),
    ):
        yield clients


@pytest.fixture
def config_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SHERPA S2 BIG / SHERPA S2 14T",
        unique_id="serial:/dev/ttyUSB0#201",
        data=dict(SERIAL_DATA),
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_integration(hass, config_entry, modbus_clients, freezer):
    # The clock is frozen before the first poll, so the coordinator's tier and
    # outage timing (time.monotonic) and the tests' time travel share one clock.
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
