from __future__ import annotations

import logging

from historical_sensor import HistoricalState
from aiohttp.web import Request
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utc_from_timestamp

from .const import CONF_WEBHOOK_ID, DOMAIN, EVENT_DATA_RECEIVED

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Numeric fields dispatched as HistoricalState to registered sensors.
# Pressure arrives in Pa from firmware; sensors apply /100 transform.
_NUMERIC_FIELDS: tuple[str, ...] = (
    "aqi",
    "temperature",
    "humidity",
    "pressure",
    "voltage",
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_id = entry.entry_id
    hass.data.setdefault(DOMAIN, {})[entry_id] = {"sensors": []}

    async def _handle_webhook(
        hass: HomeAssistant, webhook_id: str, request: Request
    ) -> None:
        try:
            data = await request.json()
        except Exception:
            _LOGGER.debug("Received non-JSON or malformed payload on Airnote webhook")
            return

        body = data.get("body", {})
        if "aqi" not in body:
            return

        # Fire event so binary sensor and aqi_level text sensor can update.
        hass.bus.async_fire(
            EVENT_DATA_RECEIVED,
            {"entry_id": entry_id, "body": body},
        )

        # `when` is the on-device measurement timestamp (Unix seconds).
        when_ts = data.get("when")
        if not when_ts:
            return

        measurement_dt = utc_from_timestamp(float(when_ts))

        sensors = hass.data.get(DOMAIN, {}).get(entry_id, {}).get("sensors", [])
        for sensor in sensors:
            raw = body.get(sensor.entity_description.payload_key)
            if raw is None:
                continue
            value = (
                sensor.entity_description.transform(raw)
                if sensor.entity_description.transform
                else float(raw)
            )
            hist_state = HistoricalState(
                state=value,
                dt=measurement_dt,
                attributes={},
            )
            try:
                await sensor.async_push_historical_state(hist_state)
            except Exception:
                _LOGGER.exception(
                    "Failed to write historical state for %s", sensor.entity_id
                )

    webhook.async_register(
        hass,
        DOMAIN,
        "Blues Airnote",
        entry.data[CONF_WEBHOOK_ID],
        _handle_webhook,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded
