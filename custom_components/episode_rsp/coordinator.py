"""Data coordinator: pushed state from the amp, with a slow poll as backup."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EpisodeRspClient, RspAuthError, RspError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


class RspCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """data = {"device": {...}, "zones": {i: {...}}, "inputs": {i: name}, "presets": [...]}"""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: EpisodeRspClient
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.client = client
        self._unsub = client.add_listener(self._handle_push)

    async def async_shutdown(self) -> None:
        self._unsub()
        await super().async_shutdown()
        await self.client.async_close()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_state()
        except RspAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RspError as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def _handle_push(self, state: dict[str, Any]) -> None:
        self.async_set_updated_data(state)

    # Each command returns after the amp replies; the reply carries the new
    # state, which _handle_push applies.

    async def async_set_volume(self, zone: int, volume: int) -> None:
        limit = self.data["zones"][zone]["max_volume"]
        await self.client.async_put("output_volume", zone, max(0, min(volume, limit)))

    async def async_set_mute(self, zone: int, mute: bool) -> None:
        await self.client.async_put("output_mute", zone, "on" if mute else "off")

    async def async_set_source(self, zone: int, input_index: int) -> None:
        await self.client.async_put("output_source1", zone, input_index)

    async def async_set_dsp_preset(self, zone: int, preset: int) -> None:
        await self.client.async_put("dsp_preset", zone, preset)
