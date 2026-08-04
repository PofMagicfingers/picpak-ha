"""Wrapper async in-process autour de la lib `picpak_ble` (module `picpak`).

Sur HA, chaque connexion BLE se fait via `bleak_retry_connector.establish_connection`
+ `bluetooth.async_ble_device_from_address(hass)` — le standard HA pour
communiquer avec un device BLE de manière robuste (retries, réutilisation
des BLEDevice discovery cache, coordination avec le scanner central).
Le BleakClient obtenu est ensuite injecté dans PicPakClient via son kwarg
`client=` (ajouté dans le fork picpak-ble `bleak-lt-4` commit deb89d6).
"""
from __future__ import annotations

import asyncio
import io
import logging
import urllib.request
from typing import Any

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
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

    Chaque méthode ouvre une connexion BLE fresh via bleak_retry_connector,
    exécute son op, ferme. Le lock BLE (une seule op à la fois par device)
    est géré à l'étage au-dessus par le coordinator via asyncio.Lock.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        timeout: float = DEFAULT_CLI_TIMEOUT_SECONDS,
    ) -> None:
        self._hass = hass
        self._device_id = device_id
        self._timeout = timeout

    async def _connect_client(self) -> BleakClientWithServiceCache:
        """Obtient un BleakClient robuste via HA + bleak_retry_connector."""
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, self._device_id, connectable=True
        )
        if ble_device is None:
            raise PicpakClientError(
                f"BLE device {self._device_id} introuvable dans le cache HA — "
                "vérifie que le device est à portée et en mode advertising"
            )
        try:
            return await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                f"Picpak-{self._device_id[-8:]}",
                max_attempts=3,
            )
        except Exception as exc:
            raise PicpakClientError(
                f"BLE connect to {self._device_id} failed: {exc}"
            ) from exc

    async def _picpak(self) -> tuple[PicPakClient, BleakClientWithServiceCache]:
        """Instancie PicPakClient avec un BleakClient HA-friendly (retry-connector)."""
        client = await self._connect_client()
        return PicPakClient(self._device_id, timeout=self._timeout, client=client), client

    async def status(self) -> dict[str, Any]:
        """État courant : slot actif, batterie, nb images, intervalle, flag door."""
        picpak, client = await self._picpak()
        try:
            async with picpak:
                display_status = await picpak.display_status()
                device_info = await picpak.device_info()
                configuration = await picpak.configuration()
        except PicPakError as exc:
            raise PicpakClientError(f"status BLE failed: {exc}") from exc
        finally:
            if client.is_connected:
                await client.disconnect()
        return {
            "current_slot_id": display_status.active_image_id,
            "battery": device_info.battery,
            "images_stored": device_info.image_count,
            "refresh_interval": configuration.refresh_interval,
            "open_door_refresh": configuration.open_door_refresh,
        }

    async def info(self) -> dict[str, Any]:
        """Infos statiques du device (versions HW/SW, serial, model)."""
        picpak, client = await self._picpak()
        try:
            async with picpak:
                device_info = await picpak.device_info()
                name = await picpak.device_name()
        except PicPakError as exc:
            raise PicpakClientError(f"info BLE failed: {exc}") from exc
        finally:
            if client.is_connected:
                await client.disconnect()
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
        picpak, client = await self._picpak()
        try:
            async with picpak:
                return await picpak.read_image(slot_id)
        except PicPakError as exc:
            raise PicpakClientError(f"download_slot({slot_id}) BLE failed: {exc}") from exc
        finally:
            if client.is_connected:
                await client.disconnect()

    async def upload(self, source: str, slot_id: int, crop: str = "smart") -> None:
        """Charge une image (path local ou URL) → encode → upload dans le slot."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        if crop not in VALID_CROPS:
            raise ValueError(f"crop {crop!r} invalide, attendu {VALID_CROPS}")

        raw = await asyncio.to_thread(self._load_source_bytes, source)
        encoded = await asyncio.to_thread(self._encode_bytes, raw, crop)

        picpak, client = await self._picpak()
        try:
            async with picpak:
                await picpak.upload(slot_id, encoded, occupied=True)
        except PicPakError as exc:
            raise PicpakClientError(f"upload({slot_id}) BLE failed: {exc}") from exc
        finally:
            if client.is_connected:
                await client.disconnect()

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
        picpak, client = await self._picpak()
        try:
            async with picpak:
                await picpak.display(slot_id)
        except PicPakError as exc:
            raise PicpakClientError(f"display({slot_id}) BLE failed: {exc}") from exc
        finally:
            if client.is_connected:
                await client.disconnect()

    async def clear_display(self) -> None:
        """Efface l'affichage — le device passe en état neutre.

        Le protocole n'expose pas de commande dédiée "clear" ; on affiche
        le slot 0 par convention (vide par défaut / réservé).
        """
        picpak, client = await self._picpak()
        try:
            async with picpak:
                await picpak.display(0)
        except PicPakError as exc:
            raise PicpakClientError(f"clear_display BLE failed: {exc}") from exc
        finally:
            if client.is_connected:
                await client.disconnect()

    async def erase(self, slot_id: int) -> None:
        """Libère le slot spécifié."""
        if not (SLOT_MIN <= slot_id <= SLOT_MAX):
            raise ValueError(f"slot_id {slot_id} hors range {SLOT_MIN}-{SLOT_MAX}")
        picpak, client = await self._picpak()
        try:
            async with picpak:
                await picpak.erase(slot_id)
        except PicPakError as exc:
            raise PicpakClientError(f"erase({slot_id}) BLE failed: {exc}") from exc
        finally:
            if client.is_connected:
                await client.disconnect()
