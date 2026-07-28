"""DataUpdateCoordinator pour le composant picpak."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CLI_BINARY,
    CONF_DEVICE_ID,
    DEFAULT_CLI_BINARY,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
)
from .picpak_client import PicpakClient, PicpakClientError

_LOGGER = logging.getLogger(__name__)


class PicpakCoordinator(DataUpdateCoordinator):
    """Coordinator qui pull l'état du device Picpak toutes les 60s."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.client = PicpakClient(
            device_id=entry.data[CONF_DEVICE_ID],
            cli_binary=entry.data.get(CONF_CLI_BINARY, DEFAULT_CLI_BINARY),
        )
        self._ble_lock = asyncio.Lock()
        self._cached_slot_id: int | None = None
        self._cached_image_bytes: bytes | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_DEVICE_ID]}",
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll status léger. Le download image conditionnel est ajouté en Task 9."""
        async with self._ble_lock:
            try:
                status = await self.hass.async_add_executor_job(self.client.status)
            except PicpakClientError as exc:
                raise UpdateFailed(f"picpak status failed: {exc}") from exc

        return {
            "current_slot_id": status["current_slot_id"],
            "battery": status["battery"],
            "images_stored": status["images_stored"],
            "refresh_interval_seconds": status["refresh_interval"],
            "open_door_refresh": status["open_door_refresh"],
            "image_bytes": self._cached_image_bytes,
        }
