"""Sensor entities du composant picpak."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, DOMAIN
from .coordinator import PicpakCoordinator


@dataclass(frozen=True, kw_only=True)
class PicpakSensorEntityDescription(SensorEntityDescription):
    """Description avec ajout du champ 'data_key' pour lookup dans coordinator.data."""

    data_key: str


SENSOR_DESCRIPTIONS: tuple[PicpakSensorEntityDescription, ...] = (
    PicpakSensorEntityDescription(
        key="current_slot",
        name="Current slot",
        data_key="current_slot_id",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PicpakSensorEntityDescription(
        key="battery",
        name="Battery",
        data_key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PicpakSensorEntityDescription(
        key="images_stored",
        name="Images stored",
        data_key="images_stored",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PicpakSensorEntityDescription(
        key="refresh_interval",
        name="Refresh interval",
        data_key="refresh_interval_seconds",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup les 4 entités sensor."""
    coordinator: PicpakCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PicpakSensorEntity(coordinator, desc) for desc in SENSOR_DESCRIPTIONS])


class PicpakSensorEntity(CoordinatorEntity[PicpakCoordinator], SensorEntity):
    """Sensor générique piloté par une PicpakSensorEntityDescription."""

    _attr_has_entity_name = True
    entity_description: PicpakSensorEntityDescription

    def __init__(
        self,
        coordinator: PicpakCoordinator,
        description: PicpakSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        device_id = coordinator.entry.data[CONF_DEVICE_ID]
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self):
        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def device_info(self) -> DeviceInfo:
        """Rattache l'entité au device picpak dans le registry HA."""
        device_id = self.coordinator.entry.data[CONF_DEVICE_ID]
        return DeviceInfo(identifiers={(DOMAIN, device_id)})
