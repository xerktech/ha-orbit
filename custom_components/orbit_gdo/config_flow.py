"""Config flow for the Orbit integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_EMAIL, DOMAIN
from .orbitclient import OrbitAuthError, OrbitClient, OrbitError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate(hass, data: Mapping[str, Any]) -> str:
    """Validate credentials; return the account number used as unique id."""
    client = OrbitClient(
        data[CONF_EMAIL], data[CONF_PASSWORD], session=async_get_clientsession(hass)
    )
    account = await client.async_login()
    return account.acc_no


class OrbitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI-driven setup."""

    VERSION = 1

    async def _try(self, data: Mapping[str, Any], errors: dict[str, str]) -> str | None:
        try:
            return await _validate(self.hass, data)
        except OrbitAuthError:
            errors["base"] = "invalid_auth"
        except OrbitError:
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating Orbit credentials")
            errors["base"] = "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = {**user_input, CONF_EMAIL: user_input[CONF_EMAIL].strip()}
            acc_no = await self._try(user_input, errors)
            if acc_no:
                await self.async_set_unique_id(acc_no)
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
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            merged = {**reauth_entry.data, **user_input}
            acc_no = await self._try(merged, errors)
            if acc_no:
                await self.async_set_unique_id(acc_no)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
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
