"""Unit tests for orbitclient.models."""

from __future__ import annotations

import pytest

from orbitclient.models import (
    DoorState,
    OrbitDevice,
    OrbitToken,
    parse_door_state,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("open", DoorState.OPEN),
        ("OPENED", DoorState.OPEN),
        (1, DoorState.OPEN),
        ("closed", DoorState.CLOSED),
        (0, DoorState.CLOSED),
        ("opening", DoorState.OPENING),
        ("closing", DoorState.CLOSING),
        ("partial", DoorState.STOPPED),
        ("gibberish", DoorState.UNKNOWN),
        (None, DoorState.UNKNOWN),
    ],
)
def test_parse_door_state(raw, expected):
    assert parse_door_state(raw) is expected


def test_token_from_dict_variants():
    token = OrbitToken.from_dict(
        {"accessToken": "abc", "refreshToken": "r", "userId": "u1"}
    )
    assert token.access_token == "abc"
    assert token.refresh_token == "r"
    assert token.user_id == "u1"


def test_token_requires_access_token():
    with pytest.raises(KeyError):
        OrbitToken.from_dict({"refresh_token": "r"})


def test_device_from_nested_state():
    device = OrbitDevice.from_dict(
        {
            "id": "d1",
            "name": "Main Door",
            "model": "Atoms Pro",
            "online": True,
            "state": {
                "door": "closed",
                "light": False,
                "obstruction": False,
                "rssi": -55,
                "battery": 90,
            },
        }
    )
    assert device.device_id == "d1"
    assert device.name == "Main Door"
    assert device.model == "Atoms Pro"
    assert device.door_state is DoorState.CLOSED
    assert device.light_on is False
    assert device.obstructed is False
    assert device.wifi_rssi == -55
    assert device.battery_level == 90


def test_device_from_flat_payload():
    device = OrbitDevice.from_dict(
        {"deviceId": "d2", "doorStatus": "open", "lightStatus": 1}
    )
    assert device.device_id == "d2"
    assert device.door_state is DoorState.OPEN
    assert device.light_on is True
    # No name reported -> generated fallback.
    assert device.name == "Orbit d2"


def test_device_requires_id():
    with pytest.raises(KeyError):
        OrbitDevice.from_dict({"name": "no id"})


def test_device_unknown_fields_kept_in_extra():
    device = OrbitDevice.from_dict({"id": "d3", "door": "open", "mystery": 42})
    assert device.extra == {"mystery": 42}


def test_merged_with_partial_update_preserves_known_fields():
    base = OrbitDevice.from_dict(
        {"id": "d1", "name": "Main", "door": "closed", "light": True, "battery": 80}
    )
    # A thin push that only reports a new door position.
    push = OrbitDevice.from_dict({"id": "d1", "door": "opening"})

    merged = base.merged_with(push)
    assert merged.door_state is DoorState.OPENING
    # Name/light/battery were not in the push -> keep the known values.
    assert merged.name == "Main"
    assert merged.light_on is True
    assert merged.battery_level == 80


def test_merged_with_updates_light_only():
    base = OrbitDevice.from_dict({"id": "d1", "door": "open", "light": False})
    push = OrbitDevice.from_dict({"id": "d1", "light": True})
    merged = base.merged_with(push)
    assert merged.light_on is True
    assert merged.door_state is DoorState.OPEN
