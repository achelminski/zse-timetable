# ZSE Bydgoszcz timetable for Home Assistant (`zse_timetable`)

[Polski](README.pl.md)

Custom integration that reads a teacher's timetable from [plan.zse.bydgoszcz.pl](https://plan.zse.bydgoszcz.pl/)
(VULCAN Optivum export) and the teacher's substitutions from
[zastepstwa.zse.bydgoszcz.pl](https://zastepstwa.zse.bydgoszcz.pl/), and exposes them as
`sensor.timetable_<teacher>` — the data source for
[zse-timetable-card](https://github.com/achelminski/zse-timetable-card).
It also sends a notification when a new timetable is published or the teacher is assigned a substitution.

## Installation

### HACS (recommended)
1. HACS → ⋮ → **Custom repositories** → `https://github.com/achelminski/zse-timetable`, type **Integration**.
2. Download **ZSE Timetable**, restart Home Assistant.

HACS shows an update in **Settings → Updates** whenever a new release is published.

### Manual
Copy `custom_components/zse_timetable/` to `/config/custom_components/zse_timetable/` and restart Home Assistant.

## Configuration
**Settings → Devices & services → Add integration → ZSE Timetable**
1. Timetable and substitutions URLs (defaults point to ZSE Bydgoszcz).
2. Teacher — picked from the list on `lista.html` — and notification services (`notify.*`, e.g.
   `mobile_app_<phone>` or `persistent_notification`; several allowed, empty = events only).

Options: notification services, check interval (default 60 min, minimum 15).

## Entities (example for teacher J.Kowalski)
- `sensor.timetable_j_kowalski` — state: Monday of the current week; attributes:
  - `teacher`, `generated`, `valid_from`, `valid_from_text` (the whole “Obowiązuje od: …” line from the timetable footer)
  - `lesson_hours`: `[{nr, start, end}]` — lesson grid of the timetable valid today
  - `days`: Mon–Fri of the current and next week (Sat/Sun only when they have lessons):
    `[{date, weekday, lessons: [{nr, start, end, subject, group, room, substitution, absent?, absent_teacher?, notes?}]}]`;
    `absent_teacher` = `{first_name, last_name}` of the absent teacher (`null` for vacat blocks);
    a substitution has `substitution: true` and one entry per lesson number
  - `days` and `lesson_hours` are excluded from the recorder
- `sensor.<device>_generated`, `sensor.<device>_valid_from` — dates from the timetable footer
- `sensor.<device>_substitutions` — number of upcoming substitutions, list in an attribute
- `sensor.<device>_last_check` (diagnostic) — time of the last check, error (if any) in the `blad` attribute;
  changes every interval, so each check shows up in the logbook

Entity and device names, notification texts, weekday names and the substitution label follow the
Home Assistant language: Polish for `pl`, English otherwise.

## How it works
- Every interval: `lista.html` (re-resolves the teacher's `plany/nN.html` by name, the numbers change between
  exports), the teacher's timetable and the substitutions page — conditional GET (ETag / Last-Modified).
- The timetable is versioned by content (generation date, “valid from” date, lesson hours, lesson grid).
  A new version applies from its “Obowiązuje od” date (fallback: generation date); earlier days keep the previous version.
- Timetable cells: structured cells (`<a class=o>3H</a>-2/2 <span class=p>j.niemiecki</span> <a class=s>205</a>`)
  give subject = `span.p`, group = class + group (`3H-2/2`), room = `a.s`; hand-typed cells (`5I_1 221 PAI`):
  numeric token = room, first token = class, rest = subject.
- Substitutions: only rows where the teacher is in the “zastępca” (substitute) column. The page shows a single day and
  is overwritten, so substitutions are kept in `.storage/zse_timetable.<entry_id>` for 60 days; sent notifications are
  remembered, so a restart does not repeat them; a substitution removed from the page disappears from the timetable.

## Notifications and events
The integration calls the selected `notify.<service>` itself (title + message); an unavailable service is logged as a warning.
It also fires bus events for your own automations:
- `zse_timetable_updated` — new timetable: `teacher, generated, valid_from, note, text`
- `zse_timetable_substitution` — new rows with the teacher as substitute: `teacher, date, weekday, lessons[], text`
