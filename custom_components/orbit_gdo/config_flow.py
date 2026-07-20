"""Config and options flow for the Orbit integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_BASE_URL,
    CONF_EMAIL,
    CONF_ENABLE_REALTIME,
    CONF_MQTT_HOST,
    DOMAIN,
)
from .orbitclient import OrbitAuthError, OrbitClient, OrbitError
from .orbitclient.const import DEFAULT_BASE_URL, DEFAULT_MQTT_HOST

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
        vol.Optional(CONF_MQTT_HOST, default=DEFAULT_MQTT_HOST): str,
    }
)


async def _validate(hass, data: dict[str, Any]) -> str:
    """Validate credentials; return the user id used as the unique id."""
    client = OrbitClient(
        data[CONF_EMAIL],
        data[CONF_PASSWORD],
        session=async_get_clientsession(hass),
        base_url=data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
        mqtt_host=data.get(CONF_MQTT_HOST, DEFAULT_MQTT_HOST),
    )
    token = await client.async_login()
    # Fall back to the email if the cloud does not return a stable user id.
    return token.user_id or data[CONF_EMAIL].lower()


class OrbitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI-driven setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                unique_id = await _validate(self.hass, user_input)
            except OrbitAuthError:
                errors["base"] = "invalid_auth"
            except OrbitError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Orbit credentials")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication after credentials stop working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            merged = {**reauth_entry.data, **user_input}
            try:
                await _validate(self.hass, merged)
            except OrbitAuthError:
                errors["base"] = "invalid_auth"
            except OrbitError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_EMAIL, default=reauth_entry.data[CONF_EMAIL]
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OrbitOptionsFlow:
        return OrbitOptionsFlow()


class OrbitOptionsFlow(OptionsFlow):
    """Toggle the optional realtime (MQTT) push channel."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ENABLE_REALTIME,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_REALTIME, True
                        ),
                    ): bool,
                }
            ),
        )
