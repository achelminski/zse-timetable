"""Koordynator: pobieranie planu i zastępstw, wersjonowanie, zdarzenia powiadomień."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from urllib.parse import urljoin

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import parser
from .const import (
    CONF_NOTIFY,
    CONF_NOTIFY_ERRORS,
    CONF_PLAN_URL,
    CONF_SCAN_INTERVAL,
    CONF_SUBSTITUTIONS_URL,
    CONF_TEACHER,
    CONF_TEACHER_CODE,
    CONF_TEACHER_HREF,
    CONF_TEACHER_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_FETCH_ERROR,
    EVENT_FETCH_RESTORED,
    EVENT_PLAN_UPDATED,
    EVENT_SUBSTITUTION,
    KEEP_SUBSTITUTIONS_DAYS,
    LIST_PAGE,
    MAX_PLAN_VERSIONS,
    STORAGE_VERSION,
)
from . import messages
from .schedule import (
    absent_teacher,
    build_timetable,
    lesson_hours,
    lesson_times,
    plan_content,
    valid_from_text as plan_valid_from_text,
    version_for_day,
)

_LOGGER = logging.getLogger(__name__)


class ZsePlanCoordinator(DataUpdateCoordinator[dict]):
    """Trzyma stan w .storage: wersje planu, zastępstwa, wysłane powiadomienia, ETagi."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_TEACHER_NAME]}",
            update_interval=timedelta(minutes=minutes),
        )
        self.teacher_label: str = entry.data[CONF_TEACHER]
        self.teacher_name: str = entry.data[CONF_TEACHER_NAME]
        self.notify_services: list[str] = list(entry.options.get(CONF_NOTIFY, []))
        self.error_notify_services: list[str] = list(entry.options.get(CONF_NOTIFY_ERRORS, []))
        self.last_error: str | None = None
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.state: dict = {
            "versions": [],
            "substitutions": {},
            "notified": [],
            "http": {},
            "teacher_href": entry.data[CONF_TEACHER_HREF],
            "last_check": None,
            "fetch_error_since": None,  # początek trwającej awarii pobierania (alert już wysłany)
        }

    async def async_load(self) -> None:
        if stored := await self._store.async_load():
            self.state.update(stored)

    async def async_remove_store(self) -> None:
        await self._store.async_remove()

    # --- pobieranie ---------------------------------------------------------

    async def _fetch(self, url: str, conditional: bool = True) -> tuple[str, dict] | None:
        """GET warunkowy; None = 304 (bez zmian). Cache nagłówków zatwierdza _commit()."""
        headers = {}
        cache = self.state["http"].get(url, {}) if conditional else {}
        if cache.get("etag"):
            headers["If-None-Match"] = cache["etag"]
        if cache.get("last_modified"):
            headers["If-Modified-Since"] = cache["last_modified"]
        session = async_get_clientsession(self.hass)
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status == 304:
                return None
            resp.raise_for_status()
            raw = await resp.read()
            new_cache = {
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
            }
            return parser.decode_html(raw, resp.headers.get("Content-Type")), new_cache

    def _commit(self, url: str, cache: dict) -> None:
        self.state["http"][url] = cache

    async def _async_update_data(self) -> dict:
        errors = []
        for label, step in (("plan", self._update_plan), ("zastępstwa", self._update_substitutions)):
            try:
                await step()
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                errors.append(f"{label}: {err}")
        self.state["last_check"] = dt_util.now().isoformat()
        if errors:
            self.last_error = "; ".join(errors)
            _LOGGER.warning("Plan lekcji %s: %s", self.teacher_label, self.last_error)
            if not self.state["versions"]:
                raise UpdateFailed(self.last_error)
        else:
            self.last_error = None
        await self._track_fetch_state()
        await self._store.async_save(self.state)
        return self.state

    async def _track_fetch_state(self) -> None:
        """Alert raz na awarię (pierwszy nieudany cykl) i komunikat o powrocie; stan w Store przetrwa restart."""
        since = self.state.get("fetch_error_since")
        if self.last_error and not since:
            self.state["fetch_error_since"] = self.state["last_check"]
            title, text = messages.fetch_error(
                self.lang,
                self.teacher_name,
                self.last_error,
                int(self.update_interval.total_seconds() // 60),
            )
            self.hass.bus.async_fire(
                EVENT_FETCH_ERROR,
                {
                    "entry_id": self.config_entry.entry_id,
                    "teacher": self.teacher_label,
                    "error": self.last_error,
                    "text": text,
                },
            )
            await self._notify(title, text, self.error_notify_services)
        elif not self.last_error and since:
            self.state["fetch_error_since"] = None
            title, text = messages.fetch_restored(
                self.lang, self.teacher_name, dt_util.as_local(datetime.fromisoformat(since))
            )
            self.hass.bus.async_fire(
                EVENT_FETCH_RESTORED,
                {
                    "entry_id": self.config_entry.entry_id,
                    "teacher": self.teacher_label,
                    "since": since,
                    "text": text,
                },
            )
            await self._notify(title, text, self.error_notify_services)

    async def _update_plan(self) -> None:
        base = self.config_entry.data[CONF_PLAN_URL]
        versions: list[dict] = self.state["versions"]

        # Numery plany/nN.html zmieniają się po przegenerowaniu — odświeżamy href z listy.
        list_url = urljoin(base, LIST_PAGE)
        if fetched := await self._fetch(list_url, conditional=bool(versions)):
            html, cache = fetched
            teacher = parser.find_teacher(
                parser.parse_teacher_list(html),
                self.teacher_name,
                self.config_entry.data.get(CONF_TEACHER_CODE),
            )
            if teacher:
                self.state["teacher_href"] = teacher["href"]
            else:
                _LOGGER.warning("Nauczyciela %s nie ma na liście planu", self.teacher_label)
            self._commit(list_url, cache)

        plan_url = urljoin(base, self.state["teacher_href"])
        fetched = await self._fetch(plan_url, conditional=bool(versions))
        if not fetched:
            return
        html, cache = fetched
        plan = parser.parse_teacher_plan(html)
        self._commit(plan_url, cache)
        if versions and plan_content(versions[-1]) == plan_content(plan):
            # Ten sam plan: odśwież tylko pola opisowe (np. nowe w kodzie), bez nowej wersji i powiadomienia.
            for key in ("valid_from_text", "note", "title"):
                versions[-1][key] = plan.get(key)
            return
        plan["fetched"] = dt_util.now().isoformat()
        first = not versions
        versions.append(plan)
        del versions[:-MAX_PLAN_VERSIONS]
        if first:
            return
        _LOGGER.info("Nowa wersja planu %s: %s", self.teacher_label, plan["generated"])
        title, text = messages.plan_updated(self.lang, self.teacher_name, plan)
        self.hass.bus.async_fire(
            EVENT_PLAN_UPDATED,
            {
                "entry_id": self.config_entry.entry_id,
                "teacher": self.teacher_label,
                "generated": plan["generated"],
                "valid_from": plan["valid_from"],
                "note": plan["note"],
                "text": text,
            },
        )
        await self._notify(title, text)

    @property
    def lang(self) -> str:
        """Język powiadomień i etykiet: język HA (pl), w pozostałych przypadkach angielski."""
        return messages.language(self.hass.config.language)

    async def _notify(self, title: str, message: str, services: list[str] | None = None) -> None:
        """Wysyła na usługi notify.* wybrane w konfiguracji integracji (domyślnie lista planu/zastępstw)."""
        for service in self.notify_services if services is None else services:
            try:
                await self.hass.services.async_call(
                    "notify", service, {"title": title, "message": message}, blocking=True
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Nie wysłano powiadomienia przez notify.%s: %s", service, err)

    async def _update_substitutions(self) -> None:
        url = self.config_entry.data[CONF_SUBSTITUTIONS_URL]
        fetched = await self._fetch(url, conditional=bool(self.state["versions"]))
        if not fetched:
            return
        html, cache = fetched
        days = parser.parse_substitutions(html)
        if not days:
            _LOGGER.debug("Strona zastępstw bez nagłówka 'Zastępstwa w dniu'")
        mine = parser.substitutions_for(days, self.teacher_label)
        subs: dict[str, list[dict]] = self.state["substitutions"]
        notified = set(self.state["notified"])
        for day_iso, rows in mine.items():
            if rows:
                subs[day_iso] = rows
            else:
                subs.pop(day_iso, None)
            new = [r for r in rows if self._key(day_iso, r) not in notified]
            if new:
                await self._fire_substitution(day_iso, new)
                notified.update(self._key(day_iso, r) for r in new)

        cutoff = (dt_util.now().date() - timedelta(days=KEEP_SUBSTITUTIONS_DAYS)).isoformat()
        self.state["substitutions"] = {d: r for d, r in subs.items() if d >= cutoff}
        self.state["notified"] = sorted(k for k in notified if k[:10] >= cutoff)
        self._commit(url, cache)

    @staticmethod
    def _key(day_iso: str, row: dict) -> str:
        return f"{day_iso}|{row['lesson']}|{row['opis']}"

    def _row_details(self, day_iso: str, row: dict) -> dict:
        version = version_for_day(self.state["versions"], date.fromisoformat(day_iso))
        times = lesson_times(version["hours"], row["lessons"]) if version else None
        return {
            "date": day_iso,
            "lesson": row["lesson"],
            "start": times[0].strftime("%H:%M") if times else None,
            "end": times[1].strftime("%H:%M") if times else None,
            "group": row["group"],
            "room": row["room"],
            "absent": row["absent"],
            "absent_teacher": absent_teacher(row["absent"]),
            "notes": row["notes"],
        }

    async def _fire_substitution(self, day_iso: str, rows: list[dict]) -> None:
        day = date.fromisoformat(day_iso)
        lessons = [self._row_details(day_iso, r) for r in rows]
        _LOGGER.info("Nowe zastępstwa %s na %s: %d", self.teacher_label, day_iso, len(rows))
        title, text = messages.substitutions(self.lang, self.teacher_name, day, lessons)
        self.hass.bus.async_fire(
            EVENT_SUBSTITUTION,
            {
                "entry_id": self.config_entry.entry_id,
                "teacher": self.teacher_label,
                "date": day_iso,
                "weekday": messages.weekday_name(self.lang, day),
                "lessons": lessons,
                "text": text,
            },
        )
        await self._notify(title, text)

    # --- odczyt dla encji ---------------------------------------------------------

    def timetable(self, weeks: int = 2) -> list[dict]:
        """Dni od poniedziałku bieżącego tygodnia przez `weeks` tygodni (z zastępstwami)."""
        texts = messages.TEXTS[self.lang]
        return build_timetable(
            self.state["versions"],
            self.state["substitutions"],
            dt_util.now().date(),
            weeks,
            substitution_label=texts["substitution"],
            weekday_names=texts["weekdays"],
        )

    def current_lesson_hours(self) -> list[dict]:
        """Siatka Nr/Godz planu obowiązującego dziś."""
        return lesson_hours(version_for_day(self.state["versions"], dt_util.now().date()))

    def upcoming_substitutions(self) -> list[dict]:
        today = dt_util.now().date().isoformat()
        return [
            self._row_details(day_iso, row)
            for day_iso, rows in sorted(self.state["substitutions"].items())
            if day_iso >= today
            for row in rows
        ]

    @property
    def valid_from_text(self) -> str | None:
        """Pełna linia „Obowiązuje od: …” najnowszego planu (jak na stronie)."""
        return plan_valid_from_text(self.latest_version)

    @property
    def latest_version(self) -> dict | None:
        return self.state["versions"][-1] if self.state["versions"] else None
