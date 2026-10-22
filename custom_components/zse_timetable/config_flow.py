"""Config flow: adresy stron -> wybór nauczyciela z listy planu; opcje: powiadomienia, alerty błędów, interwał."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

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
    DEFAULT_PLAN_URL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SUBSTITUTIONS_URL,
    DOMAIN,
    LIST_PAGE,
    MIN_SCAN_INTERVAL,
    NOTIFY_EXCLUDED,
)


def _notify_selector(hass: HomeAssistant, current: list[str]) -> SelectSelector:
    """Lista usług notify.* (telefony mobile_app i inne); zachowuje wybrane, nawet jeśli zniknęły."""
    services = set(hass.services.async_services_for_domain("notify")) - NOTIFY_EXCLUDED
    return SelectSelector(
        SelectSelectorConfig(
            options=sorted(services | set(current)),
            multiple=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _base_url(url: str) -> str:
    """Katalog planu z końcowym '/', żeby urljoin dał <katalog>/lista.html."""
    url = url.strip()
    path = urlparse(url).path
    if not path.endswith("/") and not path.endswith(".html"):
        url += "/"
    return url


class ZsePlanConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._urls: dict[str, str] = {}
        self._teachers: list[dict] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            urls = {
                CONF_PLAN_URL: _base_url(user_input[CONF_PLAN_URL]),
                CONF_SUBSTITUTIONS_URL: user_input[CONF_SUBSTITUTIONS_URL].strip(),
            }
            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    urljoin(urls[CONF_PLAN_URL], LIST_PAGE),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    resp.raise_for_status()
                    html = parser.decode_html(await resp.read(), resp.headers.get("Content-Type"))
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                self._teachers = parser.parse_teacher_list(html)
                if self._teachers:
                    self._urls = urls
                    return await self.async_step_teacher()
                errors["base"] = "no_teachers"

        schema = vol.Schema(
            {
                vol.Required(CONF_PLAN_URL, default=DEFAULT_PLAN_URL): str,
                vol.Required(CONF_SUBSTITUTIONS_URL, default=DEFAULT_SUBSTITUTIONS_URL): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_teacher(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            teacher = next(t for t in self._teachers if t["label"] == user_input[CONF_TEACHER])
            await self.async_set_unique_id(parser.normalize_name(teacher["name"]))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Plan lekcji {teacher['name']}",
                data={
                    **self._urls,
                    CONF_TEACHER: teacher["label"],
                    CONF_TEACHER_NAME: teacher["name"],
                    CONF_TEACHER_CODE: teacher["code"],
                    CONF_TEACHER_HREF: teacher["href"],
                },
                options={
                    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    CONF_NOTIFY: user_input.get(CONF_NOTIFY, []),
                    CONF_NOTIFY_ERRORS: user_input.get(CONF_NOTIFY_ERRORS, []),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_TEACHER): SelectSelector(
                    SelectSelectorConfig(
                        options=[t["label"] for t in self._teachers],
                        mode=SelectSelectorMode.DROPDOWN,
                        sort=True,
                    )
                ),
                vol.Optional(CONF_NOTIFY, default=[]): _notify_selector(self.hass, []),
                vol.Optional(CONF_NOTIFY_ERRORS, default=[]): _notify_selector(self.hass, []),
            }
        )
        return self.async_show_form(step_id="teacher", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ZsePlanOptionsFlow()


class ZsePlanOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_NOTIFY: user_input.get(CONF_NOTIFY, []),
                    CONF_NOTIFY_ERRORS: user_input.get(CONF_NOTIFY_ERRORS, []),
                }
            )
        current = self.config_entry.options.get(CONF_NOTIFY, [])
        current_errors = self.config_entry.options.get(CONF_NOTIFY_ERRORS, [])
        schema = vol.Schema(
            {
                vol.Optional(CONF_NOTIFY, default=current): _notify_selector(self.hass, current),
                vol.Optional(CONF_NOTIFY_ERRORS, default=current_errors): _notify_selector(
                    self.hass, current_errors
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=1440,
                        step=5,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
