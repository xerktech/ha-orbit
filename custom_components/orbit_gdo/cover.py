"""Garage door cover platform for Orbit."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .entity import OrbitEntity
from .orbitclient import DoorState, OrbitError

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OrbitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one cover per Orbit hub."""
    coordinator = entry.runtime_data
    async_add_entities(
        OrbitCover(coordinator, device_id) for device_id in coordinator.data
    )


class OrbitCover(OrbitEntity, CoverEntity):
    """A single Orbit garage door.

    The hardware only has a toggle "button press"; open/close/stop are mapped
    onto it using the reported state and last direction of travel, and refuse
    rather than guess when a press would move the door the wrong way.
    """

    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    _attr_name = None  # The device name is the cover name.

    def __init__(self, coordinator: OrbitDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = device_id

    @property
    def is_closed(self) -> bool | None:
        device = self.device
        if device is None or device.door_state is DoorState.UNKNOWN:
            return None
        return device.door_state is DoorState.CLOSED

    @property
    def is_opening(self) -> bool:
        return bool(self.device and self.device.door_state is DoorState.OPENING)

    @property
    def is_closing(self) -> bool:
        return bool(self.device and self.device.door_state is DoorState.CLOSING)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        device = self.device
        if device is None:
            return None
        return {"partially_open": device.door_state is DoorState.STOPPED}

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._command(self.coordinator.client.async_open_door)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._command(self.coordinator.client.async_close_door)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._command(self.coordinator.client.async_stop_door)

    async def _command(self, func) -> None:
        try:
            await func(self._device_id)
        except OrbitError as err:
            raise HomeAssistantError(f"Orbit: {err}") from err
        # No refresh needed: the hub pushes state changes within ~1s.
