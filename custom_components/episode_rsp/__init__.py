"""Episode Response (EA-RSP) multi-zone amplifier integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EpisodeRspClient
from .const import DEFAULT_PORT
from .coordinator import RspCoordinator

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SELECT]

type RspConfigEntry = ConfigEntry[RspCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RspConfigEntry) -> bool:
    data = entry.data
    client = EpisodeRspClient(
        async_get_clientsession(hass),
        data[CONF_HOST],
        data.get(CONF_PORT, DEFAULT_PORT),
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )
    coordinator = RspCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RspConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unloaded
