# ZSE Timetable Bydgoszcz dla Home Assistant (`zse_timetable`)

[English](README.md)

Integracja pobiera plan lekcji wskazanego nauczyciela ze strony [plan.zse.bydgoszcz.pl](https://plan.zse.bydgoszcz.pl/)
(eksport VULCAN Optivum) oraz jego zastępstwa z [zastepstwa.zse.bydgoszcz.pl](https://zastepstwa.zse.bydgoszcz.pl/)
i wystawia je jako `sensor.timetable_<nauczyciel>` — źródło danych dla
[zse-timetable-card](https://github.com/achelminski/zse-timetable-card).
Wysyła też powiadomienie, gdy pojawi się nowy plan albo nauczyciel dostanie zastępstwo.

## Instalacja

### HACS (zalecane)
1. HACS → ⋮ → **Własne repozytoria** → `https://github.com/achelminski/zse-timetable`, typ **Integracja**.
2. Pobierz **ZSE Timetable**, zrestartuj Home Assistant.

O każdym nowym wydaniu HACS informuje w **Ustawienia → Aktualizacje**.

### Ręcznie
Skopiuj `custom_components/zse_timetable/` do `/config/custom_components/zse_timetable/` i zrestartuj Home Assistant.

## Konfiguracja
**Ustawienia → Urządzenia i usługi → Dodaj integrację → ZSE Timetable**
1. Adresy planu i zastępstw (domyślnie ZSE Bydgoszcz).
2. Nauczyciel — z listy z `lista.html` — oraz usługi powiadomień (`notify.*`, np. `mobile_app_<telefon>` albo
   `persistent_notification`; można kilka, puste = tylko zdarzenia).

Opcje: usługi powiadomień, usługi alertów o błędach, interwał sprawdzania (domyślnie 60 min, minimum 15).

## Encje (przykład dla J.Kowalski)
- `sensor.timetable_j_kowalski` — stan: poniedziałek bieżącego tygodnia; atrybuty:
  - `teacher`, `generated`, `valid_from`, `valid_from_text` (cała linia „Obowiązuje od: …” ze stopki planu)
  - `lesson_hours`: `[{nr, start, end}]` — siatka godzin planu obowiązującego dziś
  - `days`: Pn–Pt bieżącego i następnego tygodnia (So/Nd tylko z lekcjami):
    `[{date, weekday, lessons: [{nr, start, end, subject, group, room, substitution, absent?, absent_teacher?, notes?}]}]`;
    `absent_teacher` = `{first_name, last_name}` nieobecnego nauczyciela (`null` dla bloków vacat);
    zastępstwo ma `substitution: true` i po jednym wpisie na każdy numer lekcji
  - `days` i `lesson_hours` są wyłączone z recordera
- `sensor.plan_lekcji_<nauczyciel>_wygenerowano`, `..._obowiazuje_od` — daty ze stopki planu
- `sensor.plan_lekcji_<nauczyciel>_zastepstwa` — liczba nadchodzących zastępstw, lista w atrybucie
- `sensor.plan_lekcji_<nauczyciel>_ostatnie_sprawdzenie` (diagnostyka) — czas ostatniego sprawdzenia, błąd (jeśli był)
  w atrybucie `blad`; zmienia się co interwał, więc każde sprawdzenie widać w historii aktywności

Nazwy encji i urządzenia, treść powiadomień, nazwy dni i etykieta zastępstwa są w języku Home Assistant:
polskim dla `pl`, angielskim w pozostałych przypadkach.

## Działanie
- Co interwał: `lista.html` (odświeża numer `plany/nN.html` po nazwisku — numery zmieniają się między eksportami),
  plan nauczyciela, strona zastępstw — GET warunkowy (ETag / Last-Modified).
- Plan wersjonowany po treści (data wygenerowania, „Obowiązuje od”, godziny, siatka lekcji). Nowa wersja obowiązuje
  od daty „Obowiązuje od” (zapasowo: data wygenerowania); wcześniejsze dni zostają na poprzedniej wersji.
- Komórki planu: strukturalne (`<a class=o>3H</a>-2/2 <span class=p>j.niemiecki</span> <a class=s>205</a>`) dają
  przedmiot = `span.p`, klasę z grupą (`3H-2/2`), salę = `a.s`; wpisane ręcznie (`5I_1 221 PAI`): token liczbowy = sala,
  pierwszy token = klasa, reszta = przedmiot.
- Zastępstwa: tylko wiersze z nauczycielem w kolumnie „zastępca”. Strona pokazuje jeden dzień i jest nadpisywana, więc
  zastępstwa są trzymane w `.storage/zse_timetable.<entry_id>` przez 60 dni; wysłane powiadomienia są zapamiętane (restart
  ich nie powtarza); zastępstwo usunięte ze strony znika z planu.

## Powiadomienia i zdarzenia
Integracja sama woła wybrane usługi `notify.<nazwa>` (tytuł + treść); niedostępna usługa = ostrzeżenie w logu.
Niezależnie odpala zdarzenia do własnych automatyzacji:
- `zse_timetable_updated` — nowy plan: `teacher, generated, valid_from, note, text`
- `zse_timetable_substitution` — nowe zastępstwa nauczyciela: `teacher, date, weekday, lessons[], text`
- `zse_timetable_fetch_error` — nie udało się pobrać planu lub zastępstw (sieć, błąd HTTP, nieoczekiwany układ
  strony): `teacher, error, text`; raz na awarię, przy pierwszym nieudanym sprawdzeniu
- `zse_timetable_fetch_restored` — pierwsze udane sprawdzenie po awarii: `teacher, since, text`

Oba komunikaty o awarii idą na osobną opcję **alerty o błędach** (np. `mobile_app_<telefon>` administratora), nie na
usługi powiadomień o planie. Stan awarii jest w `.storage`, więc restart w trakcie awarii nie powtarza alertu. Gdy
internet straci sam Home Assistant, alert push też nie wyjdzie — komunikat „znów działa” (z czasem początku awarii)
przyjdzie po naprawie.
