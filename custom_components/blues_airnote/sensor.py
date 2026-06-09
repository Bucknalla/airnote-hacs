from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from historical_sensor import HistoricalSensor, HistoricalState
from homeassistant.components.recorder.statistics import StatisticMetaData
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_DATA_RECEIVED

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.components.recorder.statistics import StatisticMeanType
except ImportError:
    StatisticMeanType = None  # type: ignore[assignment]


@dataclass(frozen=True, kw_only=True)
class AirNoteHistoricalSensorDescription(SensorEntityDescription):
    payload_key: str = ""
    transform: Callable[[Any], float] | None = None


@dataclass(frozen=True, kw_only=True)
class AirNoteTextSensorDescription(SensorEntityDescription):
    payload_key: str = ""


HISTORICAL_SENSOR_DESCRIPTIONS: tuple[AirNoteHistoricalSensorDescription, ...] = (
    AirNoteHistoricalSensorDescription(
        key="aqi",
        payload_key="aqi",
        name="AQI",
        device_class=SensorDeviceClass.AQI,
    ),
    AirNoteHistoricalSensorDescription(
        key="temperature",
        payload_key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        suggested_display_precision=1,
    ),
    AirNoteHistoricalSensorDescription(
        key="humidity",
        payload_key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
    ),
    AirNoteHistoricalSensorDescription(
        key="pressure",
        payload_key="pressure",
        name="Pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement="hPa",
        suggested_display_precision=0,
        transform=lambda v: round(v / 100, 0),
    ),
    AirNoteHistoricalSensorDescription(
        key="voltage",
        payload_key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
        suggested_display_precision=3,
    ),
)

TEXT_SENSOR_DESCRIPTIONS: tuple[AirNoteTextSensorDescription, ...] = (
    AirNoteTextSensorDescription(
        key="aqi_level",
        payload_key="aqi_level",
        name="AQI Level",
        icon="mdi:air-filter",
    ),
)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Airnote",
        manufacturer="Blues",
        model="Airnote",
        configuration_url="https://airnote.blues.io",
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    historical_sensors = [
        AirNoteHistoricalSensor(entry, desc)
        for desc in HISTORICAL_SENSOR_DESCRIPTIONS
    ]
    text_sensors = [AirNoteTextSensor(entry, desc) for desc in TEXT_SENSOR_DESCRIPTIONS]

    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})["sensors"] = (
        historical_sensors
    )

    async_add_entities(historical_sensors + text_sensors)


class AirNoteHistoricalSensor(HistoricalSensor, SensorEntity):
    """Numeric sensor that writes backdated readings to the HA states and statistics tables."""

    entity_description: AirNoteHistoricalSensorDescription
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state = None

    def __init__(
        self, entry: ConfigEntry, description: AirNoteHistoricalSensorDescription
    ) -> None:
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)
        self._entry_id = entry.entry_id

    @property
    def statistic_id(self) -> str:
        return f"{DOMAIN}:{self.entity_description.payload_key}"

    def get_statistic_metadata(self) -> StatisticMetaData:
        meta: dict[str, Any] = {
            "has_mean": True,
            "has_sum": False,
            "name": self.name,
            "source": DOMAIN,
            "statistic_id": self.statistic_id,
            "unit_of_measurement": self.entity_description.native_unit_of_measurement,
        }
        if StatisticMeanType is not None:
            meta["mean_type"] = StatisticMeanType.ARITHMETIC
        return StatisticMetaData(**meta)

    async def async_update_historical(self) -> None:
        # Push-based integration: no polling needed.
        pass

    async def async_calculate_statistic_data(
        self,
        hist_states: list[HistoricalState],
        *,
        last: dict | None,
    ):
        # The library calls this; return empty list since we rely on the states
        # written directly to the DB. Statistics aggregation is handled per-hour
        # by the library's _async_write_statistic_data.
        return []

    async def async_push_historical_state(self, hist_state: HistoricalState) -> None:
        """Receive one backdated reading from the webhook handler."""
        self._attr_historical_states = [hist_state]
        await self.async_write_ha_historical_states()


class AirNoteTextSensor(RestoreSensor, SensorEntity):
    """Text sensor (aqi_level) that updates in real-time via the event bus."""

    entity_description: AirNoteTextSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self, entry: ConfigEntry, description: AirNoteTextSensorDescription
    ) -> None:
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = _device_info(entry)
        self._entry_id = entry.entry_id

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value

        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_DATA_RECEIVED, self._handle_event)
        )

    async def _handle_event(self, event: Event) -> None:
        if event.data.get("entry_id") != self._entry_id:
            return
        body: dict[str, Any] = event.data["body"]
        raw = body.get(self.entity_description.payload_key)
        if raw is None:
            return
        self._attr_native_value = raw
        self.async_write_ha_state()
