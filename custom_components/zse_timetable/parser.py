"""Parsery stron VULCAN Optivum (plan lekcji) i strony zastępstw ZSE.

Moduł celowo nie importuje niczego z Home Assistant — da się go testować
lokalnie na zapisanych próbkach stron (zob. tests/).
"""

from __future__ import annotations

import re
from datetime import date
from html.parser import HTMLParser

_VOID_TAGS = {"br", "img", "meta", "link", "hr", "input", "col", "base", "area"}
_WS_RE = re.compile(r"\s+")
_DATE_RE = r"(\d{1,2})\.(\d{1,2})\.(\d{4})"
_HOURS_RE = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
_ROOM_RE = re.compile(r"^\d{1,3}[a-zA-Z]?$")
_TEACHER_HREF_RE = re.compile(r"(?:^|/)n\d+\.html$")

WEEKDAYS_PL = {
    "poniedziałek": 0,
    "wtorek": 1,
    "środa": 2,
    "czwartek": 3,
    "piątek": 4,
    "sobota": 5,
    "niedziela": 6,
}


# --- minimalne drzewo DOM ---------------------------------------------------


class Node:
    """Element HTML: tag, atrybuty, dzieci (Node albo str)."""

    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[Node | str] = []

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").lower().split())

    def iter(self, tag: str | None = None):
        """Wszystkie elementy potomne w kolejności dokumentu."""
        for child in self.children:
            if isinstance(child, Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.iter(tag)

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, Node):
                parts.append("\n" if child.tag == "br" else child.text())
            else:
                parts.append(child)
        return "".join(parts)


class _TreeBuilder(HTMLParser):
    """Tolerancyjny builder: niedomknięte tagi zamyka przy domknięciu rodzica."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs})
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._stack[-1].children.append(Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data):
        self._stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


def clean(text: str) -> str:
    """Zamienia &nbsp; i ciągi białych znaków na pojedyncze spacje."""
    return _WS_RE.sub(" ", text.replace("\xa0", " ")).strip()


def decode_html(raw: bytes, content_type: str | None = None) -> str:
    """Dekoduje stronę wg charsetu z nagłówka albo z <meta> (domyślnie UTF-8)."""
    charset = None
    for source in (content_type or "", raw[:4096].decode("ascii", "ignore")):
        match = re.search(r"charset\s*=\s*[\"']?([\w-]+)", source, re.IGNORECASE)
        if match:
            charset = match.group(1)
            break
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _to_date(match: re.Match | None) -> date | None:
    if not match:
        return None
    day, month, year = (int(g) for g in match.groups()[:3])
    try:
        return date(year, month, day)
    except ValueError:
        return None


# --- nazwiska ----------------------------------------------------------------


def split_teacher_label(label: str) -> tuple[str, str | None]:
    """'J.Kowalski (Kw)' -> ('J.Kowalski', 'Kw')."""
    label = clean(label)
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", label)
    if match:
        return match.group(1).strip(), match.group(2).strip() or None
    return label, None


def normalize_name(name: str) -> str:
    """'J. Kowalski' / 'J.Kowalski (Kw)' -> 'j.kowalski'."""
    name, _ = split_teacher_label(name)
    return re.sub(r"\s+", "", name).casefold()


def teacher_matches(candidate: str, teacher: str) -> bool:
    """Czy wpis z kolumny „zastępca” wskazuje nauczyciela z listy planu.

    Plan podaje 'J.Kowalski', zastępstwa 'J. Kowalski'; na wypadek pełnego
    imienia ('Jan Kowalski') porównujemy też inicjał + nazwisko.
    """
    if not candidate or not teacher:
        return False
    if normalize_name(candidate) == normalize_name(teacher):
        return True
    t_name, _ = split_teacher_label(teacher)
    if "." not in t_name:
        return False
    initial, surname = t_name.split(".", 1)
    words = clean(candidate).replace(".", ". ").split()
    if len(words) < 2:
        return False
    return (
        words[-1].casefold() == surname.strip().casefold()
        and words[0].casefold().startswith(initial.strip().casefold())
    )


# --- lista nauczycieli ---------------------------------------------------------


def parse_teacher_list(html: str) -> list[dict]:
    """Nauczyciele z lista.html: [{label, name, code, href}] (href względny)."""
    teachers = []
    for link in parse_html(html).iter("a"):
        href = link.attrs.get("href", "")
        if not _TEACHER_HREF_RE.search(href):
            continue
        label = clean(link.text())
        name, code = split_teacher_label(label)
        teachers.append({"label": label, "name": name, "code": code, "href": href})
    return teachers


def find_teacher(teachers: list[dict], name: str, code: str | None) -> dict | None:
    """Szuka po nazwisku (i kodzie, jeśli jest) — numery nN zmieniają się między generacjami."""
    wanted = normalize_name(name)
    same_name = [t for t in teachers if normalize_name(t["name"]) == wanted]
    for teacher in same_name:
        if code is None or teacher["code"] == code:
            return teacher
    return same_name[0] if same_name else None


# --- plan nauczyciela ------------------------------------------------------------


def _parse_cell(cell: Node) -> list[dict]:
    """Komórka planu -> lista lekcji (kilka wpisów rozdziela <br>).

    Format strukturalny: <a class=o>5H</a>-2/2 <span class=p>Pr.Ap.In.</span> <a class=s>221</a>
    Format ręczny: czysty tekst, np. '5I_1 221 PAI'.
    """
    entries: list[list[tuple[str, str]]] = [[]]

    def walk(node: Node) -> None:
        for child in node.children:
            if isinstance(child, str):
                entries[-1].append(("text", child))
            elif child.tag == "br":
                entries.append([])
            elif child.tag == "a" and "s" in child.classes:
                entries[-1].append(("room", child.text()))
            elif child.tag == "a" and "o" in child.classes:
                entries[-1].append(("class", child.text()))
            elif child.tag == "span" and "p" in child.classes:
                entries[-1].append(("subject", child.text()))
            else:
                walk(child)

    walk(cell)
    lessons = []
    for parts in entries:
        raw = clean("".join(text for _, text in parts))
        if not raw:
            continue
        room = next((clean(t) for kind, t in parts if kind == "room"), None)
        subject = next((clean(t) for kind, t in parts if kind == "subject"), None)
        group = next((clean(t) for kind, t in parts if kind == "class"), None)
        if room is not None:
            summary = clean("".join(t for kind, t in parts if kind != "room"))
        else:
            # Tekst ręczny: pierwszy token wyglądający na salę traktujemy jako salę.
            tokens = raw.split()
            room = next((tok for tok in tokens if _ROOM_RE.match(tok)), None)
            summary = " ".join(tok for tok in tokens if tok != room) if room else raw
        lessons.append(
            {
                "summary": summary or raw,
                "room": room,
                "class": group,
                "subject": subject,
                "raw": raw,
            }
        )
    return lessons


def parse_teacher_plan(html: str) -> dict:
    """Plan nauczyciela (plany/nN.html).

    Zwraca dict serializowalny do JSON:
      title, generated (ISO), valid_from (ISO|None), note,
      hours: {"0": ["07:05", "07:50"], ...},
      grid: {"0".."4": {"<nr lekcji>": [lekcja, ...]}}  (klucz dnia = weekday())
    """
    root = parse_html(html)
    table = next((t for t in root.iter("table") if "tabela" in t.classes), None)
    if table is None:
        raise ValueError("Brak tabeli planu (table.tabela)")

    day_columns: list[int] = []
    hours: dict[str, list[str]] = {}
    grid: dict[str, dict[str, list[dict]]] = {}
    for row in table.iter("tr"):
        headers = [c for c in row.children if isinstance(c, Node) and c.tag == "th"]
        if headers:
            day_columns = [
                WEEKDAYS_PL[name]
                for name in (clean(h.text()).casefold() for h in headers)
                if name in WEEKDAYS_PL
            ]
            continue
        cells = [c for c in row.children if isinstance(c, Node) and c.tag == "td"]
        nr_cell = next((c for c in cells if "nr" in c.classes), None)
        if nr_cell is None:
            continue
        nr = clean(nr_cell.text())
        hours_cell = next((c for c in cells if "g" in c.classes), None)
        if hours_cell is not None:
            match = _HOURS_RE.search(hours_cell.text())
            if match:
                h1, m1, h2, m2 = match.groups()
                hours[nr] = [f"{int(h1):02d}:{m1}", f"{int(h2):02d}:{m2}"]
        lesson_cells = [c for c in cells if "l" in c.classes]
        columns = day_columns or list(range(len(lesson_cells)))
        for weekday, cell in zip(columns, lesson_cells):
            lessons = _parse_cell(cell)
            if lessons:
                grid.setdefault(str(weekday), {})[nr] = lessons

    text = clean(root.text())
    generated = _to_date(re.search(r"wygenerowano\s+" + _DATE_RE, text, re.IGNORECASE))
    valid_match = re.search(
        r"Obowiązuje od:?\s*" + _DATE_RE + r"\s*r?\.?\s*-?\s*(.*?)(?:Drukuj plan|$)",
        text,
        re.IGNORECASE,
    )
    valid_from = _to_date(valid_match)
    # Cała linia „Obowiązuje od: … r. - uwaga” — najkrótsza komórka zaczynająca się od tego napisu
    # (komórki-kontenery układu strony też zawierają ten tekst, ale nie na początku).
    valid_lines = [
        line for line in (clean(td.text()) for td in root.iter("td")) if line.casefold().startswith("obowiązuje od")
    ]
    title_node = next((s for s in root.iter("span") if "tytulnapis" in s.classes), None)
    return {
        "title": clean(title_node.text()) if title_node else None,
        "generated": generated.isoformat() if generated else None,
        "valid_from": valid_from.isoformat() if valid_from else None,
        "valid_from_text": min(valid_lines, key=len) if valid_lines else None,
        "note": clean(valid_match.group(4)) if valid_match else None,
        "hours": hours,
        "grid": grid,
    }


# --- zastępstwa ---------------------------------------------------------------------


def _lesson_numbers(text: str) -> list[int]:
    """'3' -> [3], '3-4' -> [3, 4], '3,5' -> [3, 5]."""
    rng = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", text)
    if rng:
        first, last = int(rng.group(1)), int(rng.group(2))
        return list(range(first, last + 1)) if first <= last else [first]
    return [int(n) for n in re.findall(r"\d+", text)]


def split_opis(opis: str) -> tuple[str, str | None]:
    """'5 I(1) - 221' -> ('5 I(1)', '221')."""
    if " - " in opis:
        group, room = opis.rsplit(" - ", 1)
        return group.strip(), room.strip() or None
    return opis, None


def parse_substitutions(html: str) -> list[dict]:
    """Strona zastępstw -> [{date (ISO), weekday_name, blocks: [{absent, rows: [...]}]}].

    Wiersz: {lesson (tekst), lessons [int], opis, deputy, notes}.
    Nagłówek bloku (komórka colspan) to nauczyciel nieobecny / vacat.
    """
    days: list[dict] = []
    for row in parse_html(html).iter("tr"):
        cells = [c for c in row.children if isinstance(c, Node) and c.tag == "td"]
        texts = [clean(c.text()) for c in cells]
        if not any(texts):
            continue
        if len(cells) == 1:
            title = re.search(r"Zastępstwa w dniu\s+" + _DATE_RE + r"\s*(\S*)", texts[0], re.IGNORECASE)
            if title:
                day = _to_date(title)
                days.append(
                    {
                        "date": day.isoformat() if day else None,
                        "weekday_name": title.group(4) or None,
                        "blocks": [],
                    }
                )
            elif days:
                days[-1]["blocks"].append({"absent": texts[0], "rows": []})
            continue
        if len(cells) < 3 or not days:
            continue
        if texts[0].casefold() == "lekcja":
            continue
        if not days[-1]["blocks"]:
            days[-1]["blocks"].append({"absent": None, "rows": []})
        days[-1]["blocks"][-1]["rows"].append(
            {
                "lesson": texts[0],
                "lessons": _lesson_numbers(texts[0]),
                "opis": texts[1],
                "deputy": texts[2],
                "notes": texts[3] if len(texts) > 3 else "",
            }
        )
    return days


def substitutions_for(days: list[dict], teacher: str) -> dict[str, list[dict]]:
    """Wiersze, w których nauczyciel jest w kolumnie „zastępca”, pogrupowane po dacie.

    Każdy dzień ze strony występuje w wyniku (także z pustą listą), żeby
    odwołane zastępstwo dało się wykasować.
    """
    result: dict[str, list[dict]] = {}
    for day in days:
        if not day["date"]:
            continue
        rows = result.setdefault(day["date"], [])
        for block in day["blocks"]:
            for row in block["rows"]:
                if teacher_matches(row["deputy"], teacher):
                    group, room = split_opis(row["opis"])
                    rows.append({**row, "absent": block["absent"], "group": group, "room": room})
    return result
