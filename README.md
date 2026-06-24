# Morning digest

Каждое утро тянет события календаря и напоминания из iCloud (CalDAV) и шлёт
дайджест в Telegram. Рассчитан на работу в Docker на Synology NAS.

Планировщик — [supercronic](https://github.com/aptible/supercronic) внутри
контейнера (cron-семантика, логи в stdout). `digest.py` — one-shot: по
расписанию запускается, отправляет дайджест и завершается.

## Что внутри

- `digest.py` — сбор данных + отправка, один прогон за запуск.
- `entrypoint.sh` — рендерит crontab из `CRON_SCHEDULE` и запускает supercronic.
- `Dockerfile` — `python:3.12-slim` + supercronic, non-root, с `HEALTHCHECK`.
- `docker-compose.yml` — автоперезапуск демона, лимиты, ротация логов.
- `test_digest.py` — юнит-тесты на форматирование/экранирование (без сети).

## Настройка

1. Скопировать пример окружения и заполнить:
   ```sh
   cp .env.example .env
   ```
   - `APPLE_APP_PASSWORD` — **app-specific password**, не обычный пароль Apple ID
     (создаётся на <https://appleid.apple.com> → Войти и безопасность → Пароли для программ).
   - `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` — бот от [@BotFather](https://t.me/BotFather)
     и id чата, куда слать.
   - `CRON_SCHEDULE` — когда слать (cron-выражение, по умолчанию `0 8 * * *`).
   - `TZ` и `TIMEZONE` держать одинаковыми.
2. `.env` уже в `.gitignore` — секреты в репозиторий не попадут.

## Запуск на Synology

Через Container Manager (Project) или CLI:

```sh
docker compose up -d --build
```

Проверить отправку прямо сейчас, не дожидаясь расписания (разовый прогон,
контейнер сразу завершится):

```sh
docker compose run --rm morning-digest python digest.py
```

Логи планировщика:
```sh
docker logs -f morning-digest
```

Состояние здоровья (контейнер становится `unhealthy`, если успешной отправки
не было > 25 часов — например, протух app-password или пропал интернет):
```sh
docker inspect --format '{{.State.Health.Status}}' morning-digest
```

## Поведение при сбоях

- Сетевые вызовы (iCloud, Telegram) повторяются с экспоненциальной паузой
  (3 попытки: 5 / 10 / 20 c).
- Если прогон всё же падает — приходит сообщение об ошибке в тот же Telegram-чат,
  процесс завершается с ненулевым кодом (видно в `docker logs`), а `HEALTHCHECK`
  со временем переводит контейнер в `unhealthy`.

## Тесты

```sh
pip install pytest
python -m pytest
```
