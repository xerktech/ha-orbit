"""Binary sensors for Orbit hubs (connectivity, door sensor, auto-close)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .entity import OrbitEntity, async_add_entities_when_present
from .orbitclient import DoorSensorStatus, OrbitDevice


@dataclass(frozen=True, kw_only=True)
class OrbitBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[OrbitDevice], bool | None]
    exists_fn: Callable[[OrbitDevice], bool]


def _has_door_sensor(d: OrbitDevice) -> bool:
    return d.door_sensor not in (None, DoorSensorStatus.NOT_INSTALLED)


SENSORS: tuple[OrbitBinarySensorDescription, ...] = (
    OrbitBinarySensorDescription(
        key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.online,
        exists_fn=lambda _d: True,
    ),
    OrbitBinarySensorDescription(
        key="autoclose",
        translation_key="autoclose",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.autoclose_enabled,
        exists_fn=lambda d: d.autoclose_enabled is not None,
    ),
    OrbitBinarySensorDescription(
        key="door_sensor_battery",
        translation_key="door_sensor_battery",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.door_sensor is DoorSensorStatus.LOW_BATTERY,
        exists_fn=_has_door_sensor,
    ),
    OrbitBinarySensorDescription(
        key="door_sensor_problem",
        translation_key="door_sensor_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.door_sensor is DoorSensorStatus.LOST,
        exists_fn=_has_door_sensor,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OrbitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities_when_present(
        entry, async_add_entities, SENSORS, OrbitBinarySensor
    )


class OrbitBinarySensor(OrbitEntity, BinarySensorEntity):
    entity_description: OrbitBinarySensorDescription

    def __init__(
        self,
        coordinator: OrbitDataUpdateCoordinator,
        device_id: str,
        description: OrbitBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def available(self) -> bool:
        # Connectivity must stay available to report "disconnected".
        if self.entity_description.key == "connectivity":
            return self.coordinator.last_update_success and self.device is not None
        return super().available

    @property
    def is_on(self) -> bool | None:
        device = self.device
        return None if device is None else self.entity_description.value_fn(device)
