# ha-orbit — Skylink Orbit garage door openers for Home Assistant

A [HACS](https://hacs.xyz/) custom integration for **Skylink Orbit** Wi‑Fi garage
door openers — the **Atoms**, **Atoms Pro**, and **Nova** controllers driven by
the **Orbit Home** app (`com.mtqqdemo.skylink`).

> **Not** the same as `bhyve-home-assistant`, which is for *Orbit Irrigation's*
> B‑hyve sprinklers — a different company that happens to share the name "Orbit".

## Status

⚠️ **Protocol not yet confirmed against hardware.** Skylink publishes no API. The
cloud request/response shapes here are a structured best guess (see
[`SPEC.md`](SPEC.md)); the code is arranged so that wiring in a real, captured
protocol is a localized edit to `orbitclient/const.py` and two parse helpers in
`orbitclient/models.py`. Everything else — auth lifecycle, coordinator, entities,
config/reauth/options flows, and the test suite — is complete and green.

If you own one of these openers and can run a `mitmproxy` capture, see
[`SPEC.md` §2.1](SPEC.md#21-how-to-capture-the-protocol) — that's the one missing
piece.

## What you get

| Entity           | Description                                    |
| ---------------- | ---------------------------------------------- |
| Cover (`garage`) | Open / close / stop the door, live door state  |
| Light            | The opener's built‑in light (if present)       |
| Binary sensor    | Obstruction (`problem`), connectivity          |
| Sensor           | Wi‑Fi signal, battery (diagnostic)             |

State is polled every 30 s, with an optional MQTT push channel for near‑instant
updates that falls back to polling if the broker is unreachable.

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/xerhab/ha-orbit`,
   category **Integration**.
2. Install **Orbit Garage Door Opener (Skylink)**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Orbit** and sign in with
   your Orbit Home account.

Advanced fields let you override the API base URL and MQTT host — use these to
point at a captured host without editing source.

## Manual installation

Copy `custom_components/orbit_gdo` into your Home Assistant `config/custom_components/`
directory and restart.

## Development

```bash
uv sync --group dev        # or: pip install -e '.[dev]'
uv run ruff check .
uv run pytest
```

The `orbitclient/` package under `custom_components/orbit_gdo/` has **no Home
Assistant dependency** and is unit‑tested standalone with `aioresponses`.

## License

MIT — see [`LICENSE`](LICENSE).
