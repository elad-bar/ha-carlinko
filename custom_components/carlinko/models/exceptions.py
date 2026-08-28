"""Protocol-layer errors (HA-free)."""

from __future__ import annotations


class AuthError(Exception):
    """Credentials rejected or session cannot be renewed with stored password."""
