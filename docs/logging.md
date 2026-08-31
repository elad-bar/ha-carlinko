# Logging standard (CarLinko integration)

Guidance for **developers** adding or changing logs in `custom_components/carlinko/`.
Operators tuning Home Assistant should use the [README troubleshooting](../README.md#troubleshooting)
section; this doc defines **levels**, **message shape**, and **layering** so logs stay
readable at `info` and actionable at `warning`.

## Safety

- Never log passwords, tokens, sign keys, or full API/WS response bodies.
- Redact identifiers: `partial_id()` for vehicle IDs and entry IDs in user-visible lines;
  `mask_email()` for email on config-flow submit lines.
- Vendor login failures may include **code** and **msg** from the API (already sanitized by CarLinko).

## INFO vs DEBUG

They are not two verbosity settings for the same fact.

| | **INFO** | **DEBUG** |
| --- | --- | --- |
| Answers | What happened that matters for this flow? | How did the code get there? |
| Examples | `config flow created entry`, `CarLinko started`, `fleet change`, `remoteControl … code=` | `async_start → api.login`, `GET /user/vehicle`, WS connect attempt, entity key lists |
| Avoid | Internal call chains, HTTP method paths, per-platform reconcile spam | User-visible milestones or failures only at DEBUG |

**Pairing:** DEBUG (path/attempt) → INFO or WARNING (outcome).

```text
DEBUG    _validate_login → ApiClient.login
INFO     login ok region=sea …
```

```text
DEBUG    _validate_login → ApiClient.login
WARNING  login failed code=9997 msg=…
WARNING  config flow failed step=user error=invalid_auth …
```

**Wrong:** auth or config errors at DEBUG only; successes or failures duplicated at both INFO and DEBUG for the same fact.

Between two INFO milestones in a flow, there should be enough DEBUG to trace the path when `custom_components.carlinko: debug` is enabled.

## Levels

| Level | Use for |
| ----- | ------- |
| **debug** | Call chain, retries, cache/indexing, WS frames, `adding N entities` key lists |
| **info** | Milestones and results: flow/option/reauth start or success, setup/reload/unload, `login ok`, `vehicle list refreshed count=N`, `CarLinko started`, `fleet change` / `capability change`, `remote action`, `remoteControl … code=`, platforms complete |
| **warning** | Expected failures the operator can fix or tolerate: bad credentials, vendor non-OK codes, stale token (before reauth), no vehicles, WS setup timeout, control rejected, local config validation rejected |
| **error** | Integration cannot continue without user action: `starting reauth flow`, setup auth failed, WS/caps auth dead |
| **exception** | Unexpected bugs (`exc_info=True`): uncaught setup failure, listener crash, shutdown task failure, store save failure |

## Config and options flows

- **Region** is set only when adding the integration (`entry.data`); the options flow does not include or log region.
- User-facing validation failures → **warning** at `config_flow` (with `step=…` and `error=…`) and vendor detail at **api_client** where applicable.
- Flow boundaries (started, submit, created entry, success reload, abort) → **info**.
- Options saved → **info** e.g. `options saved stream_backstop=20 availability_seconds=2400`.
- Missing or invalid region on reauth or setup → **error** at `config_flow` or `coordinator` (`setup failed entry_id=… missing required config data key=region`).
- Unexpected exceptions in a flow step → **exception** if truly unknown; handled cases → **warning** with context.

## Lifecycle (`__init__.py`)

- **info:** `setup entry`, `unload entry`, `unload platforms ok=…`, `reload entry … reason=update_listener`, `remove entry … store deleted`, `platforms setup complete count=N`
- **error:** `setup auth failed entry_id=…` on `ConfigEntryAuthFailed`
- **debug:** unload/reload/setup sub-steps (`async_unload_entry begin`, forward platforms count)

Use `(existing entry)` on setup when `entry.runtime_data` is already set (reload/boot after first load).

## Coordinator

- **info:** `coordinator starting` / `coordinator stopping` / `coordinator stopped`, `CarLinko started`, `fleet change added=[…] removed=[…]`, `vehicle added starting ws …`, `vehicle removed stopping ws …`, `device registry removed vehicle=…`, `capability change vehicle=… added=[…] removed=[…]`
- **debug:** store loaded, `async_start → …`, `_async_wait_for_stream satisfied`, `_caps_refresh_loop`, `async_send_control opcode=…` / `result ok`
- **warning:** `no vehicle websocket connected within …s`, `auth failure source={setup\|ws\|caps_refresh\|control} …`, remote control stale/failed
- **error:** `starting reauth flow entry_id=…`, `setup failed entry_id=…` (missing/invalid region), then context lines (`WebSocket auth failed …`, `Caps refresh auth failed …`)

Fleet membership: **one INFO summary** at coordinator; per-platform entity reconcile → **debug** in `entity_setup` (not 11× INFO).

## API and WebSocket

- **info:** `login ok`, `vehicle list refreshed count=N`, `remoteControl opcode=… code=…`, WS `streaming CarLinko WS …`, WS recovery `websocket login ok after token refresh`
- **debug:** `GET /user/vehicle`, `POST /user/vehicle/remoteControl`, stale-token retry, connect attempts, push frames
- **warning:** `login failed`, `/user/vehicle returned no vehicles`, `remoteControl failed`, `remoteControl skipped vehicle_id/device_sn missing`, caps parse failures

## Entities

- **base_entity:** **info** `remote action entity=… action=… vehicle=… opcode=…`; **warning** `remote action failed no opcode …`
- **number / store:** **info** successful `local config set`; **warning** validation rejected (no success INFO on failed set); **debug** save path; **exception** on persist failure

## Message style

- Prefer stable, grep-friendly prefixes: `config flow failed step=user`, `auth failure source=ws`, `fleet change`, `capability change`.
- Use `partial_id()` for IDs in messages; full vehicle IDs only where existing code already logs them for availability transitions.
- Avoid triple-logging the same auth failure (flow + api once each is enough).

## Logger modules

| Logger | Module |
| ------ | ------ |
| `custom_components.carlinko` | `__init__.py` |
| `custom_components.carlinko.config_flow` | `config_flow.py` |
| `custom_components.carlinko.common.entity_setup` | `entity_setup.py` |
| `custom_components.carlinko.common.base_entity` | `base_entity.py` |
| `custom_components.carlinko.number` | `number.py` |
| `custom_components.carlinko.managers.coordinator` | `coordinator.py` |
| `custom_components.carlinko.managers.api_client` | `api_client.py` |
| `custom_components.carlinko.managers.ws_client` | `ws_client.py` |
| `custom_components.carlinko.managers.store` | `store.py` |

HA registers the parent logger in `manifest.json` (`loggers`: `custom_components.carlinko`).

## Testing log changes

- Use `caplog` in pytest; assert **warning** for operator-visible failures, not DEBUG-only.
- After changes, spot-check mentally at three HA levels:
  - **`info`:** milestones only — add integration or boot should tell a short story.
  - **`warning`:** failures visible without success noise.
  - **`debug`:** path between INFO lines is reconstructible.

Example operator config:

```yaml
logger:
  logs:
    custom_components.carlinko: info      # default recommendation
    # custom_components.carlinko: debug   # development / support
    # custom_components.carlinko: warning # problems-only tail
```

## Operational flows (where to log)

When touching code, know which flow you are in:

1. Add account — `config_flow` + first `async_setup_entry`
2. Lifecycle — setup, reload, unload, remove, options, reauth
3. Reauth / runtime auth — `_async_handle_auth_failure`, WS/caps/control paths
4. Fleet change — `_sync_vehicles_from_rows`
5. Capability change — `_maybe_notify_spec_changes` + `entity_setup`
6. Local entity action — cost `number` + `store`
7. Remote entity action — `base_entity` → `async_send_control` → `api_client.send_control`

New logs should fit the level rules for that flow without duplicating another layer’s outcome.
