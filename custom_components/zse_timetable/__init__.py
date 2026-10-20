"""ZSE Timetable: plan nauczyciela (VULCAN Optivum) + zastępstwa jako sensor timetable."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import ZsePlanCoordinator

PLATFORMS = [Platform.SENSOR]

type ZsePlanConfigEntry = ConfigEntry[ZsePlanCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ZsePlanConfigEntry) -> bool:
    coordinator = ZsePlanCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZsePlanConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ZsePlanConfigEntry) -> None:
    await ZsePlanCoordinator(hass, entry).async_remove_store()


async def _async_update_listener(hass: HomeAssistant, entry: ZsePlanConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
