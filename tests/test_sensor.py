from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blues_airnote.const import CONF_WEBHOOK_ID, DOMAIN, EVENT_DATA_RECEIVED

ENTRY_ID = "test_entry_id"
WEBHOOK_ID = "blues_airnote_test123"

SAMPLE_BODY = {
    "aqi": 42,
    "aqi_level": "Good",
    "temperature": 21.5,
    "humidity": 45.2,
    "pressure": 101325.0,
    "voltage": 3.718,
    "charging": False,
}


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_WEBHOOK_ID: WEBHOOK_ID},
        entry_id=ENTRY_ID,
    )
    entry.add_to_hass(hass)
    with patch("homeassistant.components.webhook.async_register"), patch(
        "homeassistant.components.webhook.async_unregister"
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    yield entry


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(platform, DOMAIN, f"{ENTRY_ID}_{key}")


async def test_sensors_created(hass: HomeAssistant, setup_integration) -> None:
    for key in ("aqi", "aqi_level", "temperature", "humidity", "pressure", "voltage"):
        assert _entity_id(hass, "sensor", key) is not None


async def test_binary_sensor_created(hass: HomeAssistant, setup_integration) -> None:
    assert _entity_id(hass, "binary_sensor", "charging") is not None


async def test_sensors_start_unavailable(hass: HomeAssistant, setup_integration) -> None:
    entity_id = _entity_id(hass, "sensor", "aqi")
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unknown"


async def test_sensors_update_on_event(hass: HomeAssistant, setup_integration) -> None:
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": ENTRY_ID, "body": SAMPLE_BODY},
    )
    await hass.async_block_till_done()

    aqi_id = _entity_id(hass, "sensor", "aqi")
    assert hass.states.get(aqi_id).state == "42"

    temp_id = _entity_id(hass, "sensor", "temperature")
    assert float(hass.states.get(temp_id).state) == pytest.approx(21.5)

    humidity_id = _entity_id(hass, "sensor", "humidity")
    assert float(hass.states.get(humidity_id).state) == pytest.approx(45.2)

    aqi_level_id = _entity_id(hass, "sensor", "aqi_level")
    assert hass.states.get(aqi_level_id).state == "Good"

    voltage_id = _entity_id(hass, "sensor", "voltage")
    assert float(hass.states.get(voltage_id).state) == pytest.approx(3.718)


async def test_pressure_converted_from_pa(hass: HomeAssistant, setup_integration) -> None:
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": ENTRY_ID, "body": SAMPLE_BODY},
    )
    await hass.async_block_till_done()

    pressure_id = _entity_id(hass, "sensor", "pressure")
    # 101325 Pa → 1013.0 hPa
    assert float(hass.states.get(pressure_id).state) == pytest.approx(1013.0)


async def test_sensors_ignore_wrong_entry_id(hass: HomeAssistant, setup_integration) -> None:
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": "some_other_entry", "body": SAMPLE_BODY},
    )
    await hass.async_block_till_done()

    aqi_id = _entity_id(hass, "sensor", "aqi")
    assert hass.states.get(aqi_id).state == "unknown"


async def test_charging_binary_sensor_updates(hass: HomeAssistant, setup_integration) -> None:
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": ENTRY_ID, "body": {**SAMPLE_BODY, "charging": True}},
    )
    await hass.async_block_till_done()

    charging_id = _entity_id(hass, "binary_sensor", "charging")
    assert hass.states.get(charging_id).state == "on"


async def test_charging_absent_defaults_false(hass: HomeAssistant, setup_integration) -> None:
    body = {k: v for k, v in SAMPLE_BODY.items() if k != "charging"}
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": ENTRY_ID, "body": body},
    )
    await hass.async_block_till_done()

    charging_id = _entity_id(hass, "binary_sensor", "charging")
    assert hass.states.get(charging_id).state == "off"
