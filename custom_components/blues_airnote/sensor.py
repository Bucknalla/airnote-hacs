from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

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


@dataclass(frozen=True, kw_only=True)
class AirNoteSensorEntityDescription(SensorEntityDescription):
    payload_key: str = ""
    transform: Callable[[Any], float] | None = None


SENSOR_DESCRIPTIONS: tuple[AirNoteSensorEntityDescription, ...] = (
    AirNoteSensorEntityDescription(
        key="aqi",
        payload_key="aqi",
        name="AQI",
        device_class=SensorDeviceClass.AQI,
    ),
    AirNoteSensorEntityDescription(
        key="aqi_level",
        payload_key="aqi_level",
        name="AQI Level",
        icon="mdi:air-filter",
    ),
    AirNoteSensorEntityDescription(
        key="temperature",
        payload_key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement="°C",
        suggested_display_precision=1,
    ),
    AirNoteSensorEntityDescription(
        key="humidity",
        payload_key="humidity",
        name="Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
    ),
    AirNoteSensorEntityDescription(
        key="pressure",
        payload_key="pressure",
        name="Pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement="hPa",
        suggested_display_precision=0,
        transform=lambda v: round(v / 100, 0),
    ),
    AirNoteSensorEntityDescription(
        key="voltage",
        payload_key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
        suggested_display_precision=3,
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
    async_add_entities(
        [AirNoteSensor(entry, desc) for desc in SENSOR_DESCRIPTIONS]
    )


class AirNoteSensor(RestoreSensor, SensorEntity):
    entity_description: AirNoteSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self, entry: ConfigEntry, description: AirNoteSensorEntityDescription
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
        self._attr_native_value = (
            self.entity_description.transform(raw)
            if self.entity_description.transform
            else raw
        )
        self.async_write_ha_state()
