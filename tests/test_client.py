"""Unit tests for orbitclient.client (network mocked with aioresponses)."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses

from orbitclient import OrbitAuthError, OrbitClient
from orbitclient.models import DoorState, OrbitDevice

BASE = "https://api.test"
LOGIN = f"{BASE}/v1/auth/login"
DEVICES = f"{BASE}/v1/devices"


def make_client(session, **kwargs) -> OrbitClient:
    return OrbitClient(
        "user@example.com", "secret", session=session, base_url=BASE, **kwargs
    )


async def test_login_caches_token_and_authorizes(session):
    with aioresponses() as m:
        m.post(
            LOGIN,
            payload={"access_token": "tok123", "user_id": "u1", "expires_in": 3600},
        )
        m.get(DEVICES, payload={"devices": [{"id": "d1", "door": "closed"}]})

        client = make_client(session)
        token = await client.async_login()
        assert token.access_token == "tok123"
        assert client.user_id == "u1"
        assert client.is_authenticated

        devices = await client.async_get_devices()
        assert [d.device_id for d in devices] == ["d1"]

    # The devices request must carry the bearer token from login.
    devices_calls = m.requests[("GET", _url(DEVICES))]
    assert devices_calls[0].kwargs["headers"]["Authorization"] == "Bearer tok123"


async def test_login_invalid_credentials_raises_auth(session):
    with aioresponses() as m:
        m.post(LOGIN, status=401)
        client = make_client(session)
        with pytest.raises(OrbitAuthError):
            await client.async_login()


async def test_get_devices_parses_bare_list(session):
    with aioresponses() as m:
        m.post(LOGIN, payload={"access_token": "t"})
        m.get(
            DEVICES,
            payload=[
                {"id": "a", "door": "open", "light": True},
                {"id": "b", "door": "closed"},
            ],
        )
        client = make_client(session)
        devices = await client.async_get_devices()

    by_id = {d.device_id: d for d in devices}
    assert by_id["a"].door_state is DoorState.OPEN
    assert by_id["a"].light_on is True
    assert by_id["b"].door_state is DoorState.CLOSED


async def test_send_command_posts_verb(session):
    with aioresponses() as m:
        m.post(LOGIN, payload={"access_token": "t"})
        m.post(f"{BASE}/v1/devices/d1/command", status=204)
        client = make_client(session)
        await client.async_open_door("d1")

    call = m.requests[("POST", _url(f"{BASE}/v1/devices/d1/command"))][0]
    assert call.kwargs["json"] == {"command": "open"}


async def test_light_command_off(session):
    with aioresponses() as m:
        m.post(LOGIN, payload={"access_token": "t"})
        m.post(f"{BASE}/v1/devices/d1/command", status=200, payload={"ok": True})
        client = make_client(session)
        await client.async_set_light("d1", False)

    call = m.requests[("POST", _url(f"{BASE}/v1/devices/d1/command"))][0]
    assert call.kwargs["json"] == {"command": "light_off"}


async def test_expired_session_triggers_relogin_and_retry(session):
    with aioresponses() as m:
        # First login, then a 401 on devices, then re-login, then success.
        m.post(LOGIN, payload={"access_token": "old", "user_id": "u1"})
        m.get(DEVICES, status=401)
        m.post(LOGIN, payload={"access_token": "new", "user_id": "u1"})
        m.get(DEVICES, payload={"devices": [{"id": "d1", "door": "open"}]})

        client = make_client(session)
        devices = await client.async_get_devices()

    assert [d.device_id for d in devices] == ["d1"]
    # Two login calls happened (initial + re-auth after 401).
    assert len(m.requests[("POST", _url(LOGIN))]) == 2


class _FakeTransport:
    """Realtime transport that immediately replays one device on connect."""

    def __init__(self, device: OrbitDevice) -> None:
        self._device = device
        self.connected = False
        self.disconnected = False

    async def async_connect(self, *, user_id, on_device):
        self.connected = True
        await on_device(self._device)

    async def async_disconnect(self):
        self.disconnected = True


async def test_realtime_delivers_device_to_callback(session):
    pushed = _FakeTransport(OrbitDevice.from_dict({"id": "d1", "door": "opening"}))
    received: list[OrbitDevice] = []

    with aioresponses() as m:
        m.post(LOGIN, payload={"access_token": "t", "user_id": "u1"})
        client = make_client(session, transport_factory=lambda **_: pushed)
        await client.async_login()
        await client.async_start_realtime(lambda d: received.append(d) or None)

    assert pushed.connected
    assert len(received) == 1
    assert received[0].door_state is DoorState.OPENING

    await client.async_stop_realtime()
    assert pushed.disconnected


class _BrokenTransport:
    async def async_connect(self, *, user_id, on_device):
        raise ConnectionError("mqtt down")

    async def async_disconnect(self):
        pass


async def test_realtime_failure_is_non_fatal(session):
    with aioresponses() as m:
        m.post(LOGIN, payload={"access_token": "t", "user_id": "u1"})
        client = make_client(session, transport_factory=lambda **_: _BrokenTransport())
        await client.async_login()
        # Must not raise even though the transport connect fails.
        await client.async_start_realtime(lambda d: None)


def _url(url: str):
    """aioresponses keys its request log by yarl.URL."""
    from yarl import URL

    return URL(url)
