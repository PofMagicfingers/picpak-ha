"""Tests unitaires pour PicpakCoordinator."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.picpak.const import DOMAIN, CONF_DEVICE_ID
from custom_components.picpak.coordinator import PicpakCoordinator


class _FakeEntry:
    """ConfigEntry minimal pour les tests."""

    def __init__(self, device_id: str = "AA:BB:CC:DD:EE:FF"):
        self.entry_id = "test_entry"
        self.data = {CONF_DEVICE_ID: device_id}


@pytest.mark.asyncio
async def test_update_data_calls_client_status(hass: HomeAssistant):
    entry = _FakeEntry()
    status_payload = {
        "current_slot_id": 42,
        "battery": 87,
        "images_stored": 150,
        "refresh_interval": 3600,
        "open_door_refresh": True,
    }
    with patch("custom_components.picpak.coordinator.PicpakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.status.return_value = status_payload
        mock_client_cls.return_value = mock_client

        coordinator = PicpakCoordinator(hass, entry)
        data = await coordinator._async_update_data()

    assert data["current_slot_id"] == 42
    assert data["battery"] == 87
    assert data["images_stored"] == 150
    assert data["refresh_interval_seconds"] == 3600
    assert data["open_door_refresh"] is True
    mock_client.status.assert_called_once()
