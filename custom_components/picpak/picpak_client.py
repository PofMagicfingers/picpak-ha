"""Wrapper subprocess du CLI `picpak` externe (paquet akx/picpak-ble).

Cette couche encapsule les appels CLI et retourne des dicts Python typés.
Elle ne dépend d'aucun module Home Assistant — elle est testable en isolation.
"""
from __future__ import annotations

import json
import subprocess
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
