"""The Orbit Garage Door Opener (Skylink) integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BASE_URL,
    CONF_EMAIL,
    CONF_ENABLE_REALTIME,
    CONF_MQTT_HOST,
    PLATFORMS,
)
from .coordinator import OrbitConfigEntry, OrbitDataUpdateCoordinator
from .orbitclient import OrbitClient
from .orbitclient.const import DEFAULT_BASE_URL, DEFAULT_MQTT_HOST


async def async_setup_entry(hass: HomeAssistant, entry: OrbitConfigEntry) -> bool:
    """Set up Orbit from a config entry."""
    session = async_get_clientsession(hass)
    client = OrbitClient(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        session=session,
        base_url=entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        mqtt_host=entry.data.get(CONF_MQTT_HOST, DEFAULT_MQTT_HOST),
    )

    coordinator = OrbitDataUpdateCoordinator(
        hass,
        entry,
        client,
        enable_realtime=entry.options.get(CONF_ENABLE_REALTIME, True),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OrbitConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: OrbitConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
