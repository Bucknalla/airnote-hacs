from __future__ import annotations

import logging
from datetime import datetime

from aiohttp.web import Request
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import utc_from_timestamp

from .const import CONF_WEBHOOK_ID, DOMAIN, EVENT_DATA_RECEIVED

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Numeric fields to backfill as external statistics.
# Pressure arrives in Pa from firmware; converted to hPa on write.
_STAT_FIELDS: tuple[tuple[str, str | None, str], ...] = (
    ("aqi", None, "Airnote AQI"),
    ("temperature", "°C", "Airnote Temperature"),
    ("humidity", "%", "Airnote Humidity"),
    ("pressure", "hPa", "Airnote Pressure"),
    ("voltage", "V", "Airnote Voltage"),
)

# Maps unit_of_measurement → HA unit_class for StatisticMetaData.
_UNIT_CLASS: dict[str | None, str] = {
    "°C": "temperature",
    "%": "unitless",
    "hPa": "pressure",
    "V": "voltage",
    None: "unitless",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry_id = entry.entry_id

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

        hass.bus.async_fire(
            EVENT_DATA_RECEIVED,
            {"entry_id": entry_id, "body": body},
        )

        # `when` is the on-device measurement timestamp (Unix seconds).
        # Data can arrive hours late when the Notecard uploads in batches, so
        # we backfill statistics at the actual measurement time rather than now.
        if when_ts := data.get("when"):
            _write_statistics(hass, body, utc_from_timestamp(float(when_ts)))

    webhook.async_register(
        hass,
        DOMAIN,
        "Blues Airnote",
        entry.data[CONF_WEBHOOK_ID],
        _handle_webhook,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _write_statistics(
    hass: HomeAssistant,
    body: dict,
    measurement_time: datetime,
) -> None:
    """Backfill external statistics at the on-device measurement timestamp."""
    try:
        from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
            StatisticData,
            StatisticMetaData,
            async_add_external_statistics,
        )
        try:
            from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                StatisticMeanType,
            )
        except ImportError:
            StatisticMeanType = None
    except ImportError:
        _LOGGER.debug("Recorder not available; skipping historical statistics")
        return

    # HA external statistics require hourly resolution (minute=0, second=0).
    period_start = measurement_time.replace(minute=0, second=0, microsecond=0)

    for field_key, unit, display_name in _STAT_FIELDS:
        raw = body.get(field_key)
        if raw is None:
            continue
        value = float(round(raw / 100, 1) if field_key == "pressure" else raw)

        statistic_id = f"{DOMAIN}:{field_key}"
        meta: dict = {
            "has_mean": True,
            "has_sum": False,
            "name": display_name,
            "source": DOMAIN,
            "statistic_id": statistic_id,
            "unit_of_measurement": unit,
            "unit_class": _UNIT_CLASS.get(unit),
        }
        if StatisticMeanType is not None:
            meta["mean_type"] = StatisticMeanType.ARITHMETIC

        _LOGGER.debug("Writing statistic %s = %s at %s", statistic_id, value, period_start)
        async_add_external_statistics(
            hass,
            StatisticMetaData(**meta),
            [StatisticData(start=period_start, mean=value, state=value)],
        )

    _LOGGER.debug("Backfilled statistics at %s", period_start)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return unloaded
