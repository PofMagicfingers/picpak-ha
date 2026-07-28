"""ConfigFlow pour l'intégration picpak (scan BLE + fallback manuel)."""
from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_DEVICE_ID, DOMAIN
from .picpak_client import PicpakClient, PicpakClientError


class PicpakConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup wizard picpak."""

    VERSION = 1
    _MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")

    def __init__(self) -> None:
        self._discovered_devices: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Étape scan : liste les devices BLE + sélection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Picpak {device_id[-8:]}",
                data={CONF_DEVICE_ID: device_id},
            )

        # Premier appel : on scanne
        if not self._discovered_devices:
            try:
                self._discovered_devices = await self.hass.async_add_executor_job(
                    PicpakClient.scan
                )
            except PicpakClientError:
                self._discovered_devices = []

        if not self._discovered_devices:
            # Aucun device → bascule vers entrée manuelle
            return await self.async_step_manual()

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.In({
                d["device_id"]: f"{d['name']} ({d['device_id']}, RSSI {d['rssi']})"
                for d in self._discovered_devices
            }),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Étape manuelle : saisie du MAC/ID en direct avec validation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip()
            if not self._MAC_RE.match(device_id):
                errors[CONF_DEVICE_ID] = "invalid_device_id"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Picpak {device_id[-8:]}",
                    data={CONF_DEVICE_ID: device_id},
                )

        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): cv.string})
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)
