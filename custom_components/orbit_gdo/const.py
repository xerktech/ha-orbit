"""Constants for the Orbit Garage Door Opener integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "orbit_gdo"

PLATFORMS = ["cover", "light", "button", "binary_sensor", "sensor"]

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# State arrives as MQTT pushes within ~1s. This periodic full resync is only a
# safety net (missed pushes, reconnects).
DEFAULT_SCAN_INTERVAL = timedelta(seconds=120)

MANUFACTURER = "Skylink"
