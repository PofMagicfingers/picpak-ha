"""Tests pour l'entry point du composant (setup / unload)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.picpak.const import CONF_DEVICE_ID, DOMAIN


@pytest.mark.asyncio
async def test_setup_entry_registers_coordinator(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICE_ID: "AA:BB:CC:DD:EE:FF"},
        entry_id="test_entry",
    )
    entry.add_to_hass(hass)

    info_payload = {
        "hw_version": "1.2.0", "sw_version": "2.5.1",
        "serial_number": "PP-XYZ", "model": "Picpak 4.2 BWRY",
    }
    status_payload = {
        "current_slot_id": 42, "battery": 87, "images_stored": 150,
        "refresh_interval": 3600, "open_door_refresh": True,
    }

    with patch("custom_components.picpak.coordinator.PicpakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.status.return_value = status_payload
        mock_client.download_slot.return_value = b"png data"
        mock_client.info.return_value = info_payload
        mock_client_cls.return_value = mock_client

        result = await hass.config_entries.async_setup(entry.entry_id)

    assert result is True
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_unload_entry_removes_coordinator(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_DEVICE_ID: "AA:BB:CC:DD:EE:FF"},
        entry_id="test_entry",
    )
    entry.add_to_hass(hass)

    with patch("custom_components.picpak.coordinator.PicpakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "current_slot_id": 1, "battery": 100, "images_stored": 0,
            "refresh_interval": 3600, "open_door_refresh": False,
        }
        mock_client.download_slot.return_value = b""
        mock_client.info.return_value = {
            "hw_version": "1", "sw_version": "1",
            "serial_number": "s", "model": "m",
        }
        mock_client_cls.return_value = mock_client

        await hass.config_entries.async_setup(entry.entry_id)
        result = await hass.config_entries.async_unload(entry.entry_id)

    assert result is True
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
