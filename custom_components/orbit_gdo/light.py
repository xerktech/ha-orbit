"""Opener light platform for Orbit.

GDO hubs accept explicit on/off commands but never report the light state, so
this is an assumed-state light: HA shows separate on/off controls and the state
is the last command sent from HA (it cannot see changes made elsewhere, e.g. the
phone app or the opener's own timer).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .entity import OrbitEntity
from .orbitclient import OrbitError

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
        if device.has_light
    )


class OrbitLight(OrbitEntity, LightEntity, RestoreEntity):
    """The opener's built-in light (on/off, state assumed)."""

    _attr_assumed_state = True
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_translation_key = "opener_light"

    def __init__(self, coordinator: OrbitDataUpdateCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_light"
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = {"on": True, "off": False}.get(last.state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        try:
            await self.coordinator.client.async_set_light(self._device_id, on)
        except OrbitError as err:
            raise HomeAssistantError(f"Orbit: {err}") from err
        self._attr_is_on = on
        self.async_write_ha_state()
