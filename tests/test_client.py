"""Client tests: REST signing/login via aioresponses, MQTT via a fake transport."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re

import pytest
from aioresponses import aioresponses

from orbitclient import (
    DoorState,
    OrbitAuthError,
    OrbitCannotConnect,
    OrbitClient,
    OrbitCommandError,
    OrbitTimeout,
    const,
)
from orbitclient.client import parse_api_body, sign

API = re.compile(r"^https://iot\.skyhm\.net:8444/skylinkhub_crm/skyhm_api_s\.jsp.*$")
ACC = "8000000001"
HUB = {
    "hub_id": "HUB1",
    "hub_name": "Single Door",
    "type": "GDO",
    "online": True,
    "reported": {"mdev": {"door": 4, "rssi": -60}},
}


class FakeTransport:
    """In-memory broker: records publishes, answers /get with a hub list."""

    def __init__(self, hubs=None, *, answer_get=True):
        self.hubs = hubs if hubs is not None else [HUB]
        self.answer_get = answer_get
        self.published: list[tuple[str, dict]] = []
        self.topics: list[str] = []
        self.username = self.password = None
        self._on_message = None
        self.connected = False

    @property
    def is_connected(self):
        return self.connected

    async def async_connect(
        self, *, username, password, topics, on_message, on_connect
    ):
        self.username, self.password, self.topics = username, password, topics
        self._on_message = on_message
        self.connected = True

    async def async_publish(self, topic, payload):
        self.published.append((topic, json.loads(payload)))
        if topic.endswith("/get") and self.answer_get:
            body = json.dumps({"data": self.hubs}).encode()
            asyncio.get_running_loop().call_soon(
                self._on_message, f"skylink/things/client/{ACC}/get/result", body
            )

    async def async_disconnect(self):
        self.connected = False

    def push(self, data):
        self._on_message(
            f"skylink/things/client/{ACC}/update/result",
            json.dumps({"data": data}).encode(),
        )


def _login_ok(m):
    m.post(
        API,
        # Byte-for-byte shape of a real reply, incl. the invalid "result":00.
        body='\n\r\n{"result":00,"message":"Success","acc_no":"'
        + ACC
        + '","alias_name":"Test User"}',
    )


def _client(session, transport):
    return OrbitClient(
        " user@example.com ", "pw", session=session, transport_factory=lambda: transport
    )


# ---- REST -------------------------------------------------------------------


def test_sign_matches_app_algorithm():
    expected = hashlib.md5(
        b"1700000000000+act_login+a@b.c+8uHDSF77ueRmLlKkl67"
    ).hexdigest()
    assert sign("1700000000000", "act_login", "a@b.c") == expected


def test_parse_api_body_fixes_invalid_result_literal():
    assert parse_api_body('\n{"result":00,"x":1}\n') == {"result": 0, "x": 1}


async def test_login_sends_signed_request(session):
    with aioresponses() as m:
        _login_ok(m)
        client = _client(session, FakeTransport())
        account = await client.async_login()
        assert account.acc_no == ACC and account.alias_name == "Test User"

        ((key, calls),) = m.requests.items()
        assert key[1].query["cmd"] == "act_login"
        headers = calls[0].kwargs["headers"]
        body = json.loads(calls[0].kwargs["data"])
        assert body["username"] == "user@example.com"  # stripped
        assert body["app_sys"] == "gcm" and body["app_brand"] == "00"
        assert headers["REQ-CMD"] == "act_login"
        assert headers["REQ-DATA"] == "user@example.com"
        assert headers["REQ-SIGNATURE"] == sign(
            headers["REQ-TIMESTAMP"], "act_login", "user@example.com"
        )


async def test_login_rejected_is_auth_error(session):
    with aioresponses() as m:
        m.post(API, body='{"result":11,"message":"Login Name Does Not Exist"}')
        with pytest.raises(OrbitAuthError, match="Does Not Exist"):
            await _client(session, FakeTransport()).async_login()


async def test_bad_signature_is_connect_error(session):
    with aioresponses() as m:
        m.post(API, body='{"result":25,"message":"Invalid Request Signature"}')
        with pytest.raises(OrbitCannotConnect):
            await _client(session, FakeTransport()).async_login()


async def test_http_error_is_connect_error(session):
    with aioresponses() as m:
        m.post(API, status=502)
        with pytest.raises(OrbitCannotConnect):
            await _client(session, FakeTransport()).async_login()


# ---- MQTT -------------------------------------------------------------------


async def test_connect_and_get_devices(session):
    t = FakeTransport()
    with aioresponses() as m:
        _login_ok(m)
        client = _client(session, t)
        devices = await client.async_get_devices()
    assert t.username == ACC and t.password == "pw"
    assert t.topics == [
        f"skylink/things/client/{ACC}/get/result",
        f"skylink/things/client/{ACC}/update/result",
    ]
    assert t.published == [(f"skylink/things/client/{ACC}/get", {})]
    assert devices["HUB1"].door_state is DoorState.CLOSED


async def test_get_devices_timeout(session):
    t = FakeTransport(answer_get=False)
    with aioresponses() as m:
        _login_ok(m)
        client = OrbitClient(
            "u", "p", session=session, timeout=0.05, transport_factory=lambda: t
        )
        with pytest.raises(OrbitTimeout):
            await client.async_get_devices()


async def _ready(session, t):
    with aioresponses() as m:
        _login_ok(m)
        client = _client(session, t)
        await client.async_get_devices()
    t.published.clear()
    return client


def _cmds(t):
    return [p["data"]["desired"]["mdev"]["ctrlgdo"]["cmd"] for _, p in t.published]


async def test_push_updates_and_notifies(session):
    t = FakeTransport()
    client = await _ready(session, t)
    seen = []
    client.on_update = seen.append
    t.push({"hub_id": "HUB1", "reported": {"mdev": {"door": 0}}})
    assert client.devices["HUB1"].door_state is DoorState.OPENING
    assert seen and seen[-1].device_id == "HUB1"


async def test_command_payload_shape(session):
    t = FakeTransport()
    client = await _ready(session, t)
    await client.async_open_door("HUB1")
    ((topic, payload),) = t.published
    assert topic == f"skylink/things/client/{ACC}/desire"
    assert payload["data"]["hub_id"] == "HUB1"
    ctrl = payload["data"]["desired"]["mdev"]["ctrlgdo"]
    assert ctrl["cmd"] == const.CTRL_PRESS and ctrl["ts"].isdigit()


async def test_open_close_are_idempotent(session):
    t = FakeTransport()
    client = await _ready(session, t)
    await client.async_close_door("HUB1")  # already closed
    assert t.published == []
    t.push({"hub_id": "HUB1", "reported": {"mdev": {"door": 1}}})
    await client.async_open_door("HUB1")  # already open
    assert t.published == []
    await client.async_close_door("HUB1")
    assert _cmds(t) == [0]


async def test_stopped_door_direction(session):
    """Real hardware: from STOPPED a press reverses the last direction."""
    t = FakeTransport()
    client = await _ready(session, t)
    t.push({"hub_id": "HUB1", "reported": {"mdev": {"door": 0}}})  # opening
    t.push({"hub_id": "HUB1", "reported": {"mdev": {"door": 2}}})  # stopped
    with pytest.raises(OrbitCommandError):
        await client.async_open_door("HUB1")  # a press would CLOSE it
    assert t.published == []
    await client.async_close_door("HUB1")
    assert _cmds(t) == [0]


async def test_stopped_with_unknown_direction_refuses(session):
    t = FakeTransport(hubs=[{**HUB, "reported": {"mdev": {"door": 2}}}])
    client = await _ready(session, t)
    for action in (client.async_open_door, client.async_close_door):
        with pytest.raises(OrbitCommandError):
            await action("HUB1")
    assert t.published == []


async def test_opening_cannot_be_closed_without_stop(session):
    t = FakeTransport()
    client = await _ready(session, t)
    t.push({"hub_id": "HUB1", "reported": {"mdev": {"door": 0}}})
    with pytest.raises(OrbitCommandError):
        await client.async_close_door("HUB1")
    await client.async_stop_door("HUB1")
    assert _cmds(t) == [0]


async def test_stop_is_noop_when_idle(session):
    t = FakeTransport()
    client = await _ready(session, t)
    await client.async_stop_door("HUB1")
    assert t.published == []


async def test_light_on_off(session):
    t = FakeTransport()
    client = await _ready(session, t)
    await client.async_set_light("HUB1", True)
    await client.async_set_light("HUB1", False)
    assert _cmds(t) == [3, 4]  # 4 = off confirmed on hardware


async def test_last_motion_survives_full_resync(session):
    t = FakeTransport()
    client = await _ready(session, t)
    t.push({"hub_id": "HUB1", "reported": {"mdev": {"door": 0}}})
    t.hubs = [{**HUB, "reported": {"mdev": {"door": 2}}}]
    await client.async_get_devices()
    assert client.devices["HUB1"].last_motion is DoorState.OPENING
