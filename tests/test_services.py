"""Tests pour les services HA du composant picpak."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.picpak.const import DOMAIN


@pytest.fixture
def hass_with_coordinator(hass: HomeAssistant):
    """Injecte un coordinator mock dans hass.data pour les services."""
    coord = MagicMock()
    coord.client = MagicMock()
    coord.async_request_refresh = AsyncMock(return_value=None)
    coord._ble_lock = asyncio.Lock()
    hass.data.setdefault(DOMAIN, {})["test_entry"] = coord
    return hass, coord


@pytest.mark.asyncio
async def test_push_image_service_calls_upload(hass_with_coordinator):
    hass, coord = hass_with_coordinator
    from custom_components.picpak import _async_register_services
    await _async_register_services(hass)

    await hass.services.async_call(
        DOMAIN,
        "push_image",
        {"slot_id": 42, "source": "/config/www/photo.jpg", "crop": "smart"},
        blocking=True,
    )

    coord.client.upload.assert_called_once_with(
        source="/config/www/photo.jpg",
        slot_id=42,
        crop="smart",
    )
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_display_slot_service(hass_with_coordinator):
    hass, coord = hass_with_coordinator
    from custom_components.picpak import _async_register_services
    await _async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "display_slot", {"slot_id": 10}, blocking=True
    )
    coord.client.display.assert_called_once_with(10)
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_clear_display_service(hass_with_coordinator):
    hass, coord = hass_with_coordinator
    from custom_components.picpak import _async_register_services
    await _async_register_services(hass)
    await hass.services.async_call(DOMAIN, "clear_display", {}, blocking=True)
    coord.client.clear_display.assert_called_once()
    coord.async_request_refresh.assert_called_once()


@pytest.mark.asyncio
async def test_erase_slot_service(hass_with_coordinator):
    hass, coord = hass_with_coordinator
    from custom_components.picpak import _async_register_services
    await _async_register_services(hass)
    await hass.services.async_call(
        DOMAIN, "erase_slot", {"slot_id": 33}, blocking=True
    )
    coord.client.erase.assert_called_once_with(33)
    coord.async_request_refresh.assert_called_once()
