"""Diagnostic sensors for Orbit devices (Wi-Fi signal, battery)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .entity import OrbitEntity
from .orbitclient import OrbitDevice


@dataclass(frozen=True, kw_only=True)
class OrbitSensorDescription(SensorEntityDescription):
    """Describes an Orbit diagnostic sensor."""

    value_fn: Callable[[OrbitDevice], int | None]
    exists_fn: Callable[[OrbitDevice], bool]


SENSORS: tuple[OrbitSensorDescription, ...] = (
    OrbitSensorDescription(
        key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.wifi_rssi,
        exists_fn=lambda d: d.wifi_rssi is not None,
    ),
    OrbitSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.battery_level,
        exists_fn=lambda d: d.battery_level is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OrbitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        OrbitSensor(coordinator, device_id, description)
        for device_id, device in coordinator.data.items()
        for description in SENSORS
        if description.exists_fn(device)
    )


class OrbitSensor(OrbitEntity, SensorEntity):
    """A diagnostic sensor derived from a device attribute."""

    entity_description: OrbitSensorDescription

    def __init__(
        self,
        coordinator: OrbitDataUpdateCoordinator,
        device_id: str,
        description: OrbitSensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> int | None:
        device = self.device
        if device is None:
            return None
        return self.entity_description.value_fn(device)
