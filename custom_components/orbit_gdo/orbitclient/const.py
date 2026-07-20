"""Endpoint configuration for the Orbit cloud API.

⚠️  PROTOCOL STATUS: PLACEHOLDER — see ``SPEC.md`` §"Protocol discovery".

Skylink does not publish an API. The hosts and paths below are the integration's
best-known defaults and are the *only* things that must change once a real
``mitmproxy`` capture of the Orbit Home app is available. Everything else in the
client is written against these constants, so wiring up the real protocol is a
single-file edit here plus (possibly) tweaks to the parse helpers in
``models.py``.

They can also be overridden at runtime (e.g. from the Home Assistant config
flow's advanced options) by passing ``base_url``/``mqtt_host`` to
:class:`~orbitclient.client.OrbitClient`, so testers can point the integration at
a captured host without editing source.
"""

from __future__ import annotations

# REST API used for authentication, device enumeration and commands.
DEFAULT_BASE_URL = "https://api.orbit.skylinkhome.com"

# Path templates, formatted against DEFAULT_BASE_URL.
PATH_LOGIN = "/v1/auth/login"
PATH_REFRESH = "/v1/auth/refresh"
PATH_DEVICES = "/v1/devices"
PATH_COMMAND = "/v1/devices/{device_id}/command"

# Realtime status channel. If MQTT is unreachable the client degrades to REST
# polling, so these being wrong only costs push latency, not functionality.
DEFAULT_MQTT_HOST = "mqtt.orbit.skylinkhome.com"
DEFAULT_MQTT_PORT = 8883
DEFAULT_MQTT_TLS = True
# {user_id} / {device_id} are substituted per subscription.
TOPIC_STATUS = "orbit/{user_id}/{device_id}/status"
TOPIC_COMMAND = "orbit/{user_id}/{device_id}/command"

# Command verbs sent to PATH_COMMAND / TOPIC_COMMAND.
CMD_OPEN = "open"
CMD_CLOSE = "close"
CMD_STOP = "stop"
CMD_LIGHT_ON = "light_on"
CMD_LIGHT_OFF = "light_off"

DEFAULT_TIMEOUT = 15.0
DEFAULT_USER_AGENT = "ha-orbit-gdo/0.1 (+https://github.com/xerhab/ha-orbit)"
