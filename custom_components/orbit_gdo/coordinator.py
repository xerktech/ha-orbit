"""Data update coordinator for the Orbit integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .orbitclient import OrbitAuthError, OrbitClient, OrbitDevice, OrbitError

_LOGGER = logging.getLogger(__name__)

type OrbitConfigEntry = ConfigEntry[OrbitDataUpdateCoordinator]


class OrbitDataUpdateCoordinator(DataUpdateCoordinator[dict[str, OrbitDevice]]):
    """Holds the device snapshot; MQTT pushes update it in real time.

    ``data`` is keyed by hub id. The periodic update re-requests the full list
    over MQTT as a safety net.
    """

    def __init__(
        self, hass: HomeAssistant, entry: OrbitConfigEntry, client: OrbitClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        client.on_update = self._handle_push

    async def _async_update_data(self) -> dict[str, OrbitDevice]:
        try:
            devices = await self.client.async_get_devices()
        except OrbitAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OrbitError as err:
            raise UpdateFailed(str(err)) from err
        return dict(devices)

    @callback
    def _handle_push(self, device: OrbitDevice) -> None:
        current = dict(self.data or {})
        current[device.device_id] = device
        self.async_set_updated_data(current)
