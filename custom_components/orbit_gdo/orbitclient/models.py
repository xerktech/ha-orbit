"""Data models for :mod:`orbitclient`.

These are plain dataclasses (no Home Assistant coupling) built by parsing the
JSON returned by the Orbit cloud API. Parsing is tolerant: unknown fields are
ignored and missing optional fields fall back to sensible defaults, so a minor
server-side schema change does not hard-fail the whole integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DoorState(StrEnum):
    """Normalised garage door position/motion state.

    The raw string reported by the cloud is mapped onto these values in
    :meth:`OrbitDevice.from_dict` so downstream code never has to reason about
    vendor spelling variants (``"OPEN"`` vs ``"opened"`` etc.).
    """

    OPEN = "open"
    CLOSED = "closed"
    OPENING = "opening"
    CLOSING = "closing"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


# Maps every raw token we have seen / expect from the cloud onto a DoorState.
# Extend this table when a packet capture reveals additional spellings rather
# than scattering conditionals through the code.
_DOOR_STATE_ALIASES: dict[str, DoorState] = {
    "open": DoorState.OPEN,
    "opened": DoorState.OPEN,
    "1": DoorState.OPEN,
    "closed": DoorState.CLOSED,
    "close": DoorState.CLOSED,
    "0": DoorState.CLOSED,
    "opening": DoorState.OPENING,
    "closing": DoorState.CLOSING,
    "stopped": DoorState.STOPPED,
    "stop": DoorState.STOPPED,
    "partial": DoorState.STOPPED,
    "ajar": DoorState.STOPPED,
}


def parse_door_state(raw: Any) -> DoorState:
    """Map a raw cloud value onto a :class:`DoorState`."""
    if raw is None:
        return DoorState.UNKNOWN
    return _DOOR_STATE_ALIASES.get(str(raw).strip().lower(), DoorState.UNKNOWN)


@dataclass(slots=True)
class OrbitToken:
    """An authenticated session returned by the login endpoint."""

    access_token: str
    refresh_token: str | None = None
    user_id: str | None = None
    #: Absolute epoch seconds at which ``access_token`` expires, if known.
    expires_at: float | None = None
    #: Optional per-session MQTT credentials, if the cloud hands them out at
    #: login instead of reusing the bearer token.
    mqtt_username: str | None = None
    mqtt_password: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrbitToken:
        """Build a token from a login response body."""
        access = (
            data.get("access_token")
            or data.get("accessToken")
            or data.get("token")
            or data.get("id_token")
        )
        if not access:
            raise KeyError("login response contained no access token")
        # Note: a relative "expires_in" is intentionally *not* consumed here.
        # The model is clock-free; OrbitClient.async_login derives the absolute
        # expiry from "now" + expires_in. Only an absolute expiry is honoured.
        expires_at = data.get("expires_at") or data.get("expiresAt")
        return cls(
            access_token=str(access),
            refresh_token=data.get("refresh_token") or data.get("refreshToken"),
            user_id=(
                data.get("user_id")
                or data.get("userId")
                or data.get("uid")
                or data.get("sub")
            ),
            # expires_at is derived by the client (it knows "now"); models must
            # stay clock-free so they remain trivially testable.
            expires_at=float(expires_at) if expires_at is not None else None,
            mqtt_username=data.get("mqtt_username") or data.get("mqttUsername"),
            mqtt_password=data.get("mqtt_password") or data.get("mqttPassword"),
        )


@dataclass(slots=True)
class OrbitDevice:
    """A single Orbit garage door opener and its current state."""

    device_id: str
    name: str
    model: str | None = None
    online: bool = True
    door_state: DoorState = DoorState.UNKNOWN
    #: Whether the opener's built-in light is on. ``None`` if the device has no
    #: controllable light.
    light_on: bool | None = None
    #: Whether the safety beam is obstructed. ``None`` if unknown/unsupported.
    obstructed: bool | None = None
    battery_level: int | None = None
    wifi_rssi: int | None = None
    firmware: str | None = None
    #: Everything else the cloud reported, kept for diagnostics.
    extra: dict[str, Any] = field(default_factory=dict)

    _KNOWN_KEYS = frozenset(
        {
            "id",
            "device_id",
            "deviceId",
            "uuid",
            "name",
            "device_name",
            "label",
            "model",
            "type",
            "online",
            "is_online",
            "connected",
            "status",
            "state",
            "door",
            "door_state",
            "doorStatus",
            "position",
            "light",
            "light_on",
            "lightStatus",
            "obstruction",
            "obstructed",
            "battery",
            "battery_level",
            "rssi",
            "wifi_rssi",
            "signal",
            "firmware",
            "fw_version",
        }
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrbitDevice:
        """Build a device from a device-list or status-update payload.

        Both the REST device list and MQTT status pushes are expected to share
        this shape (the push may be a partial — see :meth:`merged_with`).
        """
        device_id = (
            data.get("id")
            or data.get("device_id")
            or data.get("deviceId")
            or data.get("uuid")
        )
        if not device_id:
            raise KeyError("device payload contained no id")

        # Status can be nested under "state"/"status" or flattened at the top.
        state = data.get("state") or data.get("status") or {}
        if not isinstance(state, dict):
            state = {}

        def pick(*keys: str) -> Any:
            for key in keys:
                if key in data and data[key] is not None:
                    return data[key]
                if key in state and state[key] is not None:
                    return state[key]
            return None

        online_raw = pick("online", "is_online", "connected")
        light_raw = pick("light", "light_on", "lightStatus")
        obstruction_raw = pick("obstruction", "obstructed")

        extra = {
            key: value for key, value in data.items() if key not in cls._KNOWN_KEYS
        }

        return cls(
            device_id=str(device_id),
            name=str(
                data.get("name")
                or data.get("device_name")
                or data.get("label")
                or f"Orbit {device_id}"
            ),
            model=data.get("model") or data.get("type"),
            online=_as_bool(online_raw, default=True),
            door_state=parse_door_state(
                pick("door", "door_state", "doorStatus", "position")
            ),
            light_on=_as_optional_bool(light_raw),
            obstructed=_as_optional_bool(obstruction_raw),
            battery_level=_as_optional_int(pick("battery", "battery_level")),
            wifi_rssi=_as_optional_int(pick("rssi", "wifi_rssi", "signal")),
            firmware=pick("firmware", "fw_version"),
            extra=extra,
        )

    def merged_with(self, update: OrbitDevice) -> OrbitDevice:
        """Return a copy updated by a (possibly partial) status push.

        Fields left at their "unknown" sentinel in ``update`` do not overwrite
        the known value carried by ``self``. This lets a thin MQTT message that
        only reports, say, the door position update just that field.
        """
        return OrbitDevice(
            device_id=self.device_id,
            name=update.name
            if update.name and not update.name.startswith("Orbit ")
            else self.name,
            model=update.model or self.model,
            online=update.online,
            door_state=(
                update.door_state
                if update.door_state is not DoorState.UNKNOWN
                else self.door_state
            ),
            light_on=update.light_on if update.light_on is not None else self.light_on,
            obstructed=(
                update.obstructed if update.obstructed is not None else self.obstructed
            ),
            battery_level=(
                update.battery_level
                if update.battery_level is not None
                else self.battery_level
            ),
            wifi_rssi=update.wifi_rssi
            if update.wifi_rssi is not None
            else self.wifi_rssi,
            firmware=update.firmware or self.firmware,
            extra={**self.extra, **update.extra},
        )


def _as_bool(raw: Any, *, default: bool) -> bool:
    result = _as_optional_bool(raw)
    return default if result is None else result


def _as_optional_bool(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    text = str(raw).strip().lower()
    if text in {"1", "true", "on", "yes", "open", "opened"}:
        return True
    if text in {"0", "false", "off", "no", "closed", "close"}:
        return False
    return None


def _as_optional_int(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None
