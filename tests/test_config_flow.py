"""Tests pour PicpakConfigFlow."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.picpak.const import DOMAIN


@pytest.mark.asyncio
async def test_user_flow_scan_and_select(hass: HomeAssistant):
    """Flow scan → sélection du 1er device trouvé."""
    devices = [
        {"device_id": "AA:BB:CC:DD:EE:FF", "name": "Picpak-01", "rssi": -55},
        {"device_id": "11:22:33:44:55:66", "name": "Picpak-02", "rssi": -72},
    ]
    with patch(
        "custom_components.picpak.config_flow.PicpakClient.scan",
        return_value=devices,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        # Étape scan → présente la liste
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert "device_id" in result["data_schema"].schema

        # L'utilisateur sélectionne un device
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"device_id": "AA:BB:CC:DD:EE:FF"},
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["data"] == {"device_id": "AA:BB:CC:DD:EE:FF"}


@pytest.mark.asyncio
async def test_user_flow_scan_empty_redirects_to_manual(hass: HomeAssistant):
    """Scan qui ne trouve rien → propose l'entrée manuelle."""
    with patch(
        "custom_components.picpak.config_flow.PicpakClient.scan",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"
