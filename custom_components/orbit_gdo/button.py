"""Button platform for Orbit: the raw door (wall) button."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .entity import OrbitEntity, async_add_entities_when_present
from .orbitclient import OrbitClient, OrbitDevice, OrbitError

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class OrbitButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[OrbitClient, str], Awaitable[None]]
    exists_fn: Callable[[OrbitDevice], bool]


BUTTONS: tuple[OrbitButtonDescription, ...] = (
    OrbitButtonDescription(
        # Same as the wall button. Handy when the door is stopped part-way and
        # its direction is unknown (the cover then refuses to guess). Disabled
        # by default: it can move the door in either direction.
        key="door_button",
        translation_key="door_button",
        entity_registry_enabled_default=False,
        press_fn=lambda client, hub: client.async_press_button(hub),
        exists_fn=lambda _d: True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OrbitConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities_when_present(entry, async_add_entities, BUTTONS, OrbitButton)


class OrbitButton(OrbitEntity, ButtonEntity):
    entity_description: OrbitButtonDescription

    def __init__(
        self,
        coordinator: OrbitDataUpdateCoordinator,
        device_id: str,
        description: OrbitButtonDescription,
    ) -> None:
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"

    async def async_press(self) -> None:
        try:
            await self.entity_description.press_fn(
                self.coordinator.client, self._device_id
            )
        except OrbitError as err:
            raise HomeAssistantError(f"Orbit: {err}") from err
