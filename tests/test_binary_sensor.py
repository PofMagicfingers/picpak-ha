"""Tests pour PicpakBinarySensorEntity."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.picpak.binary_sensor import PicpakBinarySensorEntity


@pytest.fixture
def coordinator_on():
    coord = MagicMock()
    coord.data = {"open_door_refresh": True}
    coord.entry.data = {"device_id": "AA:BB:CC:DD:EE:FF"}
    return coord


@pytest.fixture
def coordinator_off():
    coord = MagicMock()
    coord.data = {"open_door_refresh": False}
    coord.entry.data = {"device_id": "AA:BB:CC:DD:EE:FF"}
    return coord


@pytest.fixture
def coordinator_missing():
    coord = MagicMock()
    coord.data = {}  # clé open_door_refresh absente
    coord.entry.data = {"device_id": "AA:BB:CC:DD:EE:FF"}
    return coord


def test_binary_sensor_is_on(coordinator_on):
    entity = PicpakBinarySensorEntity(coordinator_on)
    assert entity.is_on is True


def test_binary_sensor_is_off(coordinator_off):
    entity = PicpakBinarySensorEntity(coordinator_off)
    assert entity.is_on is False


def test_binary_sensor_unique_id(coordinator_on):
    entity = PicpakBinarySensorEntity(coordinator_on)
    assert entity.unique_id == "AA:BB:CC:DD:EE:FF_open_door_refresh"


def test_binary_sensor_is_on_none_when_missing(coordinator_missing):
    entity = PicpakBinarySensorEntity(coordinator_missing)
    assert entity.is_on is None
