# Orbit Garage Door Opener — Home Assistant integration spec

> **Historical.** This is the original design spec, written before the protocol
> was known; its endpoint/host assumptions (`api.orbit.skylinkhome.com`,
> `/v1/...`) were placeholders. The real, hardware‑verified protocol is
> documented in [`orbitclient/const.py`](custom_components/orbit_gdo/orbitclient/const.py).

## 1. Problem & scope

Skylink sells Wi‑Fi garage door openers — the **Atoms**, **Atoms Pro**, and the
**Nova** universal controller — driven by the **Orbit Home** mobile app
(iOS `id1375796623`, Android `com.mtqqdemo.skylink`). The app does open/close/stop,
reports door state, toggles the opener light, sends open/closed push
notifications, and supports shared users.

**As of this writing there is no Home Assistant integration, Homebridge plugin,
or documented API for these openers.** The only adjacent HA project is
`bhyve-home-assistant`, which targets **Orbit Irrigation's B‑hyve** sprinkler
controllers — a different company that merely shares the word "Orbit". A stale
Home Assistant "SkylinkNet hub" feature request never produced code.

This repo provides:

1. a **standalone async client** (`custom_components/orbit_gdo/orbitclient/`) for
   the Orbit cloud, with no Home Assistant coupling, and
2. a **HACS custom integration** (`custom_components/orbit_gdo/`) exposing each
   opener as a `cover`, plus `light`, `binary_sensor`, and diagnostic `sensor`
   entities.

### In scope (v0.1)

- Cloud login with token refresh + HA reauth flow.
- Enumerate openers; expose door as a `garage` cover (open/close/stop).
- Opener light as an on/off `light` (when the device reports one).
- Obstruction + connectivity `binary_sensor`s; Wi‑Fi/battery diagnostic sensors.
- Optional realtime push over MQTT, with automatic fallback to polling.

### Out of scope (v0.1)

- Local/LAN control (the openers are cloud‑only).
- User/share management, event‑log history, firmware updates.
- Multi‑region account routing beyond a configurable base URL.

## 2. ⚠️ Protocol status — this is the one thing that needs hardware

Skylink publishes no API and the app ships no useful public documentation. The
request/response shapes in this codebase are a **structured best guess** derived
from the app's behaviour and its package name (`com.mtqqdemo.skylink` →
"mqtt demo skylink", i.e. an MQTT‑backed realtime cloud). **They must be
confirmed against a real packet capture before the integration will talk to a
physical opener.**

The code is deliberately arranged so that confirming the protocol is a *small,
localized* change:

| What you learn from a capture      | Where it goes                                   |
| ---------------------------------- | ----------------------------------------------- |
| Real hostnames / paths / ports     | `orbitclient/const.py` (or config‑flow override) |
| Login request & response JSON      | `OrbitToken.from_dict` in `orbitclient/models.py` |
| Device‑list / status JSON          | `OrbitDevice.from_dict` in `orbitclient/models.py` |
| Command verbs / payloads           | `orbitclient/const.py` (`CMD_*`) + `async_send_command` |
| MQTT topics / auth                 | `orbitclient/const.py` + `orbitclient/transport.py` |

Everything else (auth lifecycle, retry, coordinator, entities, tests) is
protocol‑independent and already complete.

### 2.1 How to capture the protocol

1. Install **mitmproxy** on a computer; note its CA cert.
2. On an **Android** device/emulator, install the Orbit Home app. Modern Android
   distrusts user CAs for app traffic, so either use an emulator with a writable
   system partition (`emulator -writable-system`, push the mitm cert into
   `/system/etc/security/cacerts`) or a rooted device. Point the device's Wi‑Fi
   proxy at mitmproxy.
3. If the app uses **certificate pinning**, bypass it with Frida + a pinning
   bypass script, or `objection`, against the app process.
4. Drive the app: sign in, list devices, open/close the door, toggle the light.
   Capture the `login`, device‑list, and command requests, and watch for an MQTT
   `CONNECT`/`SUBSCRIBE` to learn the broker host, port, topics, and credentials.
5. Transcribe the confirmed hosts/paths/JSON into the files in the table above.
   The unit tests in `tests/` document the *assumed* shapes — update those
   fixtures to the real ones and keep them green.

Until then, users can already point the integration at a captured host without
editing source: the config flow exposes **API base URL** and **MQTT host** as
advanced fields.

## 3. Assumed cloud architecture

```
Home Assistant ──HTTPS(REST)──► api.orbit.skylinkhome.com   (auth, devices, commands)
       ▲                                                     (poll every 30s)
       └────────MQTT/TLS 8883──── mqtt.orbit.skylinkhome.com (optional status push)
```

- **Auth**: `POST /v1/auth/login {email,password}` → `{access_token, refresh_token,
  user_id, expires_in}`. Bearer token on subsequent calls; `401/403` → refresh,
  then re‑login. HA's reauth flow fires if credentials are permanently rejected.
- **Devices**: `GET /v1/devices` → list of `{id, name, model, online, state:{door,
  light, obstruction, rssi, battery}}`. Envelope‑tolerant (`devices`/`data`/bare
  list all accepted).
- **Commands**: `POST /v1/devices/{id}/command {command}` where `command` ∈
  `open|close|stop|light_on|light_off`.
- **Realtime**: MQTT subscribe `orbit/{user_id}/{device_id}/status`; each message
  is a (possibly partial) device JSON that is merged into the cached snapshot.
  If MQTT is unreachable the integration silently keeps polling.

Door‑state strings are normalised (`open/opened/1`, `closed/close/0`, `opening`,
`closing`, `stopped/partial/ajar`) in `parse_door_state`, so vendor spelling
variants don't leak upward.

## 4. Home Assistant surface

| Platform         | Entity                    | Notes                                             |
| ---------------- | ------------------------- | ------------------------------------------------- |
| `cover`          | Garage door               | `device_class=garage`; OPEN/CLOSE/STOP.           |
| `light`          | Opener light              | On/off; only if the device reports a light.       |
| `binary_sensor`  | Obstruction               | `PROBLEM`; only if reported.                       |
| `binary_sensor`  | Connectivity              | `CONNECTIVITY`; disabled by default.               |
| `sensor`         | Wi‑Fi signal / Battery    | Diagnostic; only if reported; RSSI disabled by default. |

All entities share one HA **device** per opener. State comes from a single
`DataUpdateCoordinator` keyed by `device_id`; commands call the client then
request a coordinator refresh (a realtime push usually wins the race).

Config entry `unique_id` = the cloud `user_id` (falls back to the lowercased
email), so the same account can't be added twice.

## 5. Testing & CI

- `orbitclient` is unit‑tested with `aioresponses` (no network, no HA import):
  login/refresh/expiry, device‑list envelope + status parsing, command verbs,
  auth‑error → reauth signalling, and realtime merge via a fake transport.
- CI (GitHub Actions): `ruff` lint/format check + `pytest`, plus HACS repo
  validation. `hassfest`‑style manifest correctness is covered by keeping the
  manifest to the required schema.

## 6. Roadmap

- v0.1 — this spec + client + entities + tests (protocol assumed).
- v0.2 — wire confirmed endpoints from a capture; add fixtures from real traffic.
- v0.3 — obstruction/lock entities as hardware reveals them; HA brands PR so the
  integration ships an icon; submit to HACS default repositories.
