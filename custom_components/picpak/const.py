"""Constantes du composant picpak."""

DOMAIN = "picpak"
PLATFORMS = ["image", "sensor", "binary_sensor"]

CONF_DEVICE_ID = "device_id"

DEFAULT_UPDATE_INTERVAL_SECONDS = 60
DEFAULT_CLI_TIMEOUT_SECONDS = 30

SLOT_MIN = 1
SLOT_MAX = 500

VALID_CROPS = ("smart", "center", "letterbox")
