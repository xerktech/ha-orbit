"""Data models for :mod:`orbitclient`.

Plain dataclasses (no Home Assistant coupling) parsed from the hub objects the
Orbit cloud sends over MQTT. A real hub object looks like::

    {
      "hub_id": "AbC12xYz", "hub_name": "Single Door", "type": "GDO",
      "online": true, "timezone_id": "America/New_York",
      "reported": {
        "mdev": {"door": 4, "rssi": -79, "ssid": "...", "autoclose_en": 0,
                 "firstdoor": {"door": 4}, "fw": {"type": "1", "ver": "WF..."}},
        "sdev": {"appliance": [], "sensor": []}
      }
    }

State pushes (``/update/result``) carry only ``hub_id`` + ``reported``, so
:meth:`OrbitDevice.merged_with` overlays them onto the last full snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import IntEnum, StrEnum
from typing import Any


class DoorState(StrEnum):
    """Normalised garage door position/motion state."""

    OPEN = "open"
    CLOSED = "closed"
    OPENING = "opening"
    CLOSING = "closing"
    #: Stopped part-way (the app shows a "half open" door).
    STOPPED = "stopped"
    UNKNOWN = "unknown"


#: ``reported.mdev.door`` values, from the app's door-icon switch.
_DOOR_CODES: dict[int, DoorState] = {
    0: DoorState.OPENING,
    1: DoorState.OPEN,
    2: DoorState.STOPPED,
    3: DoorState.CLOSING,
    4: DoorState.CLOSED,
    6: DoorState.STOPPED,
    7: DoorState.UNKNOWN,
}


def parse_door_state(raw: Any) -> DoorState:
    """Map a raw ``door`` code onto a :class:`DoorState`."""
    try:
        return _DOOR_CODES.get(int(raw), DoorState.UNKNOWN)
    except (TypeError, ValueError):
        return DoorState.UNKNOWN


class DoorSensorStatus(IntEnum):
    """``firstdoor.GS`` - status of the optional wireless door-position sensor."""

    NOT_INSTALLED = 0
    OK = 1
    LOW_BATTERY = 2
    LOST = 3


@dataclass(slots=True)
class OrbitAccount:
    """Result of a successful REST login."""

    acc_no: str
    alias_name: str | None = None


@dataclass(slots=True)
class OrbitDevice:
    """A single Orbit hub (garage door opener) and its current state."""

    device_id: str
    name: str
    model: str | None = None
    online: bool = True
    door_state: DoorState = DoorState.UNKNOWN
    #: Last direction of travel seen (OPENING/CLOSING). A button press from
    #: STOPPED reverses this, so it decides what "open"/"close" must do.
    last_motion: DoorState | None = None
    door_sensor: DoorSensorStatus | None = None
    autoclose_enabled: bool | None = None
    wifi_rssi: int | None = None
    wifi_ssid: str | None = None
    firmware: str | None = None
    timezone: str | None = None
    #: Raw ``reported`` block, kept for diagnostics.
    reported: dict[str, Any] = field(default_factory=dict)

    @property
    def has_light(self) -> bool:
        """Whether the opener has a (toggle-only) light - GDO models do."""
        return (self.model or "").upper() == "GDO"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrbitDevice:
        """Build a device from a full hub object (``/get/result`` entry)."""
        hub_id = data.get("hub_id")
        if not hub_id:
            raise KeyError("hub payload contained no hub_id")
        device = cls(
            device_id=str(hub_id),
            name=str(data.get("hub_name") or data.get("location") or f"Orbit {hub_id}"),
            model=data.get("type"),
            online=bool(data.get("online", True)),
            timezone=data.get("timezone_id") or data.get("timezone"),
        )
        return device._apply_reported(data.get("reported"))

    def merged_with(self, update: dict[str, Any]) -> OrbitDevice:
        """Return a copy updated by a (possibly partial) push payload."""
        merged = replace(self)
        if "online" in update:
            merged.online = bool(update["online"])
        if update.get("hub_name"):
            merged.name = str(update["hub_name"])
        return merged._apply_reported(update.get("reported"))

    def _apply_reported(self, reported: Any) -> OrbitDevice:
        if not isinstance(reported, dict):
            return self
        self.reported = {**self.reported, **reported}
        mdev = reported.get("mdev")
        if not isinstance(mdev, dict):
            return self

        # mdev.door is authoritative for GDO (it leads firstdoor.door by a beat).
        if "door" in mdev:
            self.door_state = parse_door_state(mdev["door"])
            if self.door_state in (DoorState.OPENING, DoorState.CLOSING):
                self.last_motion = self.door_state
        if "rssi" in mdev:
            self.wifi_rssi = _as_optional_int(mdev["rssi"])
        if mdev.get("ssid"):
            self.wifi_ssid = str(mdev["ssid"])
        if "autoclose_en" in mdev:
            self.autoclose_enabled = _as_optional_bool(mdev["autoclose_en"])
        fw = mdev.get("fw")
        if isinstance(fw, dict) and (fw.get("ver") or fw.get("ver_gdo")):
            self.firmware = str(fw.get("ver") or fw.get("ver_gdo"))
        first = mdev.get("firstdoor")
        if isinstance(first, dict) and "GS" in first:
            try:
                self.door_sensor = DoorSensorStatus(int(first["GS"]))
            except (TypeError, ValueError):
                self.door_sensor = None
        return self


def _as_optional_bool(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    try:
        return int(raw) != 0
    except (TypeError, ValueError):
        return None


def _as_optional_int(raw: Any) -> int | None:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None
