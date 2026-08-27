"""Config flow for CarLinko."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_EMAIL, CONF_REGION, DOMAIN
from .protocol.api_client import ApiClient
from .protocol.consts import DEFAULT_REGION
from .protocol.exceptions import AuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_REGION, default=DEFAULT_REGION): str,
    }
)


class CarlinkoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a CarLinko config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            region = (user_input.get(CONF_REGION) or DEFAULT_REGION).strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()
            try:
                await self._test_login(email, password, region)
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except AuthError as err:
                _LOGGER.debug("login failed: %s", err)
                errors["base"] = "invalid_auth"
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("login failed: %s", err)
                errors["base"] = "invalid_auth"
            else:
                return self.async_create_entry(
                    title=f"CarLinko ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_REGION: region,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            email = entry.data[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            region = entry.data.get(CONF_REGION) or DEFAULT_REGION
            try:
                await self._test_login(email, password, region)
            except AuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_auth"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: password},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    async def _test_login(self, email: str, password: str, region: str) -> None:
        session = async_get_clientsession(self.hass)

        class _TempStore:
            data: dict[str, Any] = {}

            def load(self) -> dict[str, Any]:
                return self.data

            def set_token(self, token: str | None) -> dict[str, Any]:
                self.data["token"] = token or ""
                return self.data

        api = ApiClient(email, password, region, _TempStore(), session)
        await api.login()
