"""Wrapper subprocess du CLI `picpak` externe (paquet akx/picpak-ble).

Cette couche encapsule les appels CLI et retourne des dicts Python typés.
Elle ne dépend d'aucun module Home Assistant — elle est testable en isolation.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


class PicpakClientError(Exception):
    """Erreur levée par PicpakClient (CLI absent, returncode ≠ 0, sortie non parsable)."""

    def __init__(self, message: str, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class PicpakClient:
    """Wrapper subprocess du CLI `picpak`.

    Args:
        device_id: identifiant BLE du device (MAC address ou nom).
        cli_binary: nom ou chemin du binaire (défaut "picpak").
    """

    SLOT_MIN = 0
    SLOT_MAX = 699
    VALID_CROPS = ("smart", "center", "letterbox")

    def __init__(self, device_id: str, cli_binary: str = "picpak") -> None:
        self._device_id = device_id
        self._cli = cli_binary

    def _run(self, subcommand: str, *args: str, timeout: int = 30) -> str:
        """Exécute `picpak <subcommand> --device <id> --json [args]`, retourne stdout."""
        cmd = [self._cli, subcommand, "--device", self._device_id, "--json", *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise PicpakClientError(f"CLI '{self._cli}' introuvable — vérifie l'installation") from exc
        except subprocess.TimeoutExpired as exc:
            raise PicpakClientError(f"CLI '{self._cli} {subcommand}' timeout après {timeout}s") from exc

        if result.returncode != 0:
            raise PicpakClientError(
                f"CLI '{subcommand}' returncode={result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return result.stdout

    def status(self) -> dict[str, Any]:
        """Retourne l'état courant du device : slot actif, batterie, nb images, intervalle, flag door."""
        stdout = self._run("status")
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise PicpakClientError(f"status: sortie CLI non-JSON: {stdout[:200]}") from exc

    def download_slot(self, slot_id: int) -> bytes:
        """Télécharge l'image du slot spécifié depuis le device. Retourne les bytes PNG."""
        if not (self.SLOT_MIN <= slot_id <= self.SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range 0-699")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self._run("download", str(slot_id), "--output", str(tmp_path))
            return tmp_path.read_bytes()
        finally:
            tmp_path.unlink(missing_ok=True)

    def upload(self, source: str | Path, slot_id: int, crop: str = "smart") -> None:
        """Upload une image (path local ou URL) dans le slot spécifié et l'affiche.

        Utilise l'option --overwrite pour remplacer sans confirmation.
        """
        if not (self.SLOT_MIN <= slot_id <= self.SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range 0-699")
        if crop not in self.VALID_CROPS:
            raise ValueError(f"crop {crop!r} invalide, attendu {self.VALID_CROPS}")

        source_str = str(source)
        tmp_downloaded: Path | None = None

        try:
            if source_str.startswith(("http://", "https://")):
                # Télécharger dans un tempfile
                with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
                    tmp_downloaded = Path(tmp.name)
                try:
                    with urllib.request.urlopen(source_str, timeout=30) as resp:
                        tmp_downloaded.write_bytes(resp.read())
                except Exception as exc:
                    raise PicpakClientError(f"upload: download URL échoué: {exc}") from exc
                actual_source = tmp_downloaded
            else:
                actual_source = Path(source_str)
                if not actual_source.exists():
                    raise PicpakClientError(f"upload: source introuvable: {source_str}")

            self._run(
                "upload",
                str(actual_source),
                "--start-slot", str(slot_id),
                "--overwrite",
                "--crop", crop,
            )
        finally:
            if tmp_downloaded is not None:
                tmp_downloaded.unlink(missing_ok=True)
