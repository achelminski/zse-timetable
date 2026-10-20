"""Localized notification texts (Polish / English, chosen by the Home Assistant language).

No Home Assistant imports — testable locally.
"""

from __future__ import annotations

from datetime import date

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
