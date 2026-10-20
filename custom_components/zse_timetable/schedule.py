"""Budowa struktury planu (dni -> lekcje) z zapisanych wersji planu i zastępstw.

Bez importów Home Assistant — testowalne lokalnie. Wynik jest serializowalny
do JSON (atrybuty sensora timetable).
"""

from __future__ import annotations

from datetime import date, time, timedelta

SUBSTITUTION_PREFIX = "Zastępstwo"

WEEKDAY_NAMES = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]


def lesson_parts(lesson: dict) -> tuple[str, str | None]:
    """(przedmiot, klasa z grupą) z komórki planu.

    Komórka strukturalna: przedmiot = span.p, klasa = a.o + tekst grupy za nią
    ('5H' + '-2/2'), czyli summary bez przedmiotu. Komórka wpisana ręcznie
    ('5I_1 221 PAI' -> po wycięciu sali '5I_1 PAI'): pierwszy token = klasa,
    reszta = przedmiot; pojedynczy token ('N') = przedmiot.
    """
    summary = lesson.get("summary") or lesson.get("raw") or ""
    subject = lesson.get("subject")
    if subject:
        group = " ".join(summary.replace(subject, "", 1).split())
        return subject, group or lesson.get("class")
    tokens = summary.split()
    if len(tokens) >= 2:
        return " ".join(tokens[1:]), tokens[0]
    return summary, None


def valid_from_text(version: dict | None) -> str | None:
    """Linia „Obowiązuje od: …” ze strony; dla wersji zapisanych bez niej — odtworzona z daty i uwagi."""
    if not version:
        return None
    if version.get("valid_from_text"):
        return version["valid_from_text"]
    if not version.get("valid_from"):
        return None
    day = date.fromisoformat(version["valid_from"]).strftime("%d.%m.%Y")
    note = version.get("note")
    return f"Obowiązuje od: {day} r." + (f" - {note}" if note else "")


def plan_content(version: dict) -> tuple:
    """Część wersji planu, której zmiana oznacza nowy plan (bez daty pobrania)."""
    return (
        version.get("generated"),
        version.get("valid_from"),
        repr(version.get("hours")),
        repr(version.get("grid")),
    )


def version_for_day(versions: list[dict], day: date) -> dict | None:
    """Najnowsza wersja, która obowiązuje w danym dniu.

    Nowsza generacja wygrywa od swojego valid_from wzwyż; dla dni sprzed
    pierwszej znanej wersji używamy najstarszej (lepsze niż pusty tydzień).
    """
    for version in reversed(versions):
        start = version.get("valid_from") or version.get("generated")
        if start is None or date.fromisoformat(start) <= day:
            return version
    return versions[0] if versions else None


def _hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def lesson_times(hours: dict, numbers: list[int]) -> tuple[time, time] | None:
    """Czas od początku pierwszej do końca ostatniej lekcji z listy."""
    known = [hours[str(n)] for n in numbers if str(n) in hours]
    if not known:
        return None
    return _hhmm(known[0][0]), _hhmm(known[-1][1])


def lesson_hours(version: dict | None) -> list[dict]:
    """Siatka Nr/Godz: [{nr, start, end}] posortowana po numerze lekcji."""
    hours = version["hours"] if version else {}
    return [
        {"nr": int(nr), "start": hours[nr][0], "end": hours[nr][1]}
        for nr in sorted(hours, key=int)
    ]


def build_day(
    versions: list[dict],
    substitutions: dict[str, list[dict]],
    day: date,
    substitution_label: str = SUBSTITUTION_PREFIX,
    weekday_names: list[str] = WEEKDAY_NAMES,
) -> dict:
    """Jeden dzień: lekcje z obowiązującej wersji planu + zastępstwa (po jednej na nr lekcji)."""
    version = version_for_day(versions, day)
    hours = version["hours"] if version else {}
    lessons: list[dict] = []
    if version:
        for nr, cell in version["grid"].get(str(day.weekday()), {}).items():
            slot = hours.get(nr)
            for lesson in cell:
                subject, group = lesson_parts(lesson)
                lessons.append(
                    {
                        "nr": int(nr),
                        "start": slot[0] if slot else None,
                        "end": slot[1] if slot else None,
                        "subject": subject,
                        "group": group,
                        "room": lesson.get("room"),
                        "substitution": False,
                    }
                )
    for row in substitutions.get(day.isoformat(), []):
        numbers = row.get("lessons") or []
        for nr in numbers or [None]:
            slot = hours.get(str(nr)) if nr is not None else None
            lessons.append(
                {
                    "nr": nr,
                    "start": slot[0] if slot else None,
                    "end": slot[1] if slot else None,
                    "subject": substitution_label,
                    "group": row.get("group") or row.get("opis"),
                    "room": row.get("room"),
                    "substitution": True,
                    "absent": row.get("absent"),
                    "notes": row.get("notes") or None,
                }
            )
    lessons.sort(key=lambda les: (les["nr"] is None, les["nr"] or 0, les["substitution"]))
    return {"date": day.isoformat(), "weekday": weekday_names[day.weekday()], "lessons": lessons}


def build_timetable(
    versions: list[dict],
    substitutions: dict[str, list[dict]],
    start: date,
    weeks: int = 2,
    substitution_label: str = SUBSTITUTION_PREFIX,
    weekday_names: list[str] = WEEKDAY_NAMES,
) -> list[dict]:
    """Dni od poniedziałku tygodnia `start` przez `weeks` tygodni.

    Pn–Pt zawsze (także puste — tabela ma stałe kolumny), sobota/niedziela
    tylko jeśli mają lekcje.
    """
    monday = start - timedelta(days=start.weekday())
    days = []
    for offset in range(7 * weeks):
        day = monday + timedelta(days=offset)
        built = build_day(versions, substitutions, day, substitution_label, weekday_names)
        if day.weekday() < 5 or built["lessons"]:
            days.append(built)
    return days
