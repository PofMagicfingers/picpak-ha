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

## Example: display current playing music cover

Add this to your `automations.yaml`:

```yaml
- id: picpak_music_cover
  alias: "Picpak — push cover art of currently playing music"
  trigger:
    - platform: state
      entity_id: media_player.living_room_speaker
      attribute: media_content_id
  condition:
    - condition: template
      value_template: "{{ state_attr('media_player.living_room_speaker', 'entity_picture') is not none }}"
  action:
    - service: picpak.push_image
      data:
        slot_id: 0
        source: "http://homeassistant.local:8123{{ state_attr('media_player.living_room_speaker', 'entity_picture') }}"
        crop: smart
```

The trigger fires whenever the media_content_id changes on the specified player.
It reads the `entity_picture` attribute (URL relative to your HA instance) and
pushes it to slot 0 of the Picpak device.

## Development

```bash
pip install -e ".[dev]"
pytest tests/
```

## License

MIT
