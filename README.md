# Blues Airnote — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue)](https://www.home-assistant.io)

A Home Assistant integration for the [Blues Airnote](https://airnote.blues.io) air quality monitor, distributed via HACS.

The integration registers a webhook endpoint inside Home Assistant. You paste the generated URL into the Airnote device configuration page — from that point, the Airnote pushes data directly to Home Assistant on every Notecard sync. No Notehub API credentials, no polling, no external dependencies.

## Prerequisites

- A publicly accessible Home Assistant instance with an **external URL** configured (Settings → System → Network → Home Assistant URL)
- A [Blues Airnote](https://airnote.blues.io) device

## Installation

### Via HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations** → ⋮ → **Custom repositories**.
3. Add `https://github.com/Bucknalla/airnote-hacs` with category **Integration**.
4. Find **Blues Airnote** in the HACS integration list and install it.
5. Restart Home Assistant.

### Manual

Copy the `custom_components/blues_airnote/` directory into your HA configuration directory under `custom_components/`, then restart Home Assistant.

## Setup

1. Go to **Settings → Devices & Services → Add Integration** and search for **Blues Airnote**.
2. The integration generates a unique webhook URL and displays it:

   ```
   https://your-ha/api/webhook/blues_airnote_<id>
   ```

3. Paste this URL into your [Airnote device configuration page](https://airnote.blues.io).
4. Click **Done** — the integration is now active.

The Airnote will start pushing data to Home Assistant on its next Notecard sync. The integration needs no further configuration.

## Entities

All entities are grouped under a single **Airnote** device in Settings → Devices & Services.

| Entity | Class | Unit | Notes |
|---|---|---|---|
| `sensor.airnote_aqi` | AQI | — | 0–500 |
| `sensor.airnote_aqi_level` | — | — | good / moderate / unhealthy … |
| `sensor.airnote_temperature` | Temperature | °C | |
| `sensor.airnote_humidity` | Humidity | % | |
| `sensor.airnote_pressure` | Atmospheric pressure | hPa | Converted from Pa |
| `sensor.airnote_voltage` | Voltage | V | |
| `binary_sensor.airnote_charging` | Battery charging | on/off | Defaults to off if absent |

## Historical data

The Airnote samples every 15 minutes but uploads to Notehub in batches (typically every 6 hours). Each uploaded reading includes a `when` timestamp — the time it was actually measured on the device.

This integration uses that timestamp to backfill long-term statistics in Home Assistant's recorder at the correct measurement time, rather than the time HA received it. A 6-hour batch upload fills in 24 distinct 15-minute slots in the Statistics card — no data is lost.

To view historical data: **Developer Tools → Statistics** and search for `blues_airnote`, or add a **Statistics** card to any dashboard.

## Troubleshooting

**No entities appear after setup**
The Airnote hasn't pushed data yet. Sensors become available after the first successful sync. You can confirm the webhook is reachable by sending a test payload:

```bash
curl -X POST "https://your-ha/api/webhook/blues_airnote_<id>" \
  -H "Content-Type: application/json" \
  -d '{"when":1700000000,"body":{"aqi":42,"aqi_level":"good","temperature":21.5,"humidity":45.0,"pressure":101325,"voltage":3.718,"charging":false}}'
```

**"Integration not found" or setup fails**
Ensure your HA instance has an external URL set in Settings → System → Network. The integration requires a publicly accessible URL so the Airnote can reach it.

**Sensors show stale data**
Check that the webhook URL in your [Airnote device configuration](https://airnote.blues.io) matches the URL shown during setup. Re-adding the integration generates a new webhook ID.

## Development

```bash
git clone https://github.com/Bucknalla/airnote-hacs
cd airnote-hacs
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

## Licence

MIT
