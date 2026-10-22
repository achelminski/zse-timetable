"""Sensory: data wygenerowania planu, data obowiązywania, nadchodzące zastępstwa, plan (timetable), ostatnie sprawdzenie.

Nazwy encji z tłumaczeń (strings.json / translations), unique_id bez zmian.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util, slugify

from . import ZsePlanConfigEntry
from .entity import ZsePlanEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZsePlanConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            PlanDateSensor(coordinator, "wygenerowano", "generated", "generated", "mdi:file-clock"),
            PlanDateSensor(coordinator, "obowiazuje_od", "valid_from", "valid_from", "mdi:calendar-start"),
            SubstitutionsSensor(coordinator, "zastepstwa"),
            TimetableSensor(coordinator, "timetable"),
            LastCheckSensor(coordinator, "ostatnie_sprawdzenie"),
        ]
    )


class TimetableSensor(ZsePlanEntity, SensorEntity):
    """Plan na 2 tygodnie (od poniedziałku bieżącego) z zastępstwami — źródło dla zse-timetable-card.

    Stan = poniedziałek bieżącego tygodnia; struktura w atrybutach (bez historii w recorderze).
    """

    _attr_translation_key = "timetable"
    _attr_icon = "mdi:timetable"
    _attr_device_class = SensorDeviceClass.DATE
    _unrecorded_attributes = frozenset({"days", "lesson_hours"})

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        # sensor.timetable_<nauczyciel>, a nie domyślne sensor.plan_lekcji_<nauczyciel>_timetable
        self.entity_id = f"sensor.timetable_{slugify(coordinator.teacher_name)}"

    @property
    def native_value(self) -> date:
        today = dt_util.now().date()
        return today - timedelta(days=today.weekday())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        version = self.coordinator.latest_version or {}
        return {
            "teacher": self.coordinator.teacher_label,
            "generated": version.get("generated"),
            "valid_from": version.get("valid_from"),
            "valid_from_text": self.coordinator.valid_from_text,
            "lesson_hours": self.coordinator.current_lesson_hours(),
            "days": self.coordinator.timetable(),
        }


class PlanDateSensor(ZsePlanEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator, key: str, translation_key: str, field: str, icon: str) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._field = field

    @property
    def native_value(self) -> date | None:
        version = self.coordinator.latest_version
        value = version.get(self._field) if version else None
        return date.fromisoformat(value) if value else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        version = self.coordinator.latest_version or {}
        return {
            "nauczyciel": version.get("title"),
            "uwagi": version.get("note"),
            "pobrano": version.get("fetched"),
            "ostatnie_sprawdzenie": self.coordinator.state.get("last_check"),
            "blad": self.coordinator.last_error,
        }


class SubstitutionsSensor(ZsePlanEntity, SensorEntity):
    _attr_translation_key = "substitutions"
    _attr_icon = "mdi:account-switch"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.upcoming_substitutions())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "zastepstwa": self.coordinator.upcoming_substitutions(),
            "ostatnie_sprawdzenie": self.coordinator.state.get("last_check"),
            "blad": self.coordinator.last_error,
        }


class LastCheckSensor(ZsePlanEntity, SensorEntity):
    """Czas ostatniego cyklu sprawdzania — stan zmienia się co interwał, więc każdy cykl widać w historii aktywności.

    Pozostałe sensory zmieniają stan tylko przy nowym planie/zastępstwie, a sam atrybut logbook pomija.
    """

    _attr_translation_key = "last_check"
    _attr_icon = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> datetime | None:
        value = self.coordinator.state.get("last_check")
        return dt_util.parse_datetime(value) if value else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"blad": self.coordinator.last_error}
