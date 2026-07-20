"""Base entity for Orbit devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import OrbitDataUpdateCoordinator
from .orbitclient import OrbitDevice


class OrbitEntity(CoordinatorEntity[OrbitDataUpdateCoordinator]):
    """Common device wiring shared by all Orbit platforms."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OrbitDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            name=self.device.name if self.device else f"Orbit {device_id}",
            model=self.device.model if self.device else None,
            sw_version=self.device.firmware if self.device else None,
        )

    @property
    def device(self) -> OrbitDevice | None:
        """Return the latest snapshot for this device, if present."""
        return self.coordinator.data.get(self._device_id)

    @property
    def available(self) -> bool:
        device = self.device
        return super().available and device is not None and device.online
