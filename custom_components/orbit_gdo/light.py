"""Opener light platform for Orbit.

Only devices that report a controllable light (``light_on`` is not ``None``) get
a light entity.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .entity import OrbitEntity
from .orbitclient.exceptions import OrbitError

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OrbitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        OrbitLight(coordinator, device_id)
        for device_id, device in coordinator.data.items()
        if device.light_on is not None
    )


class OrbitLight(OrbitEntity, LightEntity):
    """The opener's built-in light (on/off only)."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_translation_key = "opener_light"

    def __init__(self, coordinator: OrbitDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_light"

    @property
    def is_on(self) -> bool | None:
        return self.device.light_on if self.device else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_light(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_light(False)

    async def _set_light(self, on: bool) -> None:
        try:
            await self.coordinator.client.async_set_light(self._device_id, on)
        except OrbitError as err:
            raise HomeAssistantError(f"Orbit light command failed: {err}") from err
        await self.coordinator.async_request_refresh()
