"""Spec-driven entity factory add/remove (caps / fleet)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.carlinko.common.entity_setup import async_setup_entities
from custom_components.carlinko.models.entity_specs import get_entity_specs


def _mock_coordinator(*, vehicle_ids: list[str], state: dict, caps: dict) -> MagicMock:
    coordinator = MagicMock()
    coordinator.vehicle_ids = list(vehicle_ids)
    coordinator.vehicle_data.return_value = state
    coordinator.caps_for.return_value = caps
    coordinator._listener = None

    def register(listener):
        coordinator._listener = listener
        return MagicMock()

    coordinator.register_entity_listener.side_effect = register
    return coordinator


def _factory(coordinator, spec, vehicle_id):
    entity = MagicMock()
    entity.spec = spec
    entity.vehicle_id = vehicle_id
    entity.hass = MagicMock()
    entity.async_remove = MagicMock()
    return entity


@pytest.mark.asyncio
async def test_initial_setup_adds_cap_gated_entities() -> None:
    hass = MagicMock()
    entry = MagicMock()
    added: list = []

    def async_add_entities(entities):
        added.extend(entities)

    coordinator = _mock_coordinator(
        vehicle_ids=["veh-1"],
        state={"vehicle": {"plate": "P", "model": "M"}},
        caps={"lock": True},
    )
    async_setup_entities(hass, entry, coordinator, "lock", async_add_entities, _factory)
    keys = {e.spec.key for e in added}
    assert "lock" in keys
    entry.async_on_unload.assert_called_once()


@pytest.mark.asyncio
async def test_caps_change_removes_and_adds_entities() -> None:
    hass = MagicMock()
    entry = MagicMock()
    added: list = []

    def async_add_entities(entities):
        added.extend(entities)

    state = {"vehicle": {"plate": "P", "model": "M"}}
    caps = {"lock": True}
    coordinator = _mock_coordinator(vehicle_ids=["veh-1"], state=state, caps=caps)
    async_setup_entities(hass, entry, coordinator, "lock", async_add_entities, _factory)
    assert {e.spec.key for e in added} == {"lock"}
    lock_entity = added[0]

    # Drop lock cap → listener should remove the entity.
    caps.clear()
    wanted = get_entity_specs(platform="lock", state=state, caps=caps)
    assert not any(s.key == "lock" for s in wanted)
    coordinator._listener("veh-1", set(), {"lock"})
    lock_entity.async_remove.assert_called_once_with(force_remove=True)
    hass.async_create_task.assert_called()

    # Restore lock cap → add again.
    added.clear()
    caps["lock"] = True
    coordinator._listener("veh-1", {"lock"}, set())
    assert {e.spec.key for e in added} == {"lock"}


@pytest.mark.asyncio
async def test_phev_flag_adds_fuel_sensors() -> None:
    hass = MagicMock()
    entry = MagicMock()
    added: list = []

    def async_add_entities(entities):
        added.extend(entities)

    state = {"vehicle": {"plate": "P", "model": "M"}, "powertrain": "bev"}
    coordinator = _mock_coordinator(vehicle_ids=["veh-1"], state=state, caps={})
    async_setup_entities(
        hass, entry, coordinator, "sensor", async_add_entities, _factory
    )
    initial_keys = {e.spec.key for e in added}
    assert "fuel_range" not in initial_keys

    # Flip to PHEV and notify added keys from catalog.
    added.clear()
    state["powertrain"] = "phev"
    phev_keys = {
        s.key
        for s in get_entity_specs(platform="sensor", state=state, caps={})
        if s.when == "phev"
    }
    assert "fuel_range" in phev_keys
    coordinator._listener("veh-1", phev_keys, set())
    assert "fuel_range" in {e.spec.key for e in added}


@pytest.mark.asyncio
async def test_fleet_notify_reconciles_wanted_set() -> None:
    hass = MagicMock()
    entry = MagicMock()
    added: list = []

    def async_add_entities(entities):
        added.extend(entities)

    state = {"vehicle": {"plate": "P", "model": "M"}}
    caps = {"lock": True}
    coordinator = _mock_coordinator(vehicle_ids=["veh-1"], state=state, caps=caps)
    async_setup_entities(hass, entry, coordinator, "lock", async_add_entities, _factory)
    assert len(added) == 1
    first = added[0]

    # Second vehicle appears; fleet notify with empty vehicle_id.
    added.clear()
    coordinator.vehicle_ids = ["veh-1", "veh-2"]
    coordinator._listener("", set(), set())
    assert any(e.vehicle_id == "veh-2" and e.spec.key == "lock" for e in added)

    # Drop second vehicle; fleet reconcile removes its entity.
    veh2 = next(e for e in added if e.vehicle_id == "veh-2")
    coordinator.vehicle_ids = ["veh-1"]
    coordinator._listener("", set(), set())
    veh2.async_remove.assert_called_once_with(force_remove=True)
    first.async_remove.assert_not_called()
