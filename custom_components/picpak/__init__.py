"""Picpak custom component for Home Assistant."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_DEVICE_ID, DOMAIN, PLATFORMS
from .coordinator import PicpakCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup une entry picpak : coordinator, device_info, platforms, services.

    Tente un bond BLE auto avec retry si le device est en pairing mode. Si
    tous les retries échouent, l'entry est marquée non prête via
    ConfigEntryNotReady — HA re-tentera le setup automatiquement et affichera
    un état d'erreur clair à l'user. Pas de warning silencieux qui laisserait
    l'intégration dans un état bâtard (MTU 23, connexions cassées).
    """
    coordinator = PicpakCoordinator(hass, entry)

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            await coordinator.client.pair()
            _LOGGER.info("picpak: BLE bond established at setup (attempt %d/3)", attempt)
            break
        except Exception as exc:
            last_error = exc
            _LOGGER.info(
                "picpak: bond attempt %d/3 failed (%s) — retrying in 10s",
                attempt, exc,
            )
            if attempt < 3:
                await asyncio.sleep(10)
    else:
        raise ConfigEntryNotReady(
            f"Impossible d'appairer le Picpak {entry.data[CONF_DEVICE_ID]} après 3 tentatives. "
            f"Mets le device en mode pairing (appui 3s sur le bouton, LED bleue, "
            f"écran 'Waiting for pairing') et Home Assistant réessaiera automatiquement. "
            f"Dernière erreur : {last_error}"
        )

    await coordinator.async_config_entry_first_refresh()

    try:
        info = await coordinator.client.info()
    except Exception as exc:  # pragma: no cover — best effort
        _LOGGER.warning("picpak info failed on setup: %s", exc)
        info = {}

    device_id = entry.data[CONF_DEVICE_ID]
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        manufacturer="Picpak",
        model=info.get("model", "Unknown"),
        sw_version=info.get("sw_version"),
        hw_version=info.get("hw_version"),
        serial_number=info.get("serial_number"),
        name=f"Picpak {device_id[-8:]}",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload une entry picpak."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            for svc in ("push_image", "display_slot", "clear_display", "erase_slot", "pair_device"):
                if hass.services.has_service(DOMAIN, svc):
                    hass.services.async_remove(DOMAIN, svc)
    return unload_ok


def _iter_coordinators(hass: HomeAssistant):
    """Yield tous les coordinators picpak enregistrés (un par ConfigEntry)."""
    for coord in hass.data.get(DOMAIN, {}).values():
        yield coord


async def _async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les services picpak (idempotent)."""
    if hass.services.has_service(DOMAIN, "push_image"):
        return

    async def _push_image(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        source = call.data["source"]
        crop = call.data.get("crop", "smart")
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.upload(source=source, slot_id=slot_id, crop=crop)
            await coord.async_request_refresh()

    async def _display_slot(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.display(slot_id)
            await coord.async_request_refresh()

    async def _clear_display(call: ServiceCall) -> None:
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.clear_display()
            await coord.async_request_refresh()

    async def _erase_slot(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.erase(slot_id)
            await coord.async_request_refresh()

    async def _pair_device(call: ServiceCall) -> None:
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.pair()

    slot_schema = vol.Schema({
        vol.Required("slot_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
    })

    hass.services.async_register(
        DOMAIN,
        "push_image",
        _push_image,
        schema=vol.Schema({
            vol.Required("slot_id"): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
            vol.Required("source"): cv.string,
            vol.Optional("crop", default="smart"): vol.In(["smart", "center", "letterbox"]),
        }),
    )
    hass.services.async_register(DOMAIN, "display_slot", _display_slot, schema=slot_schema)
    hass.services.async_register(DOMAIN, "clear_display", _clear_display, schema=vol.Schema({}))
    hass.services.async_register(DOMAIN, "erase_slot", _erase_slot, schema=slot_schema)
    hass.services.async_register(DOMAIN, "pair_device", _pair_device, schema=vol.Schema({}))
