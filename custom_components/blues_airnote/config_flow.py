from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import CONF_WEBHOOK_ID, DOMAIN


class BluesAirNoteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._webhook_id = f"blues_airnote_{secrets.token_hex(8)}"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(
                title="AirNote",
                data={CONF_WEBHOOK_ID: self._webhook_id},
            )

        try:
            ha_url = get_url(self.hass, prefer_external=True)
        except NoURLAvailableError:
            return self.async_abort(reason="no_url_available")

        webhook_url = f"{ha_url}/api/webhook/{self._webhook_id}"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={"webhook_url": webhook_url},
        )
