"""Constants for the Orbit Garage Door Opener integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "orbit_gdo"

# Platforms this integration sets up.
PLATFORMS = ["cover", "light", "binary_sensor", "sensor"]

# Config entry keys.
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_BASE_URL = "base_url"
CONF_MQTT_HOST = "mqtt_host"
CONF_ENABLE_REALTIME = "enable_realtime"

# How often the coordinator polls the REST API. Realtime pushes (when the MQTT
# channel is up) refresh state faster; polling is the reliable floor.
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

MANUFACTURER = "Skylink"
