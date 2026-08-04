"""Picpak custom component for Home Assistant."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Persistent target for the sitecustomize patch. `/config/` is HA's persistent
# volume; a subdirectory here survives container restarts, unlike the container's
# site-packages which are ephemeral in HAOS/HACS podman setups. The user must
# add `-e PYTHONPATH=/config/picpak-patches` to their container config so Python
# picks up the sitecustomize.py at interpreter startup.
_PATCH_DIR = Path("/config/picpak-patches")
_PATCH_FILE = _PATCH_DIR / "sitecustomize.py"

# Rootless podman workaround. dbus-fast defaults to sending its own uid in the
# EXTERNAL auth handshake with the system bus. In rootless podman the container's
# uid 0 doesn't match the mapped host uid the kernel reports via SO_PEERCRED —
# dbus rejects with REJECTED:['EXTERNAL']. Setting UID_NOT_SPECIFIED to None
# makes dbus-fast skip the uid announcement, so dbus falls back to SO_PEERCRED
# which matches. Fixes HA's own Bluetooth integration AND our own picpak-ble
# in-process calls in one shot.
#
# The runtime import-time patch below is best-effort. If HA already imported
# dbus_fast.auth AND already opened a bluez connection with the previous
# UID_NOT_SPECIFIED value before we load, the patch is too late for the current
# process — HA's bluetooth stack is already stuck on the rejected handshake.
# The permanent fix is `_ensure_sitecustomize_patch()`, called from async_setup(),
# which writes a sitecustomize.py the Python interpreter loads at every subsequent
# startup, BEFORE any user import. First install requires TWO container restarts:
# 1st writes sitecustomize.py (no effect this run), 2nd loads it → patch active.
_DBUS_ALREADY_IMPORTED = "dbus_fast.auth" in sys.modules
try:
    import dbus_fast.auth as _dbf_auth
    _dbf_auth.UID_NOT_SPECIFIED = None
    _LOGGER.warning(
        "picpak: dbus-fast runtime auth patch applied (UID_NOT_SPECIFIED=None); "
        "dbus_fast.auth was %s imported by another module. "
        "If already imported, this current process may still fail — "
        "restart the container to activate the permanent sitecustomize patch.",
        "already" if _DBUS_ALREADY_IMPORTED else "not yet",
    )
except ImportError:
    _LOGGER.warning(
        "picpak: dbus-fast not installed yet, cannot apply runtime auth patch — "
        "restart HA after picpak-ble is installed"
    )

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_DEVICE_ID, DOMAIN, PLATFORMS
from .coordinator import PicpakCoordinator


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
    """Write sitecustomize.py in /config/picpak-patches/ so Python loads the dbus patch before ANY user import.

    Python's `site` module loads sitecustomize.py automatically at interpreter
    startup, before any `import` statement in user code runs. Writing our
    monkey-patch there guarantees that dbus_fast.auth.UID_NOT_SPECIFIED is None
    by the time HA (or anything else) imports dbus_fast for the first time.

    The `/config/` volume is HA's persistent mount, so the patch survives
    container restarts. The user must set `PYTHONPATH=/config/picpak-patches`
    on the container so Python picks up our sitecustomize.py at startup.

    Idempotent: the marker is checked before writing. Safe to call every boot.
    First call has no effect this run (Python interpreter already started
    without the file); it takes effect at the NEXT container restart.
    """
    try:
        _PATCH_DIR.mkdir(parents=True, exist_ok=True)
        existing = _PATCH_FILE.read_text() if _PATCH_FILE.exists() else ""
        if _SITECUSTOMIZE_MARKER in existing:
            _LOGGER.info(
                "picpak: sitecustomize dbus patch already present at %s "
                "(ensure PYTHONPATH=%s is set on the container)",
                _PATCH_FILE, _PATCH_DIR,
            )
            return
        _PATCH_FILE.write_text(existing + _SITECUSTOMIZE_PATCH)
        _LOGGER.warning(
            "picpak: dbus-fast auth patch written to %s. "
            "Ensure PYTHONPATH=%s is set on the container (e.g. `-e PYTHONPATH=%s` "
            "in podman/docker run, or `Environment=PYTHONPATH=%s` in a quadlet), "
            "then RESTART THE CONTAINER — this run stays broken until Python "
            "picks up the sitecustomize at its next startup.",
            _PATCH_FILE, _PATCH_DIR, _PATCH_DIR, _PATCH_DIR,
        )
    except (OSError, PermissionError) as exc:
        _LOGGER.warning(
            "picpak: could not write sitecustomize.py to %s: %s", _PATCH_FILE, exc,
        )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Install dbus-fast auth workaround via sitecustomize.py.

    Fired once per HA boot, before any ConfigEntry setup. The patch itself
    only takes effect at the NEXT container restart (Python has already
    started this time); on first install two restarts are required.
    """
    await hass.async_add_executor_job(_ensure_sitecustomize_patch)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup une entry picpak : coordinator, device_info, platforms, services."""
    coordinator = PicpakCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    try:
        info = await coordinator.client.info()
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
        return

    async def _push_image(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        source = call.data["source"]
        crop = call.data.get("crop", "smart")
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.upload(source=source, slot_id=slot_id, crop=crop)
            await coord.async_request_refresh()

    async def _display_slot(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.display(slot_id)
            await coord.async_request_refresh()

    async def _clear_display(call: ServiceCall) -> None:
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.clear_display()
            await coord.async_request_refresh()

    async def _erase_slot(call: ServiceCall) -> None:
        slot_id = call.data["slot_id"]
        for coord in _iter_coordinators(hass):
            async with coord._ble_lock:
                await coord.client.erase(slot_id)
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
