"""Diagnostics support for Orbit."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL
from .coordinator import OrbitConfigEntry

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OrbitConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (credentials redacted)."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "devices": [asdict(device) for device in (coordinator.data or {}).values()],
    }
