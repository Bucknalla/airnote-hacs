# Blues AirNote — Home Assistant Integration Design Document

| | |
|---|---|
| **Author** | Alex Bucknall |
| **Status** | Draft |
| **Version** | 0.3 |
| **Date** | June 2026 |
| **Target** | HACS (Home Assistant Community Store) |

---

## 1. Overview

This document describes the design and implementation plan for a Home Assistant custom integration for the Blues Wireless AirNote air quality monitor, distributed via HACS.

The integration registers a webhook endpoint inside Home Assistant and presents the generated URL to the user during setup. The user pastes this URL into the AirNote device configuration page. From that point, the AirNote pushes data directly to Home Assistant on every sync — no Notehub API credentials, no polling, no external dependencies.

> **Note:** This document supersedes the current manual approach (webhook automation + input_number helpers + template sensors) with a proper integration that provides device registry grouping, a config flow UI, and long-term statistics.

---

## 2. Goals & Non-Goals

### 2.1 Goals

- Zero YAML configuration for the end user
- Integration generates the webhook URL and displays it clearly during setup
- Sensor entities appear under a named device entry in the HA device registry
- Support for the AirNote payload (AQI, temperature, humidity, pressure, voltage, charging state)
- Graceful handling of absent or unexpected fields
- Publishable to HACS as a default repository

### 2.2 Non-Goals (v1)

- Support for arbitrary non-AirNote Notehub devices
- Any Notehub API integration or authentication
- Writing back to devices (sending Notes)
- Multiple simultaneous AirNote devices (can be added in v2)

---

## 3. Architecture

### 3.1 Data Flow

The integration uses a pure push architecture. The AirNote POSTs directly to the HA webhook URL on every Notecard sync. There is no polling and no outbound connection from HA to any external service.

```
AirNote Device
    |
    | (Notecard sync, ~every 60s)
    |
Notehub Cloud
    |
    | POST {ha_url}/api/webhook/blues_airnote_{entry_id}
    | (JSON payload with air.qo body)
    |
HA Webhook Handler  [blues_airnote integration]
    |
HA Sensor / Binary Sensor Entities
```

### 3.2 Repository Structure

```
custom_components/blues_airnote/
├── __init__.py           # Entry point, registers webhook
├── manifest.json         # Metadata, dependencies, version
├── config_flow.py        # UI setup — generates and displays webhook URL
├── sensor.py             # Sensor entity definitions
├── binary_sensor.py      # Binary sensor entity definitions
├── const.py              # Domain, entity definitions
└── strings.json          # UI strings / translations
hacs.json
README.md
tests/
```

---

## 4. Key Components

### 4.1 manifest.json

| Field | Value |
|---|---|
| `domain` | `blues_airnote` |
| `iot_class` | `cloud_push` |
| `config_flow` | `true` |
| `requirements` | none (uses built-in HA webhook infrastructure) |
| `version` | `1.0.0` |

### 4.2 Config Flow (`config_flow.py`)

The config flow has a single step. On submission, it:

1. Generates a unique webhook ID (e.g. `blues_airnote_{entry_id}`)
2. Constructs the full webhook URL from the HA external URL + webhook ID
3. Displays the URL to the user with a clear instruction to paste it into the AirNote device config page
4. Creates the config entry — no validation possible at this stage since the AirNote hasn't sent data yet

```
User adds integration
    |
Config flow generates webhook URL
    |
Displays: "Paste this URL into your AirNote config page:"
          https://your-ha/api/webhook/blues_airnote_abc123
    |
User confirms → config entry created → webhook registered
```

> **Prerequisite:** The user must have a publicly accessible HA instance with an external URL configured. This is a documented installation requirement and is not handled within the integration itself.

### 4.3 Webhook Handler (`__init__.py`)

On config entry setup, the integration registers a webhook handler with the HA webhook component:

```python
webhook_id = entry.data["webhook_id"]
webhook.async_register(hass, DOMAIN, "Blues AirNote", webhook_id, handle_webhook)
```

The handler receives the POST from Notehub, validates that the payload contains an `aqi` key (to filter out non-air.qo payloads), then fires an internal HA event that the sensor entities subscribe to.

Webhook handler behaviour:

- Accepts `POST` only
- Ignores payloads where `body.aqi` is absent (heartbeats, session notes, etc.)
- Fires `blues_airnote_data` event with the `body` dict as event data
- Returns HTTP 200 regardless (Notehub does not retry on failure)

### 4.4 Sensor Entities (`sensor.py`)

Each numeric field in the AirNote payload becomes a `SensorEntity`. Entities use `RestoreEntity` to recover their last known state across HA restarts.

| Entity | Device Class | Unit | Notes |
|---|---|---|---|
| `sensor.airnote_aqi` | `aqi` | — | Integer, 0–500 |
| `sensor.airnote_aqi_level` | — | — | Text: good / moderate / etc |
| `sensor.airnote_temperature` | `temperature` | °C | 1 d.p. |
| `sensor.airnote_humidity` | `humidity` | % | 1 d.p. |
| `sensor.airnote_pressure` | `atmospheric_pressure` | hPa | Converted from Pa (÷ 100), 0 d.p. |
| `sensor.airnote_voltage` | `voltage` | V | 3 d.p. |

### 4.5 Binary Sensor Entities (`binary_sensor.py`)

| Entity | Device Class | Notes |
|---|---|---|
| `binary_sensor.airnote_charging` | `battery_charging` | Optional — defaults to `False` if absent from payload |

---

## 5. Device Registry

All entities are grouped under a single device entry, giving users a clean view in Settings → Devices & Services.

| Field | Value |
|---|---|
| `identifiers` | `{(DOMAIN, entry_id)}` |
| `name` | `AirNote` |
| `manufacturer` | `Blues Wireless` |
| `model` | `AirNote` |
| `configuration_url` | `https://airnote.blues.io` |

---

## 6. Error Handling

| Scenario | Behaviour |
|---|---|
| Payload missing `aqi` key | Silently ignore — not an air.qo event |
| AirNote sends malformed JSON | HA webhook infrastructure returns 400; logged at debug level |
| Optional field absent (e.g. `charging`) | Default to `None` / `False` |
| HA restart | `RestoreEntity` recovers last known state; entities remain valid until next push |

---

## 7. Build Plan

| Phase | Effort | Deliverable |
|---|---|---|
| 1. Scaffold + manifest + const | 1 hr | Loadable integration, no entities |
| 2. Config flow (generate + display webhook URL) | 2 hrs | Full setup wizard |
| 3. Webhook handler + event firing | 2 hrs | Incoming payloads processed |
| 4. Sensor entities + RestoreEntity | 2 hrs | All AirNote sensors working |
| 5. Binary sensor + device registry | 1 hr | Charging entity, device grouping |
| 6. Error handling + edge cases | 1 hr | Robust failure modes |
| 7. Tests | 3 hrs | pytest-homeassistant-custom-component coverage |
| 8. HACS packaging + README | 2 hrs | hacs.json, badges, install guide |
| **Total** | **~14 hrs** | **HACS-publishable v1.0.0** |

The removal of the Notehub API client and coordinator reduces scope significantly compared to a polling approach.

---

## 8. Future Work (v2+)

### 8.1 Multiple AirNote Devices

Support multiple devices by scoping the webhook ID and device registry entry to a user-provided device name or serial number collected during config flow. Each device gets its own config entry and webhook URL.

### 8.2 Generic Notehub Webhook Support

A generic mode that introspects the incoming payload dynamically, creating entities for any numeric or boolean field. This would make the integration useful for arbitrary Notecard-based devices beyond the AirNote.

---

## 9. Open Questions

- Should the domain be `blues_airnote` (specific, simpler) or `blues_notehub` (broader, more future-proof)?
- Should the config flow collect a user-provided device name/label for the device registry entry, or default to "AirNote"?
- Should we submit to the official HA integrations repo (higher bar, longer review) or HACS custom repos first?