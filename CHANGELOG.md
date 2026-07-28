# Changelog

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
