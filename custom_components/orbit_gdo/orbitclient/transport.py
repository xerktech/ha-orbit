"""MQTT transport for the Orbit cloud.

Abstracted behind :class:`MqttTransport` so tests can inject a fake broker, and
so the ``paho-mqtt`` import stays lazy.
"""

from __future__ import annotations

import asyncio
import logging
import random
import ssl
from collections.abc import Callable
from typing import Protocol

from . import const
from .exceptions import OrbitAuthError, OrbitCannotConnect

_LOGGER = logging.getLogger(__name__)

#: Called on the event loop for every inbound message.
MessageHandler = Callable[[str, bytes], None]
#: Called on the event loop after every (re)connect.
ConnectHandler = Callable[[], None]


class MqttTransport(Protocol):
    """What :class:`~orbitclient.client.OrbitClient` needs from MQTT."""

    @property
    def is_connected(self) -> bool: ...

    async def async_connect(
        self,
        *,
        username: str,
        password: str,
        topics: list[str],
        on_message: MessageHandler,
        on_connect: ConnectHandler,
    ) -> None: ...

    async def async_publish(self, topic: str, payload: str) -> None: ...

    async def async_disconnect(self) -> None: ...


def build_default_transport() -> MqttTransport:
    return PahoMqttTransport()


def _build_ssl_context() -> ssl.SSLContext:
    """TLS context trusting only the bundled chain (blocking: reads a file)."""
    ctx = ssl.create_default_context(cafile=str(const.CA_BUNDLE))
    return ctx


class PahoMqttTransport:
    """Transport backed by ``paho-mqtt`` 2.x (bundled with Home Assistant).

    paho runs its network loop on its own thread; every callback is bounced
    onto the asyncio loop with ``call_soon_threadsafe``. paho handles
    reconnects itself; topics are re-subscribed on each connect.
    """

    def __init__(
        self, *, host: str = const.MQTT_HOST, port: int = const.MQTT_PORT
    ) -> None:
        self._host = host
        self._port = port
        self._client = None  # type: ignore[var-annotated]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._topics: list[str] = []
        self._on_message: MessageHandler | None = None
        self._on_connect: ConnectHandler | None = None
        self._first_connect: asyncio.Future[None] | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def async_connect(
        self,
        *,
        username: str,
        password: str,
        topics: list[str],
        on_message: MessageHandler,
        on_connect: ConnectHandler,
    ) -> None:
        import paho.mqtt.client as mqtt  # noqa: PLC0415

        loop = asyncio.get_running_loop()
        self._loop = loop
        self._topics = topics
        self._on_message = on_message
        self._on_connect = on_connect
        self._first_connect = loop.create_future()

        ssl_ctx = await loop.run_in_executor(None, _build_ssl_context)

        # The app uses "<acc_no><0-998>"; the broker may key ACLs on the prefix.
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{username}{random.randint(0, 998)}",
            clean_session=True,
        )
        client.username_pw_set(username, password)
        client.tls_set_context(ssl_ctx)
        client.reconnect_delay_set(min_delay=2, max_delay=120)
        client.on_connect = self._paho_on_connect
        client.on_disconnect = self._paho_on_disconnect
        client.on_message = self._paho_on_message
        self._client = client

        try:
            await loop.run_in_executor(
                None, client.connect, self._host, self._port, const.MQTT_KEEPALIVE
            )
        except OSError as err:
            raise OrbitCannotConnect(f"MQTT connect failed: {err}") from err
        client.loop_start()

        try:
            async with asyncio.timeout(const.DEFAULT_TIMEOUT):
                await self._first_connect
        except TimeoutError as err:
            await self.async_disconnect()
            raise OrbitCannotConnect("MQTT broker did not acknowledge connect") from err
        except OrbitAuthError:
            await self.async_disconnect()
            raise

    async def async_publish(self, topic: str, payload: str) -> None:
        client = self._client
        if client is None or not self._connected:
            raise OrbitCannotConnect("MQTT not connected")
        info = client.publish(topic, payload, qos=0)
        if info.rc != 0:
            raise OrbitCannotConnect(f"MQTT publish failed (rc={info.rc})")

    async def async_disconnect(self) -> None:
        client = self._client
        if client is None:
            return
        self._client = None
        self._connected = False
        client.disconnect()
        await asyncio.get_running_loop().run_in_executor(None, client.loop_stop)

    # ---- paho thread callbacks -------------------------------------------

    def _paho_on_connect(self, client, _userdata, _flags, reason_code, _props=None):  # noqa: ANN001
        if reason_code.is_failure:
            _LOGGER.warning("Orbit MQTT connect refused: %s", reason_code)
            # paho would retry forever with bad credentials; stop it.
            if str(reason_code) in ("Bad user name or password", "Not authorized"):
                client.disconnect()
                self._resolve_first(
                    OrbitAuthError(f"MQTT login refused: {reason_code}")
                )
            else:
                self._resolve_first(OrbitCannotConnect(f"MQTT refused: {reason_code}"))
            return
        for topic in self._topics:
            client.subscribe(topic, qos=1)
        self._connected = True
        _LOGGER.debug("Orbit MQTT connected; subscribed to %s", self._topics)
        self._resolve_first(None)
        if self._loop and self._on_connect:
            self._loop.call_soon_threadsafe(self._on_connect)

    def _paho_on_disconnect(self, _client, _userdata, _flags, reason_code, _props=None):  # noqa: ANN001
        self._connected = False
        _LOGGER.debug("Orbit MQTT disconnected: %s", reason_code)

    def _paho_on_message(self, _client, _userdata, msg) -> None:  # noqa: ANN001
        if self._loop and self._on_message:
            self._loop.call_soon_threadsafe(self._on_message, msg.topic, msg.payload)

    def _resolve_first(self, error: Exception | None) -> None:
        fut, loop = self._first_connect, self._loop
        if fut is None or loop is None:
            return

        def _set() -> None:
            if fut.done():
                return
            if error is None:
                fut.set_result(None)
            else:
                fut.set_exception(error)

        loop.call_soon_threadsafe(_set)
