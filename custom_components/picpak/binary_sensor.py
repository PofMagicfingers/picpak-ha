"""Binary sensor entity du composant picpak (open_door_refresh)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import PicpakCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PicpakCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PicpakBinarySensorEntity(coordinator)])


class PicpakBinarySensorEntity(CoordinatorEntity[PicpakCoordinator], BinarySensorEntity):
    """Indique si le mode 'open-door-refresh' (accéléromètre) est activé sur le device."""

    _attr_name = "Open door refresh"
    _attr_has_entity_name = True

    def __init__(self, coordinator: PicpakCoordinator) -> None:
        super().__init__(coordinator)
        device_id = coordinator.entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_open_door_refresh"

    @property
    def is_on(self) -> bool | None:
        val = self.coordinator.data.get("open_door_refresh")
        return bool(val) if val is not None else None

    @property
    def device_info(self) -> DeviceInfo:
        """Rattache l'entité au device picpak dans le registry HA."""
        device_id = self.coordinator.entry.data[CONF_DEVICE_ID]
        return DeviceInfo(identifiers={(DOMAIN, device_id)})
