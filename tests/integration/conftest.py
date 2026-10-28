"""Home Assistant fixtures: the integration against a fake reference unit.

The fake is built from the probe's capture of the real unit -- the same 284
answering registers, the same "a read across a gap is refused" rule -- so the
block planner, the decoders and the entity set are exercised against what the
hardware actually does, not against what the code assumes.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.util import dt as dt_util
from pymodbus.exceptions import ConnectionException, ModbusIOException
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.olimpia_sherpa_modbus.const import (
    CONF_ALLOW_WRITES,
    CONF_BAUDRATE,
    CONF_ENTITY_PREFIX,
    CONF_MODE_CONTROL,
    CONF_SERIAL_PORT,
    CONF_SLAVE,
    CONF_TRANSPORT,
    DOMAIN,
    TRANSPORT_SERIAL,
)
from custom_components.olimpia_sherpa_modbus.registers import FORBIDDEN_WRITES
from tests.sim import FakeSherpa, ModeModel

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

    async def write_register(self, address, value, *, device_id=1, no_response_expected=False):
        if not self.connected:
            raise ConnectionException("not connected")
        outcome = self.fake.write(device_id, address, value)
        if outcome is None:
            raise ModbusIOException("no response")
        if outcome is True:
            return FakeResponse(registers=[value])
        return FakeResponse(code=outcome)


@pytest.fixture
def fake() -> FakeSherpa:
    fake = FakeSherpa.from_capture(CAPTURE)
    yield fake
    # No test may ever make the integration write a forbidden register -- ADDR220
    # above all: only a person sets it, on the panel.
    assert not {a for a, _ in fake.writes} & FORBIDDEN_WRITES, fake.writes


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
        # the write check's hold: the fake reverts on its next read, not on a timer
        patch("custom_components.olimpia_sherpa_modbus.writes._wait", AsyncMock()),
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


@pytest.fixture
def advance(hass, freezer):
    """Move time forward in 10 s steps, letting each poll and mode tick complete."""

    async def run(seconds: float) -> None:
        remaining = seconds
        while remaining > 0:
            step = min(10, remaining)
            freezer.tick(timedelta(seconds=step))
            async_fire_time_changed(hass, dt_util.utcnow())
            await hass.async_block_till_done()
            remaining -= step

    return run


@pytest.fixture
def mode_unit(fake):
    """The fake with the P6 behaviour: 106 and ADDR220 move status, E09 comes at 255 s.
    The clock is looked up at call time, so the tests' frozen clock is the one used."""
    import time

    fake.mode_model = ModeModel(lambda: time.monotonic())
    return fake


@pytest.fixture
async def with_mode_control(hass, config_entry, modbus_clients, freezer):
    """Allow writes + Mode control on, set before the integration is.

    Unloads the entry at the end, while the fake link is still patched in: the
    controller's last write (at unload and at Home Assistant stop) would otherwise
    go to a real serial port and wait out its timeout.
    """
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_ALLOW_WRITES: True, CONF_MODE_CONTROL: True})
    yield config_entry
    if config_entry.state is ConfigEntryState.LOADED:
        await hass.config_entries.async_unload(config_entry.entry_id)
