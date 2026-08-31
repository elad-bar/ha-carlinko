"""Config flow for CarLinko (one hub entry per account; all vehicles auto-added)."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .common.consts import (
    AVAILABILITY_SECONDS,
    CONF_AVAILABILITY_SECONDS,
    CONF_EMAIL,
    CONF_REGION,
    CONF_STREAM_BACKSTOP,
    DEFAULT_REGION,
    DOMAIN,
    KNOWN_REGIONS,
    STREAM_BACKSTOP,
)
from .common.helpers import mask_email, partial_id
from .managers.api_client import ApiClient
from .models.exceptions import AuthError

_LOGGER = logging.getLogger(__name__)


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    region = defaults.get(CONF_REGION) or DEFAULT_REGION
    return vol.Schema(
        {
            vol.Required(
                CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_REGION, default=region): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(KNOWN_REGIONS),
                    translation_key="region",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _reauth_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


def _options_schema(entry: config_entries.ConfigEntry) -> vol.Schema:
    region = (
        entry.options.get(CONF_REGION) or entry.data.get(CONF_REGION) or DEFAULT_REGION
    )
    backstop = entry.options.get(CONF_STREAM_BACKSTOP, STREAM_BACKSTOP)
    availability = entry.options.get(CONF_AVAILABILITY_SECONDS, AVAILABILITY_SECONDS)
    return vol.Schema(
        {
            vol.Required(CONF_REGION, default=region): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=list(KNOWN_REGIONS),
                    translation_key="region",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_STREAM_BACKSTOP, default=int(backstop)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5, max=300, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_AVAILABILITY_SECONDS, default=int(availability)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=60, max=86400, step=60, mode=selector.NumberSelectorMode.BOX
                )
            ),
        }
    )


class CarlinkoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a CarLinko config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is None:
            _LOGGER.info("config flow started step=user")
        if user_input is not None:
            email = str(user_input[CONF_EMAIL]).strip()
            password = user_input[CONF_PASSWORD]
            region = (user_input.get(CONF_REGION) or DEFAULT_REGION).strip()
            _LOGGER.info(
                f"config flow submit step=user region={region} "
                f"email={mask_email(email)}"
            )
            await self.async_set_unique_id(email.lower())
            _LOGGER.debug(f"config flow unique_id set email={email.lower()}")
            try:
                self._abort_if_unique_id_configured()
            except AbortFlow:
                _LOGGER.warning(
                    f"config flow abort step=user reason=already_configured "
                    f"unique_id={email.lower()}"
                )
                raise
            try:
                await self._validate_login(email, password, region)
            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    f"config flow failed step=user error=cannot_connect: {err}"
                )
                errors["base"] = "cannot_connect"
            except AuthError as err:
                _LOGGER.warning(
                    f"config flow failed step=user error=invalid_auth: {err}"
                )
                errors["base"] = "invalid_auth"
            except ValueError:
                _LOGGER.warning("config flow abort step=user reason=no_vehicles")
                return self.async_abort(reason="no_vehicles")
            except Exception as err:
                _LOGGER.exception(f"config flow failed step=user error={err}")
                errors["base"] = "invalid_auth"
            else:
                title = f"CarLinko ({email})"
                result = self.async_create_entry(
                    title=title,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                        CONF_REGION: region,
                    },
                )
                entry_id = (result.get("result") or {}).get("entry_id", "")
                _LOGGER.info(
                    f"config flow created entry title={title} "
                    f"entry_id={partial_id(entry_id)}"
                )
                return result
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is None:
            _LOGGER.info(
                f"config flow started step=reauth_confirm "
                f"entry_id={partial_id(entry.entry_id)}"
            )
        if user_input is not None:
            email = entry.data[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            region = entry.data.get(CONF_REGION) or DEFAULT_REGION
            try:
                await self._validate_login(
                    email, password, region, require_vehicles=False
                )
            except AuthError as err:
                _LOGGER.warning(
                    f"config flow failed step=reauth_confirm error=invalid_auth: {err}"
                )
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception(
                    f"config flow failed step=reauth_confirm error={err}"
                )
                errors["base"] = "invalid_auth"
            else:
                _LOGGER.info(
                    f"config flow success step=reauth_confirm reloading "
                    f"entry_id={partial_id(entry.entry_id)}"
                )
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_PASSWORD: password},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_reauth_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is None:
            _LOGGER.info(
                f"config flow started step=reconfigure "
                f"entry_id={partial_id(entry.entry_id)}"
            )
        if user_input is not None:
            email = entry.data[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            region = (user_input.get(CONF_REGION) or DEFAULT_REGION).strip()
            try:
                await self._validate_login(
                    email, password, region, require_vehicles=False
                )
            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    f"config flow failed step=reconfigure error=cannot_connect: {err}"
                )
                errors["base"] = "cannot_connect"
            except AuthError as err:
                _LOGGER.warning(
                    f"config flow failed step=reconfigure error=invalid_auth: {err}"
                )
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception(
                    f"config flow failed step=reconfigure error={err}"
                )
                errors["base"] = "invalid_auth"
            else:
                _LOGGER.info(
                    f"config flow success step=reconfigure reloading "
                    f"entry_id={partial_id(entry.entry_id)}"
                )
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_PASSWORD: password,
                        CONF_REGION: region,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        CONF_REGION,
                        default=entry.data.get(CONF_REGION) or DEFAULT_REGION,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(KNOWN_REGIONS),
                            translation_key="region",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def _validate_login(
        self,
        email: str,
        password: str,
        region: str,
        *,
        require_vehicles: bool = True,
    ) -> None:
        _LOGGER.debug(
            f"config flow validating login require_vehicles={str(require_vehicles).lower()}"
        )
        _LOGGER.debug("config flow _validate_login → ApiClient.login POST /user/login")
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
        if require_vehicles:
            _LOGGER.debug(
                "config flow _validate_login → ApiClient.async_list_vehicles force=true"
            )
            vehicles = await api.async_list_vehicles(force=True)
            if not vehicles:
                raise ValueError("no_vehicles")
        else:
            _LOGGER.debug(
                "config flow _validate_login skip async_list_vehicles (reauth/reconfigure)"
            )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return CarlinkoOptionsFlow()


class CarlinkoOptionsFlow(config_entries.OptionsFlow):
    """Options: region, stream backstop, availability window."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is None:
            _LOGGER.info(
                f"options flow started entry_id="
                f"{partial_id(self.config_entry.entry_id)}"
            )
        if user_input is not None:
            region = str(user_input[CONF_REGION]).strip() or DEFAULT_REGION
            backstop = int(user_input[CONF_STREAM_BACKSTOP])
            availability = int(user_input[CONF_AVAILABILITY_SECONDS])
            _LOGGER.info(
                f"options saved region={region} stream_backstop={backstop} "
                f"availability_seconds={availability}"
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_REGION: region,
                    CONF_STREAM_BACKSTOP: backstop,
                    CONF_AVAILABILITY_SECONDS: availability,
                },
            )
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.config_entry),
        )
