# ha-orbit — Skylink Orbit garage door openers for Home Assistant

A custom Home Assistant integration (installable through the Marketplace, formerly
HACS) for **Skylink Orbit** Wi‑Fi garage door openers controlled by the
**Orbit Home** app (`com.mtqqdemo.skylink`).

Forked from [xerktech/ha-orbit](https://github.com/xerktech/ha-orbit), whose
integration scaffold used placeholder endpoints; this fork implements the real
protocol.

> **Not** the same as `bhyve-home-assistant` / `com.orbit.orbitsmarthome`, which
> are *Orbit Irrigation's* B‑hyve sprinklers — a different company that happens
> to share the name "Orbit".

## Status

✅ **Working against real hardware** (Skylink `GDO` hubs, firmware
`WF2012021040204`). The protocol was recovered from the Orbit Home Android app
and verified live:

* **Login** — signed REST call to `iot.skyhm.net:8444` (`cmd=act_login`).
* **Everything else** — MQTT over TLS to `iot.skyhm.net:1899`: device list,
  real‑time state pushes (≈1 s), and commands.

Details are in [`orbitclient/const.py`](custom_components/orbit_gdo/orbitclient/const.py).
Nova (`NOVA_A`/`NOVA_B`/`NVMini`) controllers are not yet supported.

## What you get

| Entity                     | Description                                                       |
| -------------------------- | ----------------------------------------------------------------- |
| Cover (`garage`)           | Open / close / stop, live state incl. opening/closing/part‑open   |
| Light                      | Opener light on/off (assumed state: the hub does not report it)   |
| Button "Door button"       | Raw wall‑button press (disabled by default)                       |
| Binary sensor              | Connectivity, auto‑close, door‑sensor battery/problem (diagnostic) |
| Sensor                     | Wi‑Fi signal (diagnostic, disabled by default)                    |

### How open / close work

The opener only accepts a single "button press" that cycles
*open → stop → close → stop → …*. The cover maps open/close/stop onto it using
the live state and the last direction of travel, and is idempotent (closing a
closed door does nothing). If a press would move the door the wrong way (e.g.
"close" while it is opening, or a part‑open door whose direction is unknown
after a restart), the command is refused instead of guessed — press **stop**
first, or use the **Door button** entity.

## Installation (Marketplace)

1. In the Marketplace, add `https://github.com/joesilva101/ha-orbit` as a
   **custom repository**, category **Integration**.
2. Install **Orbit Garage Door Opener (Skylink)**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Orbit** and sign in with
   your Orbit Home account (same email/password as the phone app).

## Manual installation

Copy `custom_components/orbit_gdo` into your Home Assistant `config/custom_components/`
directory and restart.

## Development

```bash
uv sync --group dev
uv run ruff check .
uv run pytest
```

The `orbitclient/` package under `custom_components/orbit_gdo/` has **no Home
Assistant dependency** and is unit‑tested standalone (REST via `aioresponses`,
MQTT via a fake transport, fixtures taken from real hub traffic).

## License

MIT — see [`LICENSE`](LICENSE).
