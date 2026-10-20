"""Stałe integracji ZSE Timetable."""

DOMAIN = "zse_timetable"

CONF_PLAN_URL = "plan_url"
CONF_SUBSTITUTIONS_URL = "substitutions_url"
CONF_TEACHER = "teacher"  # etykieta z listy, np. "J.Kowalski (Kw)"
CONF_TEACHER_NAME = "teacher_name"
CONF_TEACHER_CODE = "teacher_code"
CONF_TEACHER_HREF = "teacher_href"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NOTIFY = "notify_services"  # nazwy usług notify.* (bez domeny), np. mobile_app_<telefon>

# Usługi notify, których nie da się wywołać samym title/message (wymagają targetu) albo są zbiorcze.
NOTIFY_EXCLUDED = {"send_message", "notify"}

DEFAULT_PLAN_URL = "https://plan.zse.bydgoszcz.pl/"
DEFAULT_SUBSTITUTIONS_URL = "https://zastepstwa.zse.bydgoszcz.pl/"
DEFAULT_SCAN_INTERVAL = 60  # minuty
MIN_SCAN_INTERVAL = 15

LIST_PAGE = "lista.html"

STORAGE_VERSION = 1
MAX_PLAN_VERSIONS = 10
KEEP_SUBSTITUTIONS_DAYS = 60

EVENT_PLAN_UPDATED = "zse_timetable_updated"
EVENT_SUBSTITUTION = "zse_timetable_substitution"
