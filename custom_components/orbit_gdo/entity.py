"""Base entity for Orbit devices."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .orbitclient import OrbitDevice


def async_add_entities_when_present(
    entry: OrbitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    descriptions: Iterable[Any],
    factory: Callable[[OrbitDataUpdateCoordinator, str, Any], Entity],
) -> None:
    """Add one entity per (device, description) once ``exists_fn`` is true.

    Checked at setup and again on every coordinator update, so an entity whose
    field a hub only starts reporting later (e.g. auto-close, a newly paired
    door sensor, a new hub on the account) appears without a reload.
    """
    coordinator = entry.runtime_data
    descriptions = tuple(descriptions)
    added: set[tuple[str, str]] = set()

    @callback
    def _check() -> None:
        new: list[Entity] = []
        for device_id, device in (coordinator.data or {}).items():
            for description in descriptions:
                key = (device_id, description.key)
                if key not in added and description.exists_fn(device):
                    added.add(key)
                    new.append(factory(coordinator, device_id, description))
        if new:
            async_add_entities(new)

    _check()
    entry.async_on_unload(coordinator.async_add_listener(_check))


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
