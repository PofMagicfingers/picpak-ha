"""Image entity du composant picpak — miroir de l'image affichée sur le device."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import PicpakCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup l'entité image."""
    coordinator: PicpakCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PicpakImageEntity(coordinator, hass)])


class PicpakImageEntity(CoordinatorEntity[PicpakCoordinator], ImageEntity):
    """Entité image qui reflète le slot actuellement affiché sur le device."""

    _attr_content_type = "image/png"
    _attr_name = "Picpak image"
    _attr_has_entity_name = True

    def __init__(self, coordinator: PicpakCoordinator, hass: HomeAssistant) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        device_id = coordinator.entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_image"

    async def async_image(self) -> bytes | None:
        """Retourne les bytes PNG de l'image actuellement affichée."""
        return self.coordinator.data.get("image_bytes")

    @property
    def extra_state_attributes(self) -> dict:
        return {"current_slot": self.coordinator.data.get("current_slot_id")}
