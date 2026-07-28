"""Fixtures partagées pour les tests picpak."""
from __future__ import annotations

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Active les custom_components pour tous les tests."""
    yield
