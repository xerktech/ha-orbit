"""Data update coordinator for the Orbit integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .orbitclient import OrbitAuthError, OrbitClient, OrbitDevice, OrbitError

_LOGGER = logging.getLogger(__name__)

type OrbitConfigEntry = ConfigEntry[OrbitDataUpdateCoordinator]


class OrbitDataUpdateCoordinator(DataUpdateCoordinator[dict[str, OrbitDevice]]):
    """Polls the Orbit cloud and fans realtime pushes into entity state.

    ``data`` is keyed by ``device_id`` so entities can look themselves up in
    O(1) and survive devices coming and going between polls.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: OrbitConfigEntry,
        client: OrbitClient,
        *,
        enable_realtime: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.client = client
        self._enable_realtime = enable_realtime
        self._realtime_started = False

    async def _async_update_data(self) -> dict[str, OrbitDevice]:
        try:
            devices = await self.client.async_get_devices()
        except OrbitAuthError as err:
            # Triggers Home Assistant's reauth flow.
            from homeassistant.exceptions import ConfigEntryAuthFailed

            raise ConfigEntryAuthFailed(str(err)) from err
        except OrbitError as err:
            raise UpdateFailed(str(err)) from err

        # Start the realtime channel once, after we know auth works.
        if self._enable_realtime and not self._realtime_started:
            self._realtime_started = True
            await self.client.async_start_realtime(self._handle_push)

        return {device.device_id: device for device in devices}

    @callback
    def _handle_push(self, device: OrbitDevice) -> None:
        """Merge a realtime push into the current snapshot and notify entities."""
        current = dict(self.data or {})
        existing = current.get(device.device_id)
        current[device.device_id] = existing.merged_with(device) if existing else device
        self.async_set_updated_data(current)

    async def async_shutdown(self) -> None:
        await self.client.async_stop_realtime()
        await super().async_shutdown()
