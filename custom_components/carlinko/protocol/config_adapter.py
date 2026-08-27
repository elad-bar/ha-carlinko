"""Abstract config store used by ApiClient / VehicleState (file or HA Store)."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConfigAdapter(Protocol):
    """Minimal persistence surface shared by file-backed and HA-backed stores."""

    data: dict[str, Any]

    def load(self) -> dict[str, Any]:
        ...

    def save(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        ...

    def update(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def set_token(self, token: str | None) -> dict[str, Any]:
        ...

    def get_cost_config(self) -> dict[str, Any]:
        ...

    def set_cost_config(self, key: str, value: Any) -> dict[str, Any]:
        ...

    def get_vehicle(self) -> dict[str, Any]:
        ...

    def get_vehicle_id(self) -> str:
        ...
