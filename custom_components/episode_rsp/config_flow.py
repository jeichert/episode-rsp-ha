"""Config and reauth flows."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EpisodeRspClient, RspAuthError, RspError
from .const import DEFAULT_PORT, DEFAULT_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _validate(hass, host: str, port: int, user: str, password: str) -> dict:
    """Connect and return the amp's deviceinfo."""
    client = EpisodeRspClient(async_get_clientsession(hass), host, port, user, password)
    try:
        state = await client.async_get_state()
        return state["device"]
    finally:
        await client.async_close()


class EpisodeRspConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input:
            try:
                device = await _validate(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except RspAuthError as err:
                _LOGGER.error("Episode amp login refused: %s", err)
                errors["base"] = "invalid_auth"
            except RspError as err:
                _LOGGER.error("Episode amp connection failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error talking to the Episode amp")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    device.get("serialnumber") or user_input[CONF_HOST]
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=device.get("devicename") or "Episode Amplifier",
                    data=user_input,
                )

        d = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Required(
                    CONF_USERNAME, default=d.get(CONF_USERNAME, DEFAULT_USERNAME)
                ): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input:
            try:
                await _validate(
                    self.hass,
                    entry.data[CONF_HOST],
                    entry.data[CONF_PORT],
                    entry.data[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except RspAuthError as err:
                _LOGGER.error("Episode amp login refused: %s", err)
                errors["base"] = "invalid_auth"
            except RspError as err:
                _LOGGER.error("Episode amp connection failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error talking to the Episode amp")
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
