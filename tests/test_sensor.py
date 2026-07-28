"""Tests pour les 4 entités sensor picpak."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.picpak.sensor import (
    SENSOR_DESCRIPTIONS,
    PicpakSensorEntity,
    async_setup_entry,
)


@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.data = {
        "current_slot_id": 42,
        "battery": 87,
        "images_stored": 150,
        "refresh_interval_seconds": 3600,
        "open_door_refresh": True,
    }
    coord.entry.data = {"device_id": "AA:BB:CC:DD:EE:FF"}
    coord.entry.entry_id = "test_entry"
    return coord


def test_4_sensor_descriptions_exist():
    keys = {d.key for d in SENSOR_DESCRIPTIONS}
    assert keys == {"current_slot", "battery", "images_stored", "refresh_interval"}


@pytest.mark.parametrize("key,expected", [
    ("current_slot", 42),
    ("battery", 87),
    ("images_stored", 150),
    ("refresh_interval", 3600),
])
def test_sensor_native_value(coordinator, key, expected):
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
    entity = PicpakSensorEntity(coordinator, desc)
    assert entity.native_value == expected


def test_battery_sensor_has_device_class(coordinator):
    from homeassistant.components.sensor import SensorDeviceClass
    desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "battery")
    entity = PicpakSensorEntity(coordinator, desc)
    assert entity.device_class == SensorDeviceClass.BATTERY


def test_sensor_unique_ids(coordinator):
    entities = [PicpakSensorEntity(coordinator, d) for d in SENSOR_DESCRIPTIONS]
    unique_ids = {e.unique_id for e in entities}
    assert unique_ids == {
        "AA:BB:CC:DD:EE:FF_current_slot",
        "AA:BB:CC:DD:EE:FF_battery",
        "AA:BB:CC:DD:EE:FF_images_stored",
        "AA:BB:CC:DD:EE:FF_refresh_interval",
    }
