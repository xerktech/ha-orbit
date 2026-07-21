"""Standalone async client for the Skylink Orbit Home cloud API.

This package is deliberately free of any Home Assistant imports so that it can
be unit-tested (and reused) in isolation. The Home Assistant integration in the
parent package wraps it.

The exact wire protocol used by the Orbit Home app (`com.mtqqdemo.skylink`) is
not publicly documented. The request/response shapes implemented here follow the
architecture described in ``SPEC.md`` and are isolated behind small parse helpers
so that adjusting them to match a real packet capture is a localized change.
"""

from .client import OrbitClient
from .exceptions import (
    OrbitAuthError,
    OrbitCannotConnect,
    OrbitError,
    OrbitTimeout,
)
from .models import DoorState, OrbitDevice, OrbitToken

__all__ = [
    "DoorState",
    "OrbitAuthError",
    "OrbitCannotConnect",
    "OrbitClient",
    "OrbitDevice",
    "OrbitError",
    "OrbitTimeout",
    "OrbitToken",
]
