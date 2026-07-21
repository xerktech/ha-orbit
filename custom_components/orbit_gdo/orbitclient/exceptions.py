"""Exceptions raised by :mod:`orbitclient`."""

from __future__ import annotations


class OrbitError(Exception):
    """Base error for all client failures."""


class OrbitCannotConnect(OrbitError):
    """Raised when the cloud service is unreachable or returns a 5xx."""


class OrbitTimeout(OrbitCannotConnect):
    """Raised when a request exceeds the configured timeout."""


class OrbitAuthError(OrbitError):
    """Raised when credentials are rejected or a token has expired."""


class OrbitCommandError(OrbitError):
    """Raised when a device rejects a command or reports a fault."""
