# Picpak — Home Assistant custom component

Home Assistant integration for [Picpak](https://picpak.tech) e-ink Bluetooth photo frame.

## Installation via HACS

1. Add this repo as a custom repository in HACS (type: Integration).
2. Install "Picpak" from the HACS list.
3. Restart Home Assistant.

## Installation of the required CLI

This integration wraps the `picpak` CLI (from [akx/picpak-ble](https://github.com/akx/picpak-ble))
via subprocess. You must install it on the same host as Home Assistant:

```bash
pip install "picpak[cli]"
```

## Configuration

Settings → Devices & Services → Add Integration → Picpak.

The setup flow will scan for nearby Picpak devices via Bluetooth. If no device is found,
you can enter the device MAC address manually.

## Entities

- `image.picpak_image` — mirrors the image currently displayed on the device
- `sensor.picpak_current_slot` — currently displayed slot ID (0–699)
- `sensor.picpak_battery` — device battery level (%)
- `sensor.picpak_images_stored` — number of images stored on the device
- `sensor.picpak_refresh_interval` — auto-refresh interval in seconds
- `binary_sensor.picpak_open_door_refresh` — accelerometer-triggered refresh mode

## Services

- `picpak.push_image` — upload an image to a slot and display it
- `picpak.display_slot` — switch display to an already-uploaded slot
- `picpak.clear_display` — clear the device display
- `picpak.erase_slot` — free a specific slot

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT
