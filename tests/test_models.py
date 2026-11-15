"""Model parsing tests, using payloads captured from real Skylink GDO hubs."""

from __future__ import annotations

from orbitclient.models import (
    DoorSensorStatus,
    DoorState,
    OrbitDevice,
    parse_door_state,
)

HUB = {
    "hub_id": "AbC12xYz",
    "online": True,
    "timezone": "GMT-5",
    "timezone_id": "America/New_York",
    "hub_type": "M",
    "hub_name": "Single Door",
    "location": "Single Door",
    "type": "GDO",
    "reported": {
        "mdev": {
            "autoclose_en": 0,
            "door": 4,
            "rssi": -79,
            "ssid": "MyWifi",
            "firstdoor": {"door": 4},
            "fw": {"type": "1", "ver": "WF2012021040204"},
        },
        "sdev": {"appliance": [], "sensor": []},
    },
}


def _push(door: int, autoclose: int = 0) -> dict:
    return {
        "hub_id": "AbC12xYz",
        "reported": {"mdev": {"autoclose_en": autoclose, "door": door, "rssi": -79}},
    }


def test_door_codes():
    assert parse_door_state(0) is DoorState.OPENING
    assert parse_door_state(1) is DoorState.OPEN
    assert parse_door_state(2) is DoorState.STOPPED
    assert parse_door_state(3) is DoorState.CLOSING
    assert parse_door_state(4) is DoorState.CLOSED
    assert parse_door_state(6) is DoorState.STOPPED
    assert parse_door_state(7) is DoorState.UNKNOWN
    assert parse_door_state(None) is DoorState.UNKNOWN
    assert parse_door_state("x") is DoorState.UNKNOWN


def test_parse_full_hub():
    d = OrbitDevice.from_dict(HUB)
    assert d.device_id == "AbC12xYz"
    assert d.name == "Single Door"
    assert d.model == "GDO"
    assert d.online is True
    assert d.door_state is DoorState.CLOSED
    assert d.wifi_rssi == -79
    assert d.wifi_ssid == "MyWifi"
    assert d.firmware == "WF2012021040204"
    assert d.autoclose_enabled is False
    assert d.door_sensor is None
    assert d.has_light is True
    assert d.timezone == "America/New_York"
    assert d.last_motion is None


def test_hub_without_autoclose_field():
    hub = {**HUB, "reported": {"mdev": {"door": 4, "rssi": -46}}}
    assert OrbitDevice.from_dict(hub).autoclose_enabled is None


def test_merge_sequence_tracks_motion():
    """Replays the real open -> stop -> close sequence from a capture."""
    d = OrbitDevice.from_dict(HUB)
    d = d.merged_with(_push(0))
    assert (d.door_state, d.last_motion) == (DoorState.OPENING, DoorState.OPENING)
    d = d.merged_with(_push(2, autoclose=1))
    assert d.door_state is DoorState.STOPPED
    assert d.last_motion is DoorState.OPENING
    assert d.autoclose_enabled is True
    d = d.merged_with(_push(3))
    assert d.last_motion is DoorState.CLOSING
    d = d.merged_with(_push(4))
    assert d.door_state is DoorState.CLOSED
    # Fields absent from the push are preserved.
    assert d.name == "Single Door" and d.firmware == "WF2012021040204"


def test_merge_does_not_mutate_original():
    d = OrbitDevice.from_dict(HUB)
    d.merged_with(_push(0))
    assert d.door_state is DoorState.CLOSED


def test_door_sensor_status():
    hub = {**HUB, "reported": {"mdev": {"door": 4, "firstdoor": {"door": 4, "GS": 2}}}}
    assert OrbitDevice.from_dict(hub).door_sensor is DoorSensorStatus.LOW_BATTERY
