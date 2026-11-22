"""Shared base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RspCoordinator


class RspZoneEntity(CoordinatorEntity[RspCoordinator]):
    """Base for entities that belong to one stereo output zone."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RspCoordinator, entry_id: str, zone: int) -> None:
        super().__init__(coordinator)
        self._zone = zone
        dev = coordinator.data["device"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=dev.get("devicename") or "Episode Amplifier",
            manufacturer="Episode (Snap One)",
            model=dev.get("devicemodel") or "Response Series DSP Amplifier",
            sw_version=dev.get("firmwareversion"),
            serial_number=dev.get("serialnumber"),
            configuration_url=f"http://{coordinator.client.host}",
        )

    @property
    def available(self) -> bool:
        return super().available and self._zone in self.coordinator.data["zones"]

    @property
    def _zone_data(self) -> dict:
        return self.coordinator.data["zones"][self._zone]

    @property
    def zone_label(self) -> str:
        return self._zone_data.get("name") or f"Zone {self._zone + 1}"
