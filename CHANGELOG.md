# Changelog

## 0.1.4 — 2026-07-29

Workaround for rootless podman + Bluetooth + dbus REJECTED:['EXTERNAL'] auth error.

### Added

- Module-level monkey-patch of `dbus_fast.auth.UID_NOT_SPECIFIED = None` applied at import time, so HA's own Bluetooth integration works past the rootless dbus auth mismatch (uid 0 in the container's user namespace vs mapped host uid seen by SO_PEERCRED).
- `sitecustomize.py` written to site-packages at `async_setup()`, so subprocess Python (notably the bundled `picpak` CLI called by the coordinator) also picks up the patch on interpreter startup. Idempotent, auto-heals after container image bumps.

### Why

Only affects rootless podman/docker deployments. Rootful containers don't hit this because their uid 0 matches host uid 0. The patch is a workaround for the dbus-fast auth path — no functional change for users on rootful setups.

## 0.1.3 — 2026-07-29

Add `translations/{en,fr}.json` so the config flow shows explanatory text (title + description + `data_description`) instead of raw schema keys. Fixed the `device_id*`-only manual-entry screen that gave no hint on where to find the MAC address.

## 0.1.2 — 2026-07-29

Fix `requirements` in `manifest.json` : `picpak-ble[cli]>=0.1.0` (with the `[cli]` extra) instead of `picpak-ble>=0.1.0`. Without the extra, HA installed only the base library but not the `picpak` binary the integration wraps via subprocess. Also removed the obsolete "install manually" section from the README.

## 0.1.1 — 2026-07-29

Add `requirements = ["picpak-ble>=0.1.0"]` in `manifest.json` so HA auto-installs the dependency at startup via pip in its container env, instead of asking users to run pip manually inside the container.

## 0.1.0 — 2026-07-28

Initial release.

### Features

- Custom component with domain `picpak`
- Entity `image.picpak_image` mirroring the device display
- 4 sensors: `current_slot`, `battery`, `images_stored`, `refresh_interval`
- 1 binary_sensor: `open_door_refresh`
- 4 services: `push_image`, `display_slot`, `clear_display`, `erase_slot`
- Config flow with BLE scan + manual MAC fallback
- Requires the external `picpak` CLI (see README)
