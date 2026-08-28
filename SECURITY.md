# Security & privacy

This project is a **Home Assistant custom integration**. There is no server operated by
the maintainers and no telemetry phoning home. Everything below describes what the
integration does on _your_ Home Assistant instance.

## What data the integration touches

| Data                                 | Stored                             | Leaves your machine?                                                           |
| ------------------------------------ | ---------------------------------- | ------------------------------------------------------------------------------ |
| CarLinko email + password            | Home Assistant config entry        | Only to **CarLinko's own cloud** over HTTPS, to log in — like the official app |
| Auth token                           | HA storage (`CarlinkoStore`)       | Sent back to CarLinko's cloud on each request                                  |
| Live telemetry                       | In-memory (coordinator / entities) | No (unless you log or export it yourself)                                      |
| Cost knobs (tariff, petrol price, …) | HA storage                         | No                                                                             |

**Optional `engine/` CLI** (dev / debugging only): email/password/region in a gitignored
`.env`; token and vehicle ids via the same `CarlinkoStore` class, file-backed to
`data/config.json` (also gitignored). Same outbound destinations as the integration.

**No analytics, no tracking, no third-party backend.** Outbound traffic is to CarLinko's
cloud only (WebSocket + REST for login and remote control).

## Your responsibilities

- **Never commit** `.env`, `config.json`, tokens, passwords, VIN, or plate.
- Prefer a **second CarLinko account** when possible so a shared session isn’t tied to
  your primary phone login (CarLinko often allows only one active session).
- Remote control is **real actuation** — use only on a vehicle you own.

## How auth works (for the curious)

- The CarLinko request signing key is an **app-global constant** (identical in every
  install of the official app), so bundling it exposes nothing your own APK doesn't
  already contain.

## Reporting a vulnerability

Found something? **Please report it privately first** — don't open a public issue with
exploit details. Use
[GitHub private vulnerability reporting](https://github.com/elad-bar/ha-carlinko/security/advisories/new)
(Security tab → _Report a vulnerability_).

This is a hobby project with no warranty — see [LICENSE](LICENSE).
