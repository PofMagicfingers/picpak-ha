"""ConfigFlow pour l'intégration picpak (scan BLE via HA bluetooth central + fallback manuel)."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from picpak.protocol import SERVICE_UUID

from .const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PicpakConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup wizard picpak."""

    VERSION = 1
    _MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")

    def __init__(self) -> None:
        self._discovered_devices: list[dict[str, Any]] = []

    async def _run_scan(self) -> None:
        """Lit le cache du scanner Bluetooth central HA — pas de scan externe.

        Sur HAOS/container, l'adaptateur BT est owned par l'intégration
        Bluetooth officielle qui scanne en permanence. Un `BleakScanner.discover`
        externe entre en conflit et rate. `async_discovered_service_info` lit
        directement le cache du scan central.
        """
        results: list[dict[str, Any]] = []
        try:
            connectable_infos = list(
                bluetooth.async_discovered_service_info(self.hass, connectable=True)
            )
            all_infos = list(
                bluetooth.async_discovered_service_info(self.hass, connectable=False)
            )
        except Exception as exc:
            _LOGGER.error("picpak scan: read of HA bluetooth cache raised: %s", exc)
            self._discovered_devices = []
            return

        _LOGGER.info(
            "picpak scan: HA bluetooth cache contains %d connectable + %d total device(s)",
            len(connectable_infos), len(all_infos),
        )
        # On garde le superset (all_infos inclut connectable + advertising-only,
        # y compris via ESPHome BLE proxies non-connectables).
        service_infos = all_infos
        for info in service_infos:
            name = info.name or ""
            service_uuids = {u.lower() for u in (info.service_uuids or [])}
            matches_uuid = SERVICE_UUID.lower() in service_uuids
            matches_name = "picpak" in name.lower()
            _LOGGER.debug(
                "picpak scan candidate: address=%s name=%r rssi=%s uuids=%s → match(uuid=%s name=%s)",
                info.address, name, info.rssi, sorted(service_uuids),
                matches_uuid, matches_name,
            )
            if matches_uuid or matches_name:
                results.append({
                    "device_id": info.address,
                    "name": name or "(unnamed)",
                    "rssi": info.rssi,
                })

        if not results:
            _LOGGER.warning(
                "picpak scan: no Picpak match among %d connectable device(s) — "
                "check that the device is in pairing mode (LED lit) and the HA "
                "Bluetooth integration sees advertisements",
                len(service_infos),
            )
        else:
            _LOGGER.info("picpak scan: %d Picpak device(s) matched", len(results))
        self._discovered_devices = results

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

        await self._run_scan()

        if not self._discovered_devices:
            return await self.async_step_no_devices()

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.In({
                d["device_id"]: f"{d['name']} ({d['device_id']}, RSSI {d['rssi']})"
                for d in self._discovered_devices
            }),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_no_devices(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Aucun device détecté — instructions + menu (rescan / manuel)."""
        return self.async_show_menu(
            step_id="no_devices",
            menu_options=["user", "manual"],
        )

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
