#!/usr/bin/env python3
"""
Morning digest: iCloud Calendar + Reminders → Telegram
Timezone: Europe/Berlin, отправка в 08:00 каждый день
"""

import datetime
import logging
import os
import sys
import time

import caldav
import pytz
import requests
from icalendar import Calendar

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

APPLE_ID = os.environ["APPLE_ID"]
APPLE_APP_PASSWORD = os.environ["APPLE_APP_PASSWORD"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Berlin")

CALDAV_URL = "https://caldav.icloud.com"
CALDAV_TIMEOUT = int(os.environ.get("CALDAV_TIMEOUT", "30"))

# Сеть нестабильна — повторяем с экспоненциальной паузой.
MAX_RETRIES = 3
RETRY_BACKOFF = 5  # секунд: 5, 10, 20

# Лимит Telegram на одно сообщение — 4096 символов (берём с запасом).
TELEGRAM_MAX_LEN = 3900

# Файл-heartbeat для Docker HEALTHCHECK — обновляется при успешной отправке.
HEARTBEAT_FILE = os.environ.get("HEARTBEAT_FILE", "/tmp/last_success")

# Символы, которые MarkdownV2 требует экранировать обратным слешем.
_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def md_escape(text: str) -> str:
    """Экранирует все спецсимволы MarkdownV2."""
    return "".join("\\" + ch if ch in _MDV2_SPECIAL else ch for ch in text)


def with_retries(fn, *, what: str):
    """Выполняет fn() с экспоненциальным backoff. Пробрасывает последнюю ошибку."""
    delay = RETRY_BACKOFF
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 — сознательно ретраим любую ошибку
            last_exc = e
            log.warning("%s failed (attempt %d/%d): %s", what, attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
    assert last_exc is not None
    raise last_exc


def icloud_client() -> caldav.DAVClient:
    return caldav.DAVClient(
        url=CALDAV_URL,
        username=APPLE_ID,
        password=APPLE_APP_PASSWORD,
        timeout=CALDAV_TIMEOUT,
    )


def get_todays_events(calendars, tz) -> list[tuple[datetime.datetime, str, str]]:
    """Возвращает список (datetime, time_str, summary) для сегодняшних событий."""
    today = datetime.date.today()
    start = tz.localize(datetime.datetime.combine(today, datetime.time.min))
    end = tz.localize(datetime.datetime.combine(today, datetime.time.max))

    events = []
    for cal in calendars:
        try:
            results = cal.search(start=start, end=end, event=True, expand=True)
            for vevent in results:
                vevent.load()
                parsed = Calendar.from_ical(vevent.data)
                for component in parsed.walk():
                    if component.name != "VEVENT":
                        continue
                    summary = str(component.get("summary", "Без названия"))
                    dtstart = component.get("dtstart")
                    if not dtstart:
                        continue
                    dt = dtstart.dt
                    if isinstance(dt, datetime.datetime):
                        if dt.tzinfo:
                            dt = dt.astimezone(tz)
                        else:
                            dt = tz.localize(dt)
                        time_str = dt.strftime("%H:%M")
                        sort_key = dt
                    else:
                        # all-day
                        time_str = "весь день"
                        sort_key = tz.localize(
                            datetime.datetime.combine(dt, datetime.time.min)
                        )
                    events.append((sort_key, time_str, summary))
        except Exception as e:
            log.warning("Skipping calendar %s: %s", cal, e)

    events.sort(key=lambda x: x[0])
    return events


def get_todays_reminders(calendars) -> list[str]:
    """Возвращает незавершённые напоминания со сроком сегодня или раньше."""
    today = datetime.date.today()
    reminders = []

    for cal in calendars:
        try:
            # include_completed=True: при False caldav шлёт iCloud сложный
            # REPORT-фильтр, который тот отвергает с 500. Завершённые отсекаем ниже.
            todos = cal.todos(include_completed=True)
            for todo in todos:
                todo.load()
                parsed = Calendar.from_ical(todo.data)
                for component in parsed.walk():
                    if component.name != "VTODO":
                        continue
                    status = str(component.get("status", "")).upper()
                    if status == "COMPLETED":
                        continue
                    summary = str(component.get("summary", "Без названия"))
                    due = component.get("due")
                    if due:
                        dt = due.dt
                        due_date = dt.date() if isinstance(dt, datetime.datetime) else dt
                        if due_date <= today:
                            reminders.append(summary)
                    else:
                        # Напоминания без срока тоже показываем
                        reminders.append(summary)
        except Exception as e:
            log.warning("Skipping todos in calendar %s: %s", cal, e)

    return reminders


def format_message(events: list[tuple], reminders: list[str]) -> str:
    today = datetime.date.today()
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    weekday = weekdays[today.weekday()]
    date_str = md_escape(today.strftime("%d.%m.%Y"))
    lines = [f"☀️ *Доброе утро\\! {weekday}, {date_str}*\n"]

    if events:
        lines.append("📅 *Встречи сегодня:*")
        for _, time_str, summary in events:
            lines.append(f"  • {md_escape(time_str)} — {md_escape(summary)}")
    else:
        lines.append("📅 Встреч сегодня нет")

    lines.append("")

    if reminders:
        lines.append("✅ *Напоминалки:*")
        for r in reminders[:15]:  # не больше 15
            lines.append(f"  • {md_escape(r)}")
    else:
        lines.append("✅ Напоминалок нет")

    return "\n".join(lines)


def _split_for_telegram(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Режет сообщение по строкам, чтобы каждый кусок влезал в лимит Telegram."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_telegram(text: str, *, markdown: bool = True) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chunk in _split_for_telegram(text):
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": chunk}
        if markdown:
            payload["parse_mode"] = "MarkdownV2"

        def _post():
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code >= 400:
                # Берём описание из тела, НЕ из URL — иначе в лог утечёт токен.
                try:
                    desc = resp.json().get("description", resp.text[:200])
                except ValueError:
                    desc = resp.text[:200]
                raise RuntimeError(f"Telegram API {resp.status_code}: {desc}")
            return resp

        with_retries(_post, what="telegram sendMessage")
    log.info("Message sent to Telegram")


def notify_error(err: Exception) -> None:
    """Best-effort алерт об ошибке в тот же чат (без разметки, без ретраев-каскада)."""
    try:
        send_telegram(
            f"⚠️ Morning digest упал: {type(err).__name__}: {err}",
            markdown=False,
        )
    except Exception:
        log.exception("Failed to send error notification")


def _touch_heartbeat() -> None:
    try:
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(datetime.datetime.now(pytz.utc).isoformat())
    except OSError as e:
        log.warning("Could not write heartbeat file: %s", e)


def run_digest() -> bool:
    """Один прогон дайджеста. True — успех, False — была ошибка (уже залогирована)."""
    log.info("Running morning digest…")
    tz = pytz.timezone(TIMEZONE)
    try:
        client = icloud_client()
        principal = with_retries(client.principal, what="caldav principal")
        calendars = with_retries(principal.calendars, what="caldav calendars")
        events = get_todays_events(calendars, tz)
        reminders = get_todays_reminders(calendars)
        message = format_message(events, reminders)
        send_telegram(message)
        _touch_heartbeat()
        return True
    except Exception as e:
        log.exception("Digest failed")
        notify_error(e)
        return False


if __name__ == "__main__":
    # One-shot: планировщик — внешний (supercronic/cron). Здесь только один прогон.
    # Ненулевой код выхода → ошибка видна в логах cron, помимо Telegram-алерта.
    sys.exit(0 if run_digest() else 1)
