"""The bundled Lovelace cards: served, registered once, never in the way."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.olimpia_sherpa_modbus import cards

ROOT = Path(__file__).parents[2]


class FakeResources:
    """Lovelace's resource collection, as far as the registration touches it."""

    def __init__(self, items=()):
        self.loaded = True
        self.items = [dict(item) for item in items]

    def async_items(self):
        return list(self.items)

    async def async_create_item(self, data):
        self.items.append({"id": f"r{len(self.items)}", **data})

    async def async_update_item(self, item_id, data):
        for item in self.items:
            if item["id"] == item_id:
                item.update(data)


@pytest.fixture
def served(hass):
    """http's static-path registration, without starting a server."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    return hass.http.async_register_static_paths


def _lovelace(hass, resources, mode="storage"):
    from homeassistant.components.lovelace import LOVELACE_DATA

    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=resources, resource_mode=mode)


async def test_the_bundle_is_served_and_listed(hass, served):
    resources = FakeResources()
    _lovelace(hass, resources)
    await cards.async_register_cards(hass, "0.5.0")
    (config,), _ = served.call_args
    assert config[0].url_path == "/olimpia_sherpa_modbus/sherpa-cards.js"
    assert Path(config[0].path) == cards.BUNDLE
    assert [r["url"] for r in resources.items] == ["/olimpia_sherpa_modbus/sherpa-cards.js?v=0.5.0"]
    assert resources.items[0]["res_type"] == "module"


async def test_an_older_release_is_repointed_not_duplicated(hass, served):
    resources = FakeResources([{"id": "a", "url": "/olimpia_sherpa_modbus/sherpa-cards.js?v=0.4.0",
                                "res_type": "module"},
                               {"id": "b", "url": "/hacsfiles/other-card.js", "res_type": "module"}])
    _lovelace(hass, resources)
    await cards.async_register_cards(hass, "0.5.0")
    assert [r["url"] for r in resources.items] == [
        "/olimpia_sherpa_modbus/sherpa-cards.js?v=0.5.0", "/hacsfiles/other-card.js"]


async def test_registration_happens_once(hass, served):
    resources = FakeResources()
    _lovelace(hass, resources)
    await cards.async_register_cards(hass, "0.5.0")
    await cards.async_register_cards(hass, "0.5.0")       # a second entry
    assert served.call_count == 1 and len(resources.items) == 1


async def test_yaml_dashboards_are_left_alone(hass, served, caplog):
    resources = FakeResources()
    _lovelace(hass, resources, mode="yaml")
    await cards.async_register_cards(hass, "0.5.0")
    assert resources.items == []
    assert "add the Sherpa cards yourself" in caplog.text


async def test_setup_survives_the_cards_raising(hass, config_entry, modbus_clients, freezer):
    with patch("custom_components.olimpia_sherpa_modbus.async_register_cards",
               side_effect=RuntimeError("boom")):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert hass.states.get("climate.sherpa_heat_pump").state == "off"
    assert hass.states.get("sensor.sherpa_water_in").state == "25.8"


def test_the_bundle_defines_both_cards():
    bundle = cards.BUNDLE.read_text()
    assert bundle.startswith("/* Olimpia Splendid Sherpa Lovelace cards")
    for card in ("sherpa-schematic-card", "sherpa-control-card"):
        assert card in bundle


def test_the_cards_bind_only_entities_the_release_creates():
    """The id table in cards/src/shared.ts, against entities.json."""
    source = (ROOT / "cards" / "src" / "shared.ts").read_text()
    table = source[source.index("export function ids("):source.index("export type Ids")]
    bound = {f"sensor.{k}" for k in re.findall(r"\bs\('([a-z0-9_]+)'\)", table)}
    bound |= {f"binary_sensor.{k}" for k in re.findall(r"\bb\('([a-z0-9_]+)'\)", table)}
    bound |= {f"climate.{k}" for k in re.findall(r"climate\.\$\{prefix\}_([a-z0-9_]+)", table)}
    # the writable twins the control card looks for
    control = (ROOT / "cards" / "src" / "control-card.ts").read_text()
    bound |= {f"number.{k}" for k in re.findall(r"key: '([a-z_]+_setpoint)'", control)}
    manifest = json.loads((ROOT / "entities.json").read_text())
    provided = {f"{e['domain']}.{e['key']}" for e in manifest["entities"]}
    assert len(bound) > 25
    assert not bound - provided, sorted(bound - provided)
