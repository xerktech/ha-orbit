"""Binary sensors for Orbit devices (obstruction, connectivity)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .entity import OrbitEntity
from .orbitclient import OrbitDevice


@dataclass(frozen=True, kw_only=True)
class OrbitBinarySensorDescription(BinarySensorEntityDescription):
    """Describes an Orbit binary sensor and how to read it from a device."""

    value_fn: Callable[[OrbitDevice], bool | None]
    # Only create the entity when the device actually reports this attribute.
    exists_fn: Callable[[OrbitDevice], bool]


SENSORS: tuple[OrbitBinarySensorDescription, ...] = (
    OrbitBinarySensorDescription(
        key="obstruction",
        translation_key="obstruction",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.obstructed,
        exists_fn=lambda d: d.obstructed is not None,
    ),
    OrbitBinarySensorDescription(
        key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.online,
        exists_fn=lambda _d: True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OrbitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        OrbitBinarySensor(coordinator, device_id, description)
        for device_id, device in coordinator.data.items()
        for description in SENSORS
        if description.exists_fn(device)
    )


class OrbitBinarySensor(OrbitEntity, BinarySensorEntity):
    """A binary sensor derived from a device attribute."""

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
        # The connectivity sensor must stay available to report "off".
        if self.entity_description.key == "connectivity":
            return self.coordinator.last_update_success and self.device is not None
        return super().available

    @property
    def is_on(self) -> bool | None:
        device = self.device
        if device is None:
            return None
        return self.entity_description.value_fn(device)
