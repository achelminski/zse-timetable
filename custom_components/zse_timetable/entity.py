"""Wspólna baza encji (jedno urządzenie-usługa na nauczyciela)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PLAN_URL, DOMAIN
from .coordinator import ZsePlanCoordinator


class ZsePlanEntity(CoordinatorEntity[ZsePlanCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ZsePlanCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            translation_key="teacher",
            translation_placeholders={"teacher": coordinator.teacher_name},
            manufacturer="ZSE Bydgoszcz",
            model="VULCAN Optivum",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=entry.data[CONF_PLAN_URL],
        )
