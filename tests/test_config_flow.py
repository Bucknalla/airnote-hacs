from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.network import NoURLAvailableError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blues_airnote.const import CONF_WEBHOOK_ID, DOMAIN

HA_URL = "https://my-ha.example.com"


@pytest.fixture(autouse=True)
def mock_get_url():
    with patch(
        "custom_components.blues_airnote.config_flow.get_url",
        return_value=HA_URL,
    ):
        yield


async def test_step_user_shows_webhook_url(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    placeholders = result["description_placeholders"]
    assert "webhook_url" in placeholders
    assert placeholders["webhook_url"].startswith(HA_URL)
    assert "blues_airnote_" in placeholders["webhook_url"]


async def test_step_user_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Airnote"
    assert result2["data"][CONF_WEBHOOK_ID].startswith("blues_airnote_")


async def test_abort_when_already_configured(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_WEBHOOK_ID: "blues_airnote_existing"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_abort_when_no_external_url(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.blues_airnote.config_flow.get_url",
        side_effect=NoURLAvailableError,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_url_available"
