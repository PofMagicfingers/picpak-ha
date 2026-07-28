"""Picpak custom component for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _iter_coordinators(hass: HomeAssistant):
    """Yield tous les coordinators picpak enregistrés (un par ConfigEntry)."""
    for coord in hass.data.get(DOMAIN, {}).values():
        yield coord


async def _async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les 4 services picpak (idempotent)."""
    if hass.services.has_service(DOMAIN, "push_image"):
        return  # déjà enregistrés

    async def _push_image(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        source = call.data["source"]
        crop = call.data.get("crop", "smart")
        for coord in _iter_coordinators(hass):
            await hass.async_add_executor_job(
                lambda: coord.client.upload(source=source, slot_id=slot_id, crop=crop)
            )
            await coord.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "push_image",
        _push_image,
        schema=vol.Schema({
            vol.Required("slot_id"): vol.All(vol.Coerce(int), vol.Range(min=0, max=699)),
            vol.Required("source"): cv.string,
            vol.Optional("crop", default="smart"): vol.In(["smart", "center", "letterbox"]),
        }),
    )
