from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blues_airnote.const import CONF_WEBHOOK_ID, DOMAIN, EVENT_DATA_RECEIVED

ENTRY_ID = "test_entry_id"
WEBHOOK_ID = "blues_airnote_test123"
SAMPLE_WHEN = 1700000000

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

    captured = {}

    def _capture_register(hass, domain, name, webhook_id, handler):
        captured["handler"] = handler

    with patch(
        "homeassistant.components.webhook.async_register",
        side_effect=_capture_register,
    ), patch("homeassistant.components.webhook.async_unregister"):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entry._webhook_handler = captured.get("handler")
    yield entry


async def _fire_webhook(hass, handler, body, when=SAMPLE_WHEN):
    request = MagicMock()
    request.json = AsyncMock(return_value={"when": when, "body": body})
    # Prevent actual recorder writes during unit tests.
    sensors = hass.data.get(DOMAIN, {}).get(ENTRY_ID, {}).get("sensors", [])
    for sensor in sensors:
        sensor.async_write_ha_historical_states = AsyncMock()
    await handler(hass, WEBHOOK_ID, request)
    await hass.async_block_till_done()


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


async def test_aqi_level_updates_on_event(hass: HomeAssistant, setup_integration) -> None:
    """aqi_level text sensor still updates from the event bus."""
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": ENTRY_ID, "body": SAMPLE_BODY},
    )
    await hass.async_block_till_done()

    aqi_level_id = _entity_id(hass, "sensor", "aqi_level")
    assert hass.states.get(aqi_level_id).state == "Good"


async def test_webhook_dispatches_historical_states(
    hass: HomeAssistant, setup_integration
) -> None:
    """Webhook handler creates HistoricalState objects for each numeric sensor."""
    await _fire_webhook(hass, setup_integration._webhook_handler, SAMPLE_BODY)

    sensors = hass.data[DOMAIN][ENTRY_ID]["sensors"]
    assert len(sensors) == 5  # aqi, temperature, humidity, pressure, voltage

    by_key = {s.entity_description.payload_key: s for s in sensors}

    assert by_key["aqi"]._attr_historical_states[0].state == pytest.approx(42.0)
    assert by_key["temperature"]._attr_historical_states[0].state == pytest.approx(21.5)
    assert by_key["humidity"]._attr_historical_states[0].state == pytest.approx(45.2)
    assert by_key["voltage"]._attr_historical_states[0].state == pytest.approx(3.718)


async def test_numeric_sensors_show_latest_value(
    hass: HomeAssistant, setup_integration
) -> None:
    """After a webhook, numeric sensors expose the most recent measurement as their state."""
    await _fire_webhook(hass, setup_integration._webhook_handler, SAMPLE_BODY)

    aqi_id = _entity_id(hass, "sensor", "aqi")
    assert float(hass.states.get(aqi_id).state) == pytest.approx(42.0)

    temp_id = _entity_id(hass, "sensor", "temperature")
    assert float(hass.states.get(temp_id).state) == pytest.approx(21.5)


async def test_pressure_converted_from_pa(
    hass: HomeAssistant, setup_integration
) -> None:
    """Pressure raw Pa value is converted to hPa before writing as a historical state."""
    await _fire_webhook(hass, setup_integration._webhook_handler, SAMPLE_BODY)

    sensors = hass.data[DOMAIN][ENTRY_ID]["sensors"]
    pressure_sensor = next(
        s for s in sensors if s.entity_description.payload_key == "pressure"
    )
    # 101325 Pa → round(101325 / 100, 0) = 1013.0 hPa
    assert pressure_sensor._attr_historical_states[0].state == pytest.approx(1013.0)


async def test_sensors_ignore_wrong_entry_id(
    hass: HomeAssistant, setup_integration
) -> None:
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": "some_other_entry", "body": SAMPLE_BODY},
    )
    await hass.async_block_till_done()

    aqi_id = _entity_id(hass, "sensor", "aqi")
    assert hass.states.get(aqi_id).state == "unknown"


async def test_charging_binary_sensor_updates(
    hass: HomeAssistant, setup_integration
) -> None:
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": ENTRY_ID, "body": {**SAMPLE_BODY, "charging": True}},
    )
    await hass.async_block_till_done()

    charging_id = _entity_id(hass, "binary_sensor", "charging")
    assert hass.states.get(charging_id).state == "on"


async def test_charging_absent_defaults_false(
    hass: HomeAssistant, setup_integration
) -> None:
    body = {k: v for k, v in SAMPLE_BODY.items() if k != "charging"}
    hass.bus.async_fire(
        EVENT_DATA_RECEIVED,
        {"entry_id": ENTRY_ID, "body": body},
    )
    await hass.async_block_till_done()

    charging_id = _entity_id(hass, "binary_sensor", "charging")
    assert hass.states.get(charging_id).state == "off"
