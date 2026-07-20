"""Test configuration.

The ``orbitclient`` package lives inside ``custom_components/orbit_gdo`` so it
ships with the integration, but it has no Home Assistant dependency. To exercise
it in isolation (without importing Home Assistant), we put that directory on
``sys.path`` and import ``orbitclient`` as a top-level package.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CLIENT_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "orbit_gdo"
if str(_CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLIENT_ROOT))


@pytest.fixture
async def session():
    """Provide an aiohttp ClientSession closed after the test."""
    import aiohttp

    async with aiohttp.ClientSession() as client_session:
        yield client_session
