"""Picpak custom component for Home Assistant."""
from __future__ import annotations

import logging
import site
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_DEVICE_ID, DOMAIN, PLATFORMS
from .coordinator import PicpakCoordinator

_LOGGER = logging.getLogger(__name__)

# Rootless podman workaround : dbus-fast defaults to sending its own uid in the
# EXTERNAL auth handshake with the system bus. In rootless podman that uid is 0
# in the container's user namespace but the kernel reports the mapped host uid
# via SO_PEERCRED, causing dbus to reject the handshake with REJECTED:['EXTERNAL'].
# Setting UID_NOT_SPECIFIED to None makes dbus-fast skip the uid announcement, so
# dbus falls back to SO_PEERCRED which matches. Applied here at module import so
# it takes effect before HA loads the bluetooth integration.
try:
    import dbus_fast.auth as _dbf_auth
    _dbf_auth.UID_NOT_SPECIFIED = None
except ImportError:
    pass  # dbus-fast pas encore installé, sera couvert par sitecustomize au prochain boot


_SITECUSTOMIZE_MARKER = "# picpak-ha : dbus-fast auth EXTERNAL patch for rootless podman"
_SITECUSTOMIZE_PATCH = f"""
{_SITECUSTOMIZE_MARKER}
try:
    import dbus_fast.auth as _dbf_auth
    _dbf_auth.UID_NOT_SPECIFIED = None
    import sys as _sys
    print("[picpak] dbus-fast auth patched via sitecustomize", file=_sys.stderr)
except ImportError:
    pass
"""


def _ensure_sitecustomize_patch() -> None:
    """Write sitecustomize.py in site-packages so subprocess Python (picpak CLI) also gets the patch.

    The runtime patch above only affects the current HA process. The picpak CLI
    is launched by HA via subprocess.run(), starting a fresh Python interpreter
    that would import dbus_fast unpatched. sitecustomize.py is loaded automatically
    by Python at interpreter startup (via the `site` module, always active unless
    `python -S`), so writing our patch there covers every subsequent Python process.

    Idempotent : the marker is checked before appending. Safe to call at every
    HA boot. Auto-heals on container image bumps (fresh site-packages → we rewrite).
    """
    try:
        for sp in site.getsitepackages():
            sp_path = Path(sp)
            if not sp_path.is_dir():
                continue
            target = sp_path / "sitecustomize.py"
            existing = target.read_text() if target.exists() else ""
            if _SITECUSTOMIZE_MARKER in existing:
                continue  # déjà appliqué
            new_content = existing + _SITECUSTOMIZE_PATCH
            target.write_text(new_content)
            _LOGGER.info("dbus-fast auth patch written to %s", target)
            return
        _LOGGER.warning("no writable site-packages found for sitecustomize.py")
    except (OSError, PermissionError) as exc:
        _LOGGER.warning("could not write sitecustomize.py for dbus-fast patch: %s", exc)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Boot-time setup : install dbus-fast auth workaround for subprocess Python."""
    await hass.async_add_executor_job(_ensure_sitecustomize_patch)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup une entry picpak : coordinator, device_info, platforms, services."""
    coordinator = PicpakCoordinator(hass, entry)

    # First refresh — récupère l'état initial + lève l'entry si BLE injoignable
    await coordinator.async_config_entry_first_refresh()

    # Récupère et enregistre les infos statiques (versions HW/SW, serial) — best effort
    try:
        info = await hass.async_add_executor_job(coordinator.client.info)
    except Exception as exc:  # pragma: no cover — best effort
        _LOGGER.warning("picpak info failed on setup: %s", exc)
        info = {}

    device_id = entry.data[CONF_DEVICE_ID]
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, device_id)},
        manufacturer="Picpak",
        model=info.get("model", "Unknown"),
        sw_version=info.get("sw_version"),
        hw_version=info.get("hw_version"),
        serial_number=info.get("serial_number"),
        name=f"Picpak {device_id[-8:]}",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload une entry picpak."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            # dernier device → on peut désenregistrer les services
            for svc in ("push_image", "display_slot", "clear_display", "erase_slot"):
                if hass.services.has_service(DOMAIN, svc):
                    hass.services.async_remove(DOMAIN, svc)
    return unload_ok


def _iter_coordinators(hass: HomeAssistant):
    """Yield tous les coordinators picpak enregistrés (un par ConfigEntry)."""
    for coord in hass.data.get(DOMAIN, {}).values():
        yield coord


async def _async_register_services(hass: HomeAssistant) -> None:
    """Enregistre les 4 services picpak (idempotent)."""
    if hass.services.has_service(DOMAIN, "push_image"):
        return  # déjà enregistrés

    async def _push_image(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        source = call.data["source"]
        crop = call.data.get("crop", "smart")
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await hass.async_add_executor_job(
                    lambda: coord.client.upload(source=source, slot_id=slot_id, crop=crop)
                )
            await coord.async_request_refresh()

    async def _display_slot(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await hass.async_add_executor_job(coord.client.display, slot_id)
            await coord.async_request_refresh()

    async def _clear_display(call: ServiceCall) -> None:
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await hass.async_add_executor_job(coord.client.clear_display)
            await coord.async_request_refresh()

    async def _erase_slot(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await hass.async_add_executor_job(coord.client.erase, slot_id)
            await coord.async_request_refresh()

    slot_schema = vol.Schema({
        vol.Required("slot_id"): vol.All(vol.Coerce(int), vol.Range(min=0, max=699)),
    })

    hass.services.async_register(
        DOMAIN,
        "push_image",
        _push_image,
        schema=vol.Schema({
            vol.Required("slot_id"): vol.All(vol.Coerce(int), vol.Range(min=0, max=699)),
            vol.Required("source"): cv.string,
            vol.Optional("crop", default="smart"): vol.In(["smart", "center", "letterbox"]),
        }),
    )
    hass.services.async_register(DOMAIN, "display_slot", _display_slot, schema=slot_schema)
    hass.services.async_register(DOMAIN, "clear_display", _clear_display, schema=vol.Schema({}))
    hass.services.async_register(DOMAIN, "erase_slot", _erase_slot, schema=slot_schema)
