"""Serve the bundled Lovelace cards and register them with the frontend.

The cards are built from cards/ into www/sherpa-cards.js and shipped inside the
integration, so a pinned release carries cards that match its entities.

Registration goes through Lovelace *resources* rather than
``frontend.add_extra_js_url``, for the reason the another integration integration found: an
extra module URL runs before the frontend has finished booting, and Home
Assistant then replaces ``window.customElements`` with a scoped registry,
silently discarding what was defined. Resources load after the frontend is up.

Nothing here may break setup: the entities matter more than the cards.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "sherpa-cards.js"
CARD_PATH = f"/{DOMAIN}/{CARD_FILENAME}"
#: The version query busts the browser cache when the bundle changes, and makes
#: the resource easy to recognise and repoint on upgrade.
CARD_URL = f"{CARD_PATH}?v={{version}}"
BUNDLE = Path(__file__).parent / "www" / CARD_FILENAME
_REGISTERED = f"{DOMAIN}_cards_registered"


async def async_register_cards(hass: HomeAssistant, version: str) -> None:
    """Serve the bundle once per Home Assistant, and list it as a resource."""
    if hass.data.get(_REGISTERED):
        return
    if not BUNDLE.is_file():
        _LOGGER.debug("No card bundle at %s; skipping the cards", BUNDLE)
        return
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_PATH, str(BUNDLE), cache_headers=False)])
    except Exception:  # noqa: BLE001 - never fail setup over a dashboard card
        _LOGGER.warning("Could not serve the Sherpa cards; the integration works without "
                        "them", exc_info=True)
        return
    hass.data[_REGISTERED] = True
    await _async_register_resource(hass, CARD_URL.format(version=version))


async def _async_register_resource(hass: HomeAssistant, url: str) -> None:
    try:
        from homeassistant.components.lovelace import LOVELACE_DATA
    except ImportError:
        return
    lovelace = hass.data.get(LOVELACE_DATA)
    resources = getattr(lovelace, "resources", None)
    if resources is None:
        _LOGGER.debug("Lovelace resources are not ready; not registering the cards")
        return
    if getattr(lovelace, "resource_mode", None) != "storage":
        # In YAML mode the resource list belongs to the user's configuration.
        _LOGGER.info("Lovelace is in YAML mode, so add the Sherpa cards yourself:\n"
                     "lovelace:\n  resources:\n    - url: %s\n      type: module", url)
        return
    try:
        if hasattr(resources, "async_load") and not resources.loaded:
            await resources.async_load()
        base = url.split("?")[0]
        for item in resources.async_items():
            existing = str(item.get("url", ""))
            if existing.split("?")[0] != base:
                continue
            if existing != url:
                # Same bundle, older release: point it at this one.
                await resources.async_update_item(item["id"], {"url": url, "res_type": "module"})
                _LOGGER.info("Updated the Sherpa card resource to %s", url)
            return
        await resources.async_create_item({"url": url, "res_type": "module"})
        _LOGGER.info("Registered the Sherpa card resource at %s", url)
    except Exception:  # noqa: BLE001 - a dashboard card must not break setup
        _LOGGER.warning("Could not add the Sherpa cards to the Lovelace resources. Add it "
                        "under Settings > Dashboards > Resources: %s (module)", url,
                        exc_info=True)
