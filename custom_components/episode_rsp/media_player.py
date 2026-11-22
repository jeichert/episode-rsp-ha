"""One media_player per stereo output zone."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import RspConfigEntry
from .coordinator import RspCoordinator
from .entity import RspZoneEntity

FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RspConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        RspZonePlayer(coordinator, entry.entry_id, zone)
        for zone in coordinator.data["zones"]
    )


class RspZonePlayer(RspZoneEntity, MediaPlayerEntity):
    """A zone. The amp has no per-zone power, so the state is always ON."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = FEATURES
    _attr_state = MediaPlayerState.ON

    def __init__(self, coordinator: RspCoordinator, entry_id: str, zone: int) -> None:
        super().__init__(coordinator, entry_id, zone)
        self._attr_unique_id = f"{entry_id}_zone_{zone}"

    @property
    def name(self) -> str:
        return self.zone_label

    # ---- sources: the amp stores a 0-based input index

    @property
    def _source_map(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for idx, raw in self.coordinator.data["inputs"].items():
            label = raw or f"Input {idx + 1}"
            if label in out:
                label = f"{label} ({idx + 1})"
            out[label] = idx
        return out

    @property
    def source_list(self) -> list[str]:
        return list(self._source_map)

    @property
    def source(self) -> str | None:
        current = self._zone_data.get("source")
        for label, idx in self._source_map.items():
            if idx == current:
                return label
        return None  # e.g. "No Input"

    async def async_select_source(self, source: str) -> None:
        await self.coordinator.async_set_source(self._zone, self._source_map[source])

    # ---- volume: the amp uses 0 to 100 directly

    @property
    def volume_level(self) -> float | None:
        vol = self._zone_data.get("volume")
        return None if vol is None else vol / 100

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.async_set_volume(self._zone, round(volume * 100))

    @property
    def is_volume_muted(self) -> bool:
        return bool(self._zone_data.get("mute"))

    async def async_mute_volume(self, mute: bool) -> None:
        await self.coordinator.async_set_mute(self._zone, mute)
