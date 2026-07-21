"""Async REST + realtime client for the Skylink Orbit Home cloud."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from . import const
from .exceptions import (
    OrbitAuthError,
    OrbitCannotConnect,
    OrbitCommandError,
    OrbitError,
    OrbitTimeout,
)
from .models import OrbitDevice, OrbitToken
from .transport import RealtimeTransport, build_default_transport

_LOGGER = logging.getLogger(__name__)

#: Callback invoked with a device update pushed over the realtime channel.
StatusCallback = Callable[[OrbitDevice], Awaitable[None] | None]


class OrbitClient:
    """Talks to the Orbit cloud on behalf of the Home Assistant integration.

    The client owns authentication (login + transparent token refresh) and
    exposes high-level operations. It never imports Home Assistant, so it can be
    exercised standalone in tests.
    """

    def __init__(
        self,
        email: str,
        password: str,
        *,
        session: aiohttp.ClientSession,
        base_url: str = const.DEFAULT_BASE_URL,
        mqtt_host: str = const.DEFAULT_MQTT_HOST,
        mqtt_port: int = const.DEFAULT_MQTT_PORT,
        mqtt_tls: bool = const.DEFAULT_MQTT_TLS,
        timeout: float = const.DEFAULT_TIMEOUT,
        transport_factory: Callable[..., RealtimeTransport] | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._mqtt_tls = mqtt_tls
        self._timeout = timeout
        self._transport_factory = transport_factory or build_default_transport

        self._token: OrbitToken | None = None
        self._auth_lock = asyncio.Lock()
        self._transport: RealtimeTransport | None = None

    @property
    def user_id(self) -> str | None:
        """The authenticated user id, if a login has completed."""
        return self._token.user_id if self._token else None

    @property
    def is_authenticated(self) -> bool:
        return self._token is not None

    # ---- Authentication ---------------------------------------------------

    async def async_login(self) -> OrbitToken:
        """Authenticate and cache the resulting session token."""
        payload = {"email": self._email, "password": self._password}
        data = await self._raw_request(
            "POST", const.PATH_LOGIN, json=payload, authed=False
        )
        try:
            token = OrbitToken.from_dict(data)
        except KeyError as err:
            raise OrbitAuthError(f"unexpected login response: {err}") from err

        # The model stays clock-free; the client (which knows "now") derives the
        # absolute expiry from a relative expires_in when the server sends one.
        expires_in = data.get("expires_in") or data.get("expiresIn")
        if token.expires_at is None and expires_in is not None:
            try:
                token.expires_at = time.time() + float(expires_in)
            except (TypeError, ValueError):
                token.expires_at = None
        self._token = token
        _LOGGER.debug("Logged in as user_id=%s", token.user_id)
        return token

    async def _async_ensure_token(self) -> OrbitToken:
        """Return a valid token, logging in or refreshing as needed."""
        async with self._auth_lock:
            if self._token is None:
                return await self.async_login()
            if self._token.expires_at is not None and (
                self._token.expires_at - time.time() < 60
            ):
                await self._async_refresh_or_relogin()
            return self._token

    async def _async_refresh_or_relogin(self) -> None:
        assert self._token is not None
        if not self._token.refresh_token:
            self._token = None
            await self.async_login()
            return
        try:
            data = await self._raw_request(
                "POST",
                const.PATH_REFRESH,
                json={"refresh_token": self._token.refresh_token},
                authed=False,
            )
            refreshed = OrbitToken.from_dict(data)
            # Carry forward the user id / mqtt creds if the refresh omits them.
            refreshed.user_id = refreshed.user_id or self._token.user_id
            self._token = refreshed
        except OrbitError:
            _LOGGER.debug("Token refresh failed; re-logging in")
            self._token = None
            await self.async_login()

    # ---- Devices & commands ----------------------------------------------

    async def async_get_devices(self) -> list[OrbitDevice]:
        """Fetch the list of devices and their current state."""
        data = await self._request("GET", const.PATH_DEVICES)
        raw_list = _extract_device_list(data)
        devices: list[OrbitDevice] = []
        for raw in raw_list:
            try:
                devices.append(OrbitDevice.from_dict(raw))
            except (KeyError, TypeError) as err:
                _LOGGER.warning("Skipping unparseable device payload: %s", err)
        return devices

    async def async_send_command(self, device_id: str, command: str) -> None:
        """Send a raw command verb to a device."""
        path = const.PATH_COMMAND.format(device_id=device_id)
        try:
            await self._request("POST", path, json={"command": command})
        except OrbitError:
            raise
        except Exception as err:  # noqa: BLE001 - normalise to our hierarchy
            raise OrbitCommandError(str(err)) from err

    async def async_open_door(self, device_id: str) -> None:
        await self.async_send_command(device_id, const.CMD_OPEN)

    async def async_close_door(self, device_id: str) -> None:
        await self.async_send_command(device_id, const.CMD_CLOSE)

    async def async_stop_door(self, device_id: str) -> None:
        await self.async_send_command(device_id, const.CMD_STOP)

    async def async_set_light(self, device_id: str, on: bool) -> None:
        await self.async_send_command(
            device_id, const.CMD_LIGHT_ON if on else const.CMD_LIGHT_OFF
        )

    # ---- Realtime (optional push channel) --------------------------------

    async def async_start_realtime(self, callback: StatusCallback) -> None:
        """Connect the realtime channel and stream device updates to callback.

        Failure here is non-fatal: the caller is expected to keep polling
        :meth:`async_get_devices`. We log and return rather than raise so a
        broken MQTT host never takes the whole integration down.
        """
        token = await self._async_ensure_token()
        if not token.user_id:
            _LOGGER.debug("No user_id available; realtime channel disabled")
            return

        self._transport = self._transport_factory(
            host=self._mqtt_host,
            port=self._mqtt_port,
            tls=self._mqtt_tls,
            username=token.mqtt_username or token.user_id,
            password=token.mqtt_password or token.access_token,
        )

        async def _on_message(device: OrbitDevice) -> None:
            result = callback(device)
            if asyncio.iscoroutine(result):
                await result

        try:
            await self._transport.async_connect(
                user_id=token.user_id, on_device=_on_message
            )
        except Exception as err:  # noqa: BLE001 - never fatal
            _LOGGER.info("Realtime channel unavailable, polling only: %s", err)
            self._transport = None

    async def async_stop_realtime(self) -> None:
        if self._transport is not None:
            await self._transport.async_disconnect()
            self._transport = None

    # ---- HTTP plumbing ----------------------------------------------------

    async def _request(
        self, method: str, path: str, *, json: dict[str, Any] | None = None
    ) -> Any:
        """Authenticated request with a single automatic re-auth on 401."""
        token = await self._async_ensure_token()
        try:
            return await self._raw_request(
                method, path, json=json, token=token.access_token
            )
        except OrbitAuthError:
            _LOGGER.debug("Auth rejected mid-session; re-logging in and retrying")
            self._token = None
            token = await self._async_ensure_token()
            return await self._raw_request(
                method, path, json=json, token=token.access_token
            )

    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        token: str | None = None,
        authed: bool = True,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/json",
            "User-Agent": const.DEFAULT_USER_AGENT,
        }
        if authed and token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with self._session.request(
                method,
                url,
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as resp:
                return await self._handle_response(resp)
        except TimeoutError as err:
            raise OrbitTimeout(f"timeout calling {method} {path}") from err
        except aiohttp.ClientError as err:
            raise OrbitCannotConnect(f"connection error calling {path}: {err}") from err

    @staticmethod
    async def _handle_response(resp: aiohttp.ClientResponse) -> Any:
        if resp.status in (401, 403):
            raise OrbitAuthError(f"authentication failed ({resp.status})")
        if resp.status >= 500:
            raise OrbitCannotConnect(f"server error ({resp.status})")
        if resp.status >= 400:
            body = await _safe_text(resp)
            raise OrbitError(f"request failed ({resp.status}): {body}")
        if resp.status == 204 or resp.content_length == 0:
            return {}
        try:
            return await resp.json(content_type=None)
        except (aiohttp.ContentTypeError, ValueError):
            # Some command endpoints reply with a bare "OK" body.
            return {"raw": await _safe_text(resp)}


def _extract_device_list(data: Any) -> list[dict[str, Any]]:
    """Pull the list of device dicts out of a variety of envelope shapes."""
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("devices", "data", "results", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [d for d in value if isinstance(d, dict)]
        # A single-device object.
        if data.get("id") or data.get("device_id") or data.get("deviceId"):
            return [data]
    return []


async def _safe_text(resp: aiohttp.ClientResponse) -> str:
    try:
        return (await resp.text())[:500]
    except Exception:  # noqa: BLE001
        return "<unreadable>"
