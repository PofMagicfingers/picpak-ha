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

from .const import DEFAULT_CLI_TIMEOUT_SECONDS, SLOT_MIN, SLOT_MAX, VALID_CROPS


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

    def __init__(self, device_id: str, cli_binary: str = "picpak") -> None:
        self._device_id = device_id
        self._cli = cli_binary

    def _run(self, subcommand: str, *args: str, timeout: int = DEFAULT_CLI_TIMEOUT_SECONDS) -> str:
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

    def info(self) -> dict[str, Any]:
        """Retourne les infos statiques du device (versions HW/SW, serial, model)."""
        stdout = self._run("info")
        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise PicpakClientError(f"info: sortie CLI non-JSON: {stdout[:200]}") from exc

    def download_slot(self, slot_id: int) -> bytes:
        """Télécharge l'image du slot spécifié depuis le device. Retourne les bytes PNG."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self._run("download", str(slot_id), "--output", str(tmp_path))
            try:
                return tmp_path.read_bytes()
            except OSError as exc:
                raise PicpakClientError(
                    f"download_slot({slot_id}): fichier tempfile absent après succès CLI: {exc}"
                ) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

    def upload(self, source: str | Path, slot_id: int, crop: str = "smart") -> None:
        """Upload une image (path local ou URL) dans le slot spécifié et l'affiche.

        Utilise l'option --overwrite pour remplacer sans confirmation.
        """
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        if crop not in VALID_CROPS:
            raise ValueError(f"crop {crop!r} invalide, attendu {VALID_CROPS}")

        source_str = str(source)
        tmp_downloaded: Path | None = None

        try:
            if source_str.startswith(("http://", "https://")):
                # Télécharger dans un tempfile
                with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
                    tmp_downloaded = Path(tmp.name)
                try:
                    with urllib.request.urlopen(source_str, timeout=DEFAULT_CLI_TIMEOUT_SECONDS) as resp:
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

    def display(self, slot_id: int) -> None:
        """Bascule l'affichage sur le slot spécifié (sans re-upload)."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        self._run("display", str(slot_id))

    def clear_display(self) -> None:
        """Efface l'affichage — le device passe en état neutre."""
        self._run("clear")

    def erase(self, slot_id: int) -> None:
        """Libère le slot spécifié."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        self._run("erase", str(slot_id))

    @staticmethod
    def scan(cli_binary: str = "picpak", timeout: int = 10) -> list[dict[str, Any]]:
        """Scan BLE pour trouver les devices Picpak à proximité.

        Retourne une liste de dicts avec 'device_id', 'name', 'rssi'.
        """
        cmd = [cli_binary, "scan", "--json", "--timeout", str(timeout)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5,  # marge par rapport au CLI
                check=False,
            )
        except FileNotFoundError as exc:
            raise PicpakClientError(f"CLI '{cli_binary}' introuvable — vérifie l'installation") from exc
        except subprocess.TimeoutExpired as exc:
            raise PicpakClientError(f"CLI '{cli_binary} scan' timeout après {timeout + 5}s") from exc

        if result.returncode != 0:
            raise PicpakClientError(
                f"scan returncode={result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise PicpakClientError(f"scan: sortie CLI non-JSON: {result.stdout[:200]}") from exc
