from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, EVENT_DATA_RECEIVED


@dataclass(frozen=True, kw_only=True)
class AirNoteBinarySensorEntityDescription(BinarySensorEntityDescription):
    payload_key: str = ""


BINARY_SENSOR_DESCRIPTIONS: tuple[AirNoteBinarySensorEntityDescription, ...] = (
    AirNoteBinarySensorEntityDescription(
        key="charging",
        payload_key="charging",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [AirNoteBinarySensor(entry, desc) for desc in BINARY_SENSOR_DESCRIPTIONS]
    )


class AirNoteBinarySensor(RestoreEntity, BinarySensorEntity):
    entity_description: AirNoteBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self, entry: ConfigEntry, description: AirNoteBinarySensorEntityDescription
    ) -> None:
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="AirNote",
            manufacturer="Blues Wireless",
            model="AirNote",
            configuration_url="https://airnote.blues.io",
        )
        self._entry_id = entry.entry_id
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._attr_is_on = last.state == "on"

        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_DATA_RECEIVED, self._handle_event)
        )

    async def _handle_event(self, event: Event) -> None:
        if event.data.get("entry_id") != self._entry_id:
            return
        body: dict = event.data["body"]
        charging = body.get(self.entity_description.payload_key)
        self._attr_is_on = bool(charging) if charging is not None else False
        self.async_write_ha_state()
