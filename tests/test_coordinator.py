"""Tests unitaires pour PicpakCoordinator."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.picpak.const import DOMAIN, CONF_DEVICE_ID
from custom_components.picpak.coordinator import PicpakCoordinator
from custom_components.picpak.picpak_client import PicpakClientError


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


@pytest.mark.asyncio
async def test_update_data_downloads_image_on_slot_change(hass: HomeAssistant):
    entry = _FakeEntry()
    status_1 = {"current_slot_id": 5, "battery": 90, "images_stored": 10,
                "refresh_interval": 3600, "open_door_refresh": False}
    status_2 = {"current_slot_id": 7, "battery": 90, "images_stored": 10,
                "refresh_interval": 3600, "open_door_refresh": False}
    png_5 = b"png bytes slot 5"
    png_7 = b"png bytes slot 7"

    with patch("custom_components.picpak.coordinator.PicpakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.status.side_effect = [status_1, status_2]
        mock_client.download_slot.side_effect = [png_5, png_7]
        mock_client_cls.return_value = mock_client

        coord = PicpakCoordinator(hass, entry)
        data1 = await coord._async_update_data()
        assert data1["image_bytes"] == png_5
        assert mock_client.download_slot.call_count == 1

        data2 = await coord._async_update_data()
        assert data2["image_bytes"] == png_7
        assert mock_client.download_slot.call_count == 2


@pytest.mark.asyncio
async def test_update_data_no_download_when_slot_unchanged(hass: HomeAssistant):
    entry = _FakeEntry()
    status = {"current_slot_id": 5, "battery": 90, "images_stored": 10,
              "refresh_interval": 3600, "open_door_refresh": False}
    png = b"png bytes slot 5"

    with patch("custom_components.picpak.coordinator.PicpakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.status.return_value = status
        mock_client.download_slot.return_value = png
        mock_client_cls.return_value = mock_client

        coord = PicpakCoordinator(hass, entry)
        await coord._async_update_data()  # 1er appel → download
        await coord._async_update_data()  # 2e appel → pas de download

    assert mock_client.download_slot.call_count == 1


@pytest.mark.asyncio
async def test_update_data_keeps_cache_when_download_fails(hass: HomeAssistant, caplog):
    entry = _FakeEntry()
    status = {"current_slot_id": 5, "battery": 90, "images_stored": 10,
              "refresh_interval": 3600, "open_door_refresh": False}

    with patch("custom_components.picpak.coordinator.PicpakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.status.return_value = status
        mock_client.download_slot.side_effect = PicpakClientError("BLE flaky")
        mock_client_cls.return_value = mock_client

        coord = PicpakCoordinator(hass, entry)
        coord._cached_image_bytes = b"old cache"

        data = await coord._async_update_data()

    assert data["image_bytes"] == b"old cache"  # cache préservé


@pytest.mark.asyncio
async def test_update_data_raises_update_failed_on_ble_error(hass: HomeAssistant):
    entry = _FakeEntry()

    with patch("custom_components.picpak.coordinator.PicpakClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.status.side_effect = PicpakClientError("device unreachable")
        mock_client_cls.return_value = mock_client

        coord = PicpakCoordinator(hass, entry)
        with pytest.raises(UpdateFailed, match="picpak status failed"):
            await coord._async_update_data()
