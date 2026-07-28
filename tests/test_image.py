"""Tests pour PicpakImageEntity."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.picpak.image import PicpakImageEntity


@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.data = {
        "current_slot_id": 42,
        "image_bytes": b"fake png data",
    }
    coord.entry.data = {"device_id": "AA:BB:CC:DD:EE:FF"}
    return coord


@pytest.mark.asyncio
async def test_image_entity_returns_bytes(coordinator, hass):
    entity = PicpakImageEntity(coordinator, hass)
    bytes_ = await entity.async_image()
    assert bytes_ == b"fake png data"


def test_image_entity_current_slot_attribute(coordinator, hass):
    entity = PicpakImageEntity(coordinator, hass)
    assert entity.extra_state_attributes == {"current_slot": 42}


def test_image_entity_unique_id(coordinator, hass):
    entity = PicpakImageEntity(coordinator, hass)
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_image"


def test_image_entity_content_type(coordinator, hass):
    entity = PicpakImageEntity(coordinator, hass)
    assert entity.content_type == "image/png"
