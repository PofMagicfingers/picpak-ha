"""Wrapper async in-process autour de la lib `picpak_ble` (module `picpak`).

Remplace l'ancien wrapper subprocess : plus de spawn du binaire `picpak`,
plus de parse text, plus de dbus REJECTED côté subprocess. Tout tourne
dans le process HA principal.
"""
from __future__ import annotations

import asyncio
import io
import logging
import urllib.request
from typing import Any

from picpak.client import PicPakClient, PicPakError
from picpak.consts import PERCEPTUAL_RETENTION, PERCEPTUAL_TONE
from picpak.image.consts import DEFAULT_DITHER, DEFAULT_RESCUE
from picpak.image.image import encode_rgb_image
from PIL import Image

from .const import DEFAULT_CLI_TIMEOUT_SECONDS, SLOT_MAX, SLOT_MIN, VALID_CROPS

_LOGGER = logging.getLogger(__name__)


class PicpakClientError(Exception):
    """Erreur remontée par PicpakClient (BLE, encoding, download URL)."""


class PicpakClient:
    """Wrapper async in-process autour de picpak_ble.PicPakClient.

    Chaque méthode ouvre une connexion BLE fresh, exécute son op, ferme.
    Le lock BLE (une seule op à la fois par device) est géré à l'étage
    au-dessus par le coordinator via `asyncio.Lock`.

    Args:
        device_id: MAC address BLE du device.
        timeout: timeout par op (secondes).
    """

    def __init__(self, device_id: str, timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS) -> None:
        self._device_id = device_id
        self._timeout = timeout

    def _client(self) -> PicPakClient:
        return PicPakClient(self._device_id, timeout=self._timeout)

    async def status(self) -> dict[str, Any]:
        """État courant : slot actif, batterie, nb images, intervalle, flag door."""
        try:
            async with self._client() as client:
                display_status = await client.display_status()
                device_info = await client.device_info()
                configuration = await client.configuration()
        except PicPakError as exc:
            raise PicpakClientError(f"status BLE failed: {exc}") from exc
        return {
            "current_slot_id": display_status.active_image_id,
            "battery": device_info.battery,
            "images_stored": device_info.image_count,
            "refresh_interval": configuration.refresh_interval,
            "open_door_refresh": configuration.open_door_refresh,
        }

    async def info(self) -> dict[str, Any]:
        """Infos statiques du device (versions HW/SW, serial, model)."""
        try:
            async with self._client() as client:
                device_info = await client.device_info()
                name = await client.device_name()
        except PicPakError as exc:
            raise PicpakClientError(f"info BLE failed: {exc}") from exc
        return {
            "model": "PicPak",
            "name": name,
            "sw_version": device_info.software_version,
            "hw_version": device_info.hardware_version,
            "serial_number": device_info.serial,
        }

    async def download_slot(self, slot_id: int) -> bytes:
        """Télécharge et vérifie MD5 l'image encodée du slot depuis le device."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        try:
            async with self._client() as client:
                return await client.read_image(slot_id)
        except PicPakError as exc:
            raise PicpakClientError(f"download_slot({slot_id}) BLE failed: {exc}") from exc

    async def upload(self, source: str, slot_id: int, crop: str = "smart") -> None:
        """Charge une image (path local ou URL) → encode → upload dans le slot."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        if crop not in VALID_CROPS:
            raise ValueError(f"crop {crop!r} invalide, attendu {VALID_CROPS}")

        raw = await asyncio.to_thread(self._load_source_bytes, source)
        encoded = await asyncio.to_thread(self._encode_bytes, raw, crop)

        try:
            async with self._client() as client:
                await client.upload(slot_id, encoded, occupied=True)
        except PicPakError as exc:
            raise PicpakClientError(f"upload({slot_id}) BLE failed: {exc}") from exc

    @staticmethod
    def _load_source_bytes(source: str) -> bytes:
        if source.startswith(("http://", "https://")):
            try:
                with urllib.request.urlopen(source, timeout=DEFAULT_CLI_TIMEOUT_SECONDS) as resp:
                    return resp.read()
            except Exception as exc:
                raise PicpakClientError(f"upload: download URL échoué: {exc}") from exc
        try:
            with open(source, "rb") as f:
                return f.read()
        except OSError as exc:
            raise PicpakClientError(f"upload: source introuvable: {source}") from exc

    @staticmethod
    def _encode_bytes(raw: bytes, crop: str) -> bytes:
        try:
            with Image.open(io.BytesIO(raw)) as img:
                return encode_rgb_image(
                    img,
                    dither=DEFAULT_DITHER,
                    tone=PERCEPTUAL_TONE,
                    retention=PERCEPTUAL_RETENTION,
                    crop=crop,
                    rescue=DEFAULT_RESCUE,
                )
        except Exception as exc:
            raise PicpakClientError(f"upload: encoding échoué: {exc}") from exc

    async def display(self, slot_id: int) -> None:
        """Bascule l'affichage sur le slot spécifié (sans re-upload)."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        try:
            async with self._client() as client:
                await client.display(slot_id)
        except PicPakError as exc:
            raise PicpakClientError(f"display({slot_id}) BLE failed: {exc}") from exc

    async def clear_display(self) -> None:
        """Efface l'affichage — le device passe en état neutre.

        Le protocole n'expose pas de commande dédiée "clear" ; on affiche
        le slot 0 par convention (vide par défaut / réservé).
        """
        try:
            async with self._client() as client:
                await client.display(0)
        except PicPakError as exc:
            raise PicpakClientError(f"clear_display BLE failed: {exc}") from exc

    async def erase(self, slot_id: int) -> None:
        """Libère le slot spécifié."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        try:
            async with self._client() as client:
                await client.erase(slot_id)
        except PicPakError as exc:
            raise PicpakClientError(f"erase({slot_id}) BLE failed: {exc}") from exc

