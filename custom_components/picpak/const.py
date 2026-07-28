"""Constantes du composant picpak."""

DOMAIN = "picpak"
PLATFORMS = ["image", "sensor", "binary_sensor"]

CONF_DEVICE_ID = "device_id"
CONF_CLI_BINARY = "cli_binary"

DEFAULT_UPDATE_INTERVAL_SECONDS = 60
DEFAULT_CLI_BINARY = "picpak"
DEFAULT_CLI_TIMEOUT_SECONDS = 30

SLOT_MIN = 0
SLOT_MAX = 699

VALID_CROPS = ("smart", "center", "letterbox")
