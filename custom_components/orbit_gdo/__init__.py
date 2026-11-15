"""The Orbit Garage Door Opener (Skylink) integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_EMAIL, PLATFORMS
from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .orbitclient import OrbitClient


async def async_setup_entry(hass: HomeAssistant, entry: OrbitConfigEntry) -> bool:
    """Set up Orbit from a config entry."""
    client = OrbitClient(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        session=async_get_clientsession(hass),
    )
    coordinator = OrbitDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OrbitConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_disconnect()
    return unload_ok
