# AGENTS.md

Заметки для агентов/контрибьюторов. Сюда записываем **каждый реально пойманный
баг как правило**, чтобы он не повторился. Кратко, по делу, с причиной.

## Деплой и окружение

Прод — Synology NAS (DSM 7, Container Manager), деплой по SSH через `deploy.sh`.

- **Целевая директория:** `/volume2/docker/morning-digest` (SSD-том, shared folder).
  Данные держим только в shared folder — иначе DSM может снести при обновлении.
- **docker на Synology — root-only.** Сокет `/var/run/docker.sock` принадлежит
  `root:root`. Команды идут через `sudo /usr/local/bin/docker` (настроен
  passwordless sudo в `/etc/sudoers.d/docker-nopasswd`, только для docker-бинаря).
- **git на NAS нет.** Деплой = `rsync` с рабочей машины, не `git pull` на NAS.
- **`.env` живёт только на NAS** (`chmod 600`), исключён из `rsync --delete`.
  В git не коммитим (см. `.gitignore`).

## Грабли, на которые уже наступили (НЕ повторять)

1. **Non-root + `COPY` сохраняет режим из контекста сборки.**
   У автора файлы локально `-rw-------` (umask 077). `COPY` тащит этот режим,
   образ бежит под uid 1000 (`app`) → `Permission denied` на чтение `/app/*`.
   → В Dockerfile **явно** выставлять права после `COPY`
   (`chmod 0644 digest.py && chmod 0755 entrypoint.sh`). Не полагаться на
   режим файлов в репозитории.

2. **supercronic выполняет команду cron БЕЗ шелла.**
   `0 8 * * * cd /app && python digest.py` падает с
   `Failed to fork exec: no such file or directory` — `cd` это shell-builtin.
   → Только абсолютный бинарь + абсолютный путь, без `cd`/`&&`/пайпов/`$VAR`:
   `0 8 * * * /usr/local/bin/python /app/digest.py`.

3. **Entrypoint-обёртка над планировщиком должна пробрасывать аргументы.**
   `ENTRYPOINT ["./entrypoint.sh"]`, который всегда `exec supercronic`, ломает
   разовый прогон: `docker compose run --rm <svc> python digest.py` запускал
   supercronic, а не команду. → В entrypoint: `[ "$#" -gt 0 ] && exec "$@"`
   до запуска планировщика.

4. **Секреты не должны попадать в логи.**
   `requests` кладёт полный URL (с токеном бота) в текст `HTTPError`. Логирование
   исключения светило токен в логах и в чате. → Не логировать сырое исключение
   с URL; брать `description` из тела ответа Telegram
   (`resp.json()["description"]`), а не из URL.

5. **Synology-ядро не поддерживает CPU CFS-квоты.**
   `cpus: 0.5` в compose → `NanoCPUs can not be set ... kernel does not support
   CPU CFS scheduler`. → Не ставить `cpus:` лимит. `mem_limit` работает.

6. **supercronic как PID 1 на ядре Synology фаталит в reaper'е.**
   `exec supercronic /tmp/crontab` (pid1, reaping включён) падает с
   `Failed to fork exec: no such file or directory` ещё ДО чтения crontab —
   контейнер уходит в рестарт-цикл (растущий backoff Docker). Прямой запуск
   supercronic (не pid1) работает. → Запускать с `-no-reap`:
   `exec supercronic -no-reap "$CRONTAB"`. Reaper не нужен — задача порождает
   один дочерний процесс, который завершается сам.

7. **iCloud Reminders недоступны через CalDAV (фича убрана).**
   После апгрейда iCloud Reminders («upgraded reminders», списки с ⚠️ в имени)
   Apple не отдаёт задачи через CalDAV — остаются только служебные заглушки
   («Где найти мои напоминания?» и т.п.). Публичного API нет (только EventKit на
   устройстве или Shortcuts). → Напоминания из дайджеста удалены, остался только
   календарь. Если вернёшь — данные брать НЕ из CalDAV.
   Побочно: `cal.todos()` на iCloud к тому же падает с `500`, если не передать
   `include_completed=True` (сложный REPORT-фильтр сервер отвергает).

8. **Не глушить ошибки на `debug`.**
   Перехват per-calendar ошибок логировался на `log.debug` — полный отказ выборки
   напоминаний (см. п.7) был невидим в INFO-логах. → Подобные «пропускаем и идём
   дальше» логировать как минимум `warning`, иначе системный сбой выглядит как
   «данных нет».

## Проверка после изменений

- Прогнать `python -m pytest` (юнит-тесты на форматирование/экранирование).
- После деплоя проверять **оба** пути:
  - разовый прогон: `docker compose run --rm morning-digest python digest.py`
    (отправка в Telegram end-to-end);
  - daemon-режим: контейнер должен быть `Up`, а не `Restarting` — смотреть
    `docker logs morning-digest` (supercronic поднялся, расписание загружено).
  Эти два пути расходятся — зелёный one-shot не гарантирует живой daemon.
