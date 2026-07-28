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


class TestDownloadSlot:
    def test_download_slot_success(self, tmp_path):
        # Le CLI `picpak download` écrit l'image dans un fichier temporaire.
        # On simule ça en interceptant subprocess.run et en écrivant un PNG bidon
        # au path que le CLI est censé produire.
        fake_png = b"\x89PNG\r\n\x1a\nfake image bytes"

        def _mock_run(cmd, **kwargs):
            # Le client passe --output <path> au CLI pour spécifier le fichier de sortie
            output_idx = cmd.index("--output")
            output_path = cmd[output_idx + 1]
            with open(output_path, "wb") as f:
                f.write(fake_png)
            return _completed(stdout="", returncode=0)

        with patch("subprocess.run", side_effect=_mock_run) as mock_run:
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            result = client.download_slot(42)
        assert result == fake_png
        cmd = mock_run.call_args[0][0]
        assert "download" in cmd
        assert "42" in cmd
        assert "--output" in cmd

    def test_download_slot_out_of_range_raises(self):
        client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
        with pytest.raises(ValueError, match="0-699"):
            client.download_slot(700)
        with pytest.raises(ValueError, match="0-699"):
            client.download_slot(-1)

    def test_download_slot_cli_error_raises(self):
        with patch("subprocess.run", return_value=_completed(stderr="slot empty", returncode=1)):
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            with pytest.raises(PicpakClientError, match="returncode=1"):
                client.download_slot(42)


class TestUpload:
    def test_upload_local_path_success(self, tmp_path):
        source = tmp_path / "photo.jpg"
        source.write_bytes(b"\xff\xd8\xff\xe0 fake jpg")

        with patch("subprocess.run", return_value=_completed(returncode=0)) as mock_run:
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            client.upload(source=str(source), slot_id=42, crop="smart")

        cmd = mock_run.call_args[0][0]
        assert "upload" in cmd
        assert str(source) in cmd
        assert "--start-slot" in cmd
        assert "42" in cmd
        assert "--overwrite" in cmd
        assert "--crop" in cmd
        assert "smart" in cmd

    def test_upload_url_downloads_first(self, tmp_path):
        # URL → doit télécharger dans un tempfile puis upload celui-ci
        url = "https://example.com/photo.jpg"
        fake_body = b"\xff\xd8\xff\xe0 downloaded jpg"

        with (
            patch("urllib.request.urlopen") as mock_urlopen,
            patch("subprocess.run", return_value=_completed(returncode=0)) as mock_run,
        ):
            mock_urlopen.return_value.__enter__.return_value.read.return_value = fake_body
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            client.upload(source=url, slot_id=10)

        # subprocess.run appelé avec un path local (pas l'URL directement)
        cmd = mock_run.call_args[0][0]
        assert url not in cmd
        # le dernier argument avant --start-slot devrait être un path local
        # on vérifie juste que --start-slot 10 est là
        assert "--start-slot" in cmd
        assert "10" in cmd

    def test_upload_slot_out_of_range_raises(self, tmp_path):
        source = tmp_path / "p.jpg"
        source.write_bytes(b"x")
        client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
        with pytest.raises(ValueError, match="0-699"):
            client.upload(source=str(source), slot_id=1000)

    def test_upload_invalid_crop_raises(self, tmp_path):
        source = tmp_path / "p.jpg"
        source.write_bytes(b"x")
        client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
        with pytest.raises(ValueError, match="crop"):
            client.upload(source=str(source), slot_id=42, crop="wrong")

    def test_upload_source_missing_raises(self):
        client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
        with pytest.raises(PicpakClientError, match="introuvable"):
            client.upload(source="/nonexistent/path.jpg", slot_id=42)


class TestDisplay:
    def test_display_success(self):
        with patch("subprocess.run", return_value=_completed(returncode=0)) as mock_run:
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            client.display(42)
        cmd = mock_run.call_args[0][0]
        assert "display" in cmd
        assert "42" in cmd

    def test_display_out_of_range_raises(self):
        client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
        with pytest.raises(ValueError, match="0-699"):
            client.display(1000)


class TestClearDisplay:
    def test_clear_display_success(self):
        with patch("subprocess.run", return_value=_completed(returncode=0)) as mock_run:
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            client.clear_display()
        cmd = mock_run.call_args[0][0]
        # La sous-commande peut être "clear" ou "erase-all" selon CLI ; on vise "clear"
        assert "clear" in cmd


class TestErase:
    def test_erase_success(self):
        with patch("subprocess.run", return_value=_completed(returncode=0)) as mock_run:
            client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
            client.erase(42)
        cmd = mock_run.call_args[0][0]
        assert "erase" in cmd
        assert "42" in cmd

    def test_erase_out_of_range_raises(self):
        client = PicpakClient(device_id="AA:BB:CC:DD:EE:FF")
        with pytest.raises(ValueError, match="0-699"):
            client.erase(-1)


class TestScan:
    def test_scan_returns_devices(self):
        devices = [
            {"device_id": "AA:BB:CC:DD:EE:FF", "name": "Picpak-01", "rssi": -55},
            {"device_id": "11:22:33:44:55:66", "name": "Picpak-02", "rssi": -72},
        ]
        with patch("subprocess.run", return_value=_completed(stdout=json.dumps(devices))) as mock_run:
            result = PicpakClient.scan(timeout=5)
        assert result == devices
        cmd = mock_run.call_args[0][0]
        assert "scan" in cmd
        # scan n'a pas de --device
        assert "--device" not in cmd

    def test_scan_empty(self):
        with patch("subprocess.run", return_value=_completed(stdout="[]")):
            result = PicpakClient.scan()
        assert result == []

    def test_scan_cli_error_raises(self):
        with patch("subprocess.run", return_value=_completed(stderr="bluetooth unavailable", returncode=1)):
            with pytest.raises(PicpakClientError, match="returncode=1"):
                PicpakClient.scan()
