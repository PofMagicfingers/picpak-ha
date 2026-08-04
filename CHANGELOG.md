# Changelog

## 0.1.16 — 2026-08-04

Use `bleak_retry_connector` for BLE connection establishment — the HA standard for reliable BLE.

### Why

After v0.1.15 first successful scan on real hardware (Pof enabled the HA Bluetooth integration which unblocked discovery), the config entry setup failed with `habluetooth.wrappers` warning:

> `BleakClient.connect() called without bleak-retry-connector. For reliable connection establishment, use bleak_retry_connector.establish_connection().`

`picpak-ble` was creating and connecting its own raw `BleakClient` inside `PicPakClient.__aenter__` — HA's Bluetooth stack requires clients obtained via `bleak_retry_connector.establish_connection()` for retries, cache reuse, and coordination with the central scanner.

### Changed

- `picpak_client.py` now takes `hass` as first constructor arg and, on every BLE operation:
  1. Resolves the `BLEDevice` via `bluetooth.async_ble_device_from_address(hass, mac, connectable=True)`.
  2. Establishes a `BleakClientWithServiceCache` via `bleak_retry_connector.establish_connection(..., max_attempts=3)`.
  3. Injects that connected client into `PicPakClient(mac, client=...)` via the new `client=` kwarg (added in fork commit `deb89d6`).
  4. Disconnects the client cleanly in `finally`.
- `coordinator.py` passes `hass` to the client constructor.

### Fork bump

- `picpak-ble` fork pinned to commit `deb89d6` on branch `bleak-lt-4`. The commit adds a `client=` kwarg to `PicPakClient` so callers can inject a pre-connected BleakClient; backward compatible with existing `PicPakClient(mac)` usage.

## 0.1.15 — 2026-08-04

Write the sitecustomize dbus patch to `/config/picpak-patches/` (persistent volume) instead of site-packages (ephemeral). Requires a one-time container config change.

### Why

v0.1.14 wrote `sitecustomize.py` to `/usr/local/lib/python3.14/site-packages/`, which is inside the container image on HAOS/podman setups — every `podman restart` throws it away. Persistent HA config lives under `/config`, which is a volume mount that survives restarts.

Verified on Pof's container that `PYTHONPATH` is not preset by HA (only `UV_SYSTEM_PYTHON=true`), so adding our own dir to it can't collide with anything.

### Changed

- `_ensure_sitecustomize_patch()` writes to `/config/picpak-patches/sitecustomize.py` and `mkdir -p` the directory as needed.
- WARNING log now spells out the container config the user must add and points to the exact path.

### One-time setup for users

Add to the HA container config (podman/docker run, compose, or quadlet):

```
-e PYTHONPATH=/config/picpak-patches
```

Then restart the container. On first install:
1. **First restart** after adding the env var → the custom_component writes `sitecustomize.py` to `/config/picpak-patches/`, but Python has already started without picking it up. Bluetooth still broken this run.
2. **Second restart** → Python starts, sees `PYTHONPATH=/config/picpak-patches`, loads our `sitecustomize.py`, patches dbus-fast **before** HA imports it. Bluetooth works.

After the first two restarts, the file is stable and future updates only touch it if the patch content changes.

## 0.1.14 — 2026-08-03

Real fix for rootless-podman dbus REJECTED: write a `sitecustomize.py` so Python loads the patch before any user import (including HA's bluetooth stack).

### Why

v0.1.13 log proved the runtime patch fires **after** HA has already imported `dbus_fast.auth`: `dbus_fast.auth was already imported by another module`. Once HA's bluez manager has opened its dbus connection with the pre-patched UID_NOT_SPECIFIED value, changing the value in-process no longer helps — HA's connection is already stuck on the rejected handshake.

Python's `site` module loads `sitecustomize.py` automatically at interpreter startup, **before any user import**. Writing our patch there guarantees `UID_NOT_SPECIFIED = None` before HA even loads, so its very first dbus handshake succeeds.

### Added

- `_ensure_sitecustomize_patch()` (from v0.1.4, adapted): writes an idempotent patch to `site-packages/sitecustomize.py` from `async_setup()`. First install requires **two container restarts** — the first writes the file (no effect this run because Python already started), the second loads it.

### Changed

- WARNING wording of `picpak scan: no Picpak match` now reports both counts (total + connectable) for less confusion.

## 0.1.13 — 2026-08-03

Log confirmation that the dbus-fast auth patch was actually applied — and whether it fired too late.

### Why

After v0.1.12 shipped a real fix for the rootless-podman dbus REJECTED issue, we couldn't tell from the logs whether the module-level patch had fired at all, or fired too late (after HA's bluetooth integration had already loaded `dbus_fast.auth`). This adds a WARNING-level log at every startup — visible in the default HA log without enabling debug — that reports both facts.

### Added

- Startup log line: `picpak: dbus-fast auth patch applied (UID_NOT_SPECIFIED=None); dbus_fast.auth was {already,not yet} imported by another module`. If `already`, the patch is applied but any code that read the value before the patch is now stale — a restart may be needed.

## 0.1.12 — 2026-08-03

Restore the rootless-podman dbus-fast auth workaround — this time in the right place.

### Why

v0.1.11 diagnostic proved that HA's central Bluetooth scanner sees 0 devices, and a direct `podman exec homeassistant python3 -c "…BleakScanner.discover…"` fails with `AuthError: REJECTED:['EXTERNAL']`. Same root cause as v0.1.4 : rootless podman + dbus. Removed in v0.1.5 on the assumption it wasn't useful, which was right for the subprocess CLI (never fired there) but wrong for the in-process path introduced in v0.1.7 — that IS where it needs to fire.

### Changed

- Module-level `dbus_fast.auth.UID_NOT_SPECIFIED = None` at import time in `__init__.py`. HA imports the custom_component before it loads its Bluetooth integration, so the patch takes effect early enough to fix HA's own bluetooth stack AND our picpak-ble in-process calls.

### Removed

- Nothing from v0.1.11 — the `connectable=False` scan superset stays, still useful for detection via ESPHome BLE proxies.

## 0.1.11 — 2026-08-03

Widen the scan to include advertising-only devices (not just connectable ones).

### Why

v0.1.10 logs on real hardware showed `HA bluetooth cache contains 0 connectable device(s)` while the PicPak was actively advertising. `connectable=True` filters out devices seen only via an ESPHome BLE proxy (which advertises but doesn't route the connection), and also filters out devices HA hasn't yet promoted to "connectable" status. Reading the full cache (`connectable=False`) gives the superset and lets the filter decide.

### Changed

- `config_flow._run_scan` now reads both `connectable=True` (for the log count) and `connectable=False` (the superset actually used for matching).

## 0.1.10 — 2026-08-03

Diagnostic logs on the config-flow scan — no functional change.

### Added

- `config_flow._run_scan` now logs, per invocation:
  - INFO: how many connectable devices HA's Bluetooth central scanner has cached
  - DEBUG: for each candidate — address, name, rssi, service_uuids, match reason
  - WARNING when no Picpak was matched among N candidates
  - ERROR if the HA cache read raised

### Why

v0.1.9 scan returned empty on real hardware while the PicPak was in "Waiting for pairing". Not enough visibility to know whether HA's central scanner sees nothing at all (adapter/permission issue), or sees devices but the PicPak isn't among them (advertising not picked up), or sees the PicPak but the filter doesn't match (name/UUID mismatch). These logs surface all three cases.

## 0.1.9 — 2026-08-03

Fix scan: read HA's central Bluetooth scanner cache instead of racing it with an ad-hoc `BleakScanner.discover`.

### Why

On HAOS / HA container, the Bluetooth adapter is owned by the official Bluetooth integration which scans permanently. Calling `BleakScanner.discover()` from a custom_component either finds nothing or fights the central scanner for adapter access. Reported on real hardware in v0.1.7: PicPak in "Waiting for pairing" (LED lit, actively advertising) → HA config flow scan returns empty.

### Changed

- `config_flow._run_scan` now uses `homeassistant.components.bluetooth.async_discovered_service_info(hass, connectable=True)` — reads the cache maintained by HA's central Bluetooth scanner instead of starting its own.
- Filters kept identical: matches on Picpak SERVICE_UUID or a name containing "picpak" (case-insensitive).
- Static `PicpakClient.scan()` method removed — no longer needed, and it was the wrong approach anyway.

## 0.1.8 — 2026-08-03

Docs — version badge at top of README + doc alignment with the v0.1.7 refactor.

### Why

HACS tracks git tags/releases as its "version" surface. A commit without a tag shows up as a raw sha (`7bdf590`) rather than a version — hard to eyeball what's installed vs available. Bumping so the README badge and the manifest agree, and both are visible in HACS after this tag is fetched.

## 0.1.7 — 2026-08-03

Big refactor: use `picpak-ble` as an in-process async library instead of shelling out to its CLI.

### Why

The previous `PicpakClient` was a subprocess wrapper that passed `--json` to every `picpak <cmd>` invocation, assuming JSON output. **The CLI never had a `--json` option** — every command outputs plain text. That whole wrapper was based on an imagined API and would have failed on every call. Reported on first hardware test of v0.1.5 (`podman exec -it homeassistant picpak scan --json` → `Error: No such option: --json`).

### Changed

- `PicpakClient` now wraps `picpak.client.PicPakClient` (the actual library) with async methods. No more `subprocess.run`, no more text parsing.
- `scan()` calls `bleak.BleakScanner.discover` directly and filters by SERVICE_UUID or name — no CLI hop.
- `upload()` loads the source (path or URL), opens with PIL, encodes via `picpak.image.encode_rgb_image` in a worker thread, then uploads via BLE.
- `coordinator.py` drops all `hass.async_add_executor_job` — everything is async-native now.
- Services (`push_image`, `display_slot`, `clear_display`, `erase_slot`) call the client's async methods directly.
- Fixed side effect: the BLE dbus REJECTED issue (rootless podman + subprocess) is no longer relevant — all BLE calls happen in the main HA process, which already has its own dbus-fast setup working.

### Requirements

- `picpak-ble[client,image]` (was `picpak-ble[cli]`). No more `click`/`tqdm` pulled in; only `bleak` and `Pillow`.

### Removed

- `CONF_CLI_BINARY` / `DEFAULT_CLI_BINARY` constants — no CLI binary to point to anymore.

## 0.1.6 — 2026-08-03

Better UX when no Picpak device is detected during scan (instead of jumping straight to manual MAC entry).

### Added

- New `no_devices` step in the config flow: when the initial Bluetooth scan finds nothing, the user now sees an explanation that Picpak devices don't advertise by default (battery saving) and needs a **3-second button press to enter advertising mode**, plus a menu with two options:
  - **Rescan** — retries the BLE scan (after the user has pressed the button)
  - **Enter MAC manually** — jumps to the existing manual-entry step
- English + French translations for the new step.

### Why

Reported after first successful install of v0.1.5 on real hardware: the scan returned empty because the Picpak wasn't in advertising mode, and the UI silently jumped to manual MAC entry without explaining why or telling the user how to make the device discoverable.

## 0.1.5 — 2026-08-03

Fix the real cause of the Bluetooth issue in rootless podman + drop the sitecustomize workaround.

### Changed

- `requirements` now points to a fork of `picpak-ble` with the `bleak<2` pin relaxed to `bleak<4`. Repository: [PofMagicfingers/picpak-ble@bleak-lt-4](https://github.com/PofMagicfingers/picpak-ble/tree/bleak-lt-4).

### Removed

- Module-level dbus-fast auth monkey-patch (`UID_NOT_SPECIFIED = None`) that never fired in the subprocess `picpak` CLI (as pointed out — the CLI starts its own Python interpreter that loads the system-level `sitecustomize.py`, not this custom component's patch).
- `_ensure_sitecustomize_patch()` helper and its `async_setup()` invocation, no longer needed.

### Why

The actual blocker was the defensive `bleak<2` pin in `picpak-ble` (against the 2.0 AcquireNotify breaking change that bleak 3.0.2 reverted in May 2026). The pin conflicts with HA's own bleak 3.x install. Loosening it to `bleak<4` in a fork resolves the underlying `pip` conflict without any runtime workaround. Analysis: picpak-ble uses only `BleakClient`, `start_notify`, `write_gatt_char`, and `BleakScanner.discover` — all stable APIs since bleak 0.x.

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
