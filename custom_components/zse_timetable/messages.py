"""Localized notification texts (Polish / English, chosen by the Home Assistant language).

No Home Assistant imports — testable locally.
"""

from __future__ import annotations

from datetime import date, datetime

TEXTS = {
    "pl": {
        "weekdays": ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"],
        "substitution": "Zastępstwo",
        "plan_title": "Plan lekcji zaktualizowany",
        "plan_text": "Plan lekcji {teacher} zaktualizowany (wygenerowano {generated}), obowiązuje od {valid_from}.",
        "sub_title": "Zastępstwo {weekday} {day_short}",
        "sub_header": "Zastępstwa {teacher} — {weekday} {day}:",
        "lesson": "lekcja",
        "room": "sala",
        "absent": "za",
        "fetch_error_title": "Plan lekcji — błąd pobierania",
        "fetch_error_text": "Nie udało się pobrać planu lub zastępstw {teacher}: {error}. "
        "Kolejne próby co {interval} min, powiadomię po naprawie.",
        "fetch_ok_title": "Plan lekcji — pobieranie działa",
        "fetch_ok_text": "Pobieranie planu i zastępstw {teacher} znów działa (awaria od {since}).",
    },
    "en": {
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "substitution": "Substitution",
        "plan_title": "Timetable updated",
        "plan_text": "Timetable of {teacher} updated (generated {generated}), valid from {valid_from}.",
        "sub_title": "Substitution {weekday} {day_short}",
        "sub_header": "Substitutions for {teacher} — {weekday} {day}:",
        "lesson": "lesson",
        "room": "room",
        "absent": "covering for",
        "fetch_error_title": "Timetable — download failed",
        "fetch_error_text": "Could not download the timetable or substitutions of {teacher}: {error}. "
        "Retrying every {interval} min, you will be notified when it works again.",
        "fetch_ok_title": "Timetable — download restored",
        "fetch_ok_text": "Downloading the timetable and substitutions of {teacher} works again (failing since {since}).",
    },
}


def language(code: str | None) -> str:
    """'pl', 'pl-PL' -> 'pl'; everything else -> 'en'."""
    return "pl" if (code or "").lower().startswith("pl") else "en"


def _dmy(iso: str | None) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y") if iso else "?"


def weekday_name(lang: str, day: date) -> str:
    return TEXTS[lang]["weekdays"][day.weekday()]


def plan_updated(lang: str, teacher: str, plan: dict) -> tuple[str, str]:
    """(title, message) for a new timetable version."""
    t = TEXTS[lang]
    text = t["plan_text"].format(
        teacher=teacher,
        generated=_dmy(plan.get("generated")),
        valid_from=_dmy(plan.get("valid_from") or plan.get("generated")),
    )
    if plan.get("note"):
        text += f" {plan['note']}"
    return t["plan_title"], text


def fetch_error(lang: str, teacher: str, error: str, interval: int) -> tuple[str, str]:
    """(title, message) for the first failed check of an outage."""
    t = TEXTS[lang]
    return t["fetch_error_title"], t["fetch_error_text"].format(
        teacher=teacher, error=error, interval=interval
    )


def fetch_restored(lang: str, teacher: str, since: datetime) -> tuple[str, str]:
    """(title, message) for the first successful check after an outage; since = local time it started."""
    t = TEXTS[lang]
    return t["fetch_ok_title"], t["fetch_ok_text"].format(
        teacher=teacher, since=since.strftime("%d.%m.%Y %H:%M")
    )


def substitutions(lang: str, teacher: str, day: date, lessons: list[dict]) -> tuple[str, str]:
    """(title, message) for new substitutions on one day.

    lessons: [{lesson, start, end, group, room, absent, notes}]
    """
    t = TEXTS[lang]
    weekday = weekday_name(lang, day)
    lines = []
    for les in lessons:
        when = f" ({les['start']}–{les['end']})" if les.get("start") else ""
        line = f"• {t['lesson']} {les['lesson']}{when}: {les['group']}"
        if les.get("room"):
            line += f", {t['room']} {les['room']}"
        if les.get("absent"):
            line += f" — {t['absent']}: {les['absent']}"
        if les.get("notes"):
            line += f" ({les['notes']})"
        lines.append(line)
    title = t["sub_title"].format(weekday=weekday, day_short=day.strftime("%d.%m"))
    header = t["sub_header"].format(teacher=teacher, weekday=weekday, day=day.strftime("%d.%m.%Y"))
    return title, header + "\n" + "\n".join(lines)
