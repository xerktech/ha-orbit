"""Realtime transport for Orbit status pushes.

The realtime channel is optional. It is abstracted behind
:class:`RealtimeTransport` so that:

* tests can inject a fake that replays canned messages, and
* the heavy ``paho-mqtt`` dependency is imported lazily (only when a real
  connection is actually opened), keeping the pure-Python client importable in
  environments without it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from . import const
from .models import OrbitDevice

_LOGGER = logging.getLogger(__name__)

DeviceHandler = Callable[[OrbitDevice], Awaitable[None]]


class RealtimeTransport(Protocol):
    """Minimal interface the client needs from a realtime transport."""

    async def async_connect(
        self, *, user_id: str, on_device: DeviceHandler
    ) -> None: ...

    async def async_disconnect(self) -> None: ...


def build_default_transport(
    *,
    host: str,
    port: int,
    tls: bool,
    username: str,
    password: str,
) -> RealtimeTransport:
    """Factory for the production (paho-mqtt) transport."""
    return PahoMqttTransport(
        host=host, port=port, tls=tls, username=username, password=password
    )


class PahoMqttTransport:
    """Realtime transport backed by ``paho-mqtt`` (Home Assistant bundles it).

    ``paho-mqtt`` runs its network loop on a background thread and delivers
    messages via callbacks. We bounce those onto the event loop with
    :meth:`asyncio.loop.call_soon_threadsafe` so ``on_device`` runs as a normal
    coroutine on the loop that created this transport.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        tls: bool,
        username: str,
        password: str,
    ) -> None:
        self._host = host
        self._port = port
        self._tls = tls
        self._username = username
        self._password = password
        self._client = None  # type: ignore[var-annotated]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_device: DeviceHandler | None = None
        self._user_id: str | None = None

    async def async_connect(self, *, user_id: str, on_device: DeviceHandler) -> None:
        # Imported here so the client stays importable without paho installed.
        import paho.mqtt.client as mqtt  # noqa: PLC0415

        self._loop = asyncio.get_running_loop()
        self._on_device = on_device
        self._user_id = user_id

        client = mqtt.Client()
        client.username_pw_set(self._username, self._password)
        if self._tls:
            client.tls_set()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        self._client = client

        await self._loop.run_in_executor(
            None, client.connect, self._host, self._port, 60
        )
        client.loop_start()
        _LOGGER.debug("MQTT realtime connected to %s:%s", self._host, self._port)

    async def async_disconnect(self) -> None:
        client = self._client
        if client is None:
            return
        self._client = None
        await asyncio.get_running_loop().run_in_executor(None, client.loop_stop)
        client.disconnect()

    # ---- paho thread callbacks -------------------------------------------

    def _on_connect(self, client, _userdata, _flags, _rc) -> None:  # noqa: ANN001
        topic = const.TOPIC_STATUS.format(user_id=self._user_id, device_id="+")
        client.subscribe(topic)
        _LOGGER.debug("Subscribed to %s", topic)

    def _on_message(self, _client, _userdata, msg) -> None:  # noqa: ANN001
        try:
            payload = json.loads(msg.payload)
        except (ValueError, TypeError):
            _LOGGER.debug("Ignoring non-JSON MQTT payload on %s", msg.topic)
            return
        if not isinstance(payload, dict):
            return
        try:
            device = OrbitDevice.from_dict(payload)
        except (KeyError, TypeError):
            _LOGGER.debug("Ignoring MQTT payload without a device id")
            return

        loop = self._loop
        handler = self._on_device
        if loop is None or handler is None:
            return
        # Hop from the paho network thread back onto the event loop.
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(handler(device)))
