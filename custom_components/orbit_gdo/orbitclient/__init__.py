"""Standalone async client for the Skylink Orbit Home cloud.

Free of Home Assistant imports so it can be unit-tested and reused in isolation.
The protocol (signed REST login + MQTT over TLS) was recovered from the Orbit
Home Android app (``com.mtqqdemo.skylink``) - see ``const.py``.
"""

from .client import OrbitClient
from .exceptions import (
    OrbitAuthError,
    OrbitCannotConnect,
    OrbitCommandError,
    OrbitError,
    OrbitTimeout,
)
from .models import DoorSensorStatus, DoorState, OrbitAccount, OrbitDevice

__all__ = [
    "DoorSensorStatus",
    "DoorState",
    "OrbitAccount",
    "OrbitAuthError",
    "OrbitCannotConnect",
    "OrbitClient",
    "OrbitCommandError",
    "OrbitDevice",
    "OrbitError",
    "OrbitTimeout",
]
