"""Tests unitaires pour PicpakClient — mock subprocess.run."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from custom_components.picpak.picpak_client import PicpakClient, PicpakClientError


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Helper : construit un CompletedProcess mock."""
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)


class TestStatus:
    def test_status_success(self):
        payload = {
            "current_slot_id": 42,
            "battery": 87,
            "images_stored": 150,
            "refresh_interval": 3600,
            "open_door_refresh": True,
        }
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(payload))) as mock_run:
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            result = client.status()
        assert result == payload
        mock_run.assert_called_once()
        # Vérifier que le device_id est bien passé au CLI
        cmd = mock_run.call_args[0][0]
        assert "--device" in cmd
        assert "AA:BB:CC:DD:EE:FF" in cmd
        assert "status" in cmd

    def test_status_cli_missing_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            with pytest.raises(PicpakClientError, match="introuvable"):
                client.status()

    def test_status_nonzero_returncode_raises(self):
        with patch(
            "subprocess.run",
            return_value=_completed(stderr="device unreachable", returncode=2),
        ):
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            with pytest.raises(PicpakClientError, match="returncode=2") as exc_info:
                client.status()
            assert exc_info.value.stderr == "device unreachable"
            assert exc_info.value.returncode == 2

    def test_status_invalid_json_raises(self):
        with patch("subprocess.run", return_value=_completed(stdout="pas du json")):
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            with pytest.raises(PicpakClientError, match="non-JSON"):
                client.status()

    def test_status_timeout_raises(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="picpak", timeout=30)):
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            with pytest.raises(PicpakClientError, match="timeout"):
                client.status()
