"""DSP preset select, one per zone."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RspConfigEntry
from .coordinator import RspCoordinator
from .entity import RspZoneEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: RspConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        RspDspPreset(coordinator, entry.entry_id, zone)
        for zone in coordinator.data["zones"]
    )


class RspDspPreset(RspZoneEntity, SelectEntity):
    """The preset is stored as an index into the amp's preset list."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: RspCoordinator, entry_id: str, zone: int) -> None:
        super().__init__(coordinator, entry_id, zone)
        self._attr_unique_id = f"{entry_id}_zone_{zone}_dsp_preset"

    @property
    def name(self) -> str:
        return f"{self.zone_label} DSP preset"

    @property
    def options(self) -> list[str]:
        return self.coordinator.data["presets"]

    @property
    def current_option(self) -> str | None:
        presets = self.coordinator.data["presets"]
        idx = self._zone_data.get("dsp_preset")
        return presets[idx] if idx is not None and 0 <= idx < len(presets) else None

    async def async_select_option(self, option: str) -> None:
        index = self.coordinator.data["presets"].index(option)
        await self.coordinator.async_set_dsp_preset(self._zone, index)
