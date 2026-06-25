#!/bin/sh
set -eu

# Разовый запуск с аргументами (docker compose run ... <cmd>) — выполняем их
# и не поднимаем планировщик. Удобно для теста: `... run --rm md python digest.py`.
if [ "$#" -gt 0 ]; then
  exec "$@"
fi

# Рендерим crontab и запускаем supercronic.
# supercronic выполняет команду без шелла, поэтому никаких `cd`/`&&` —
# только абсолютный бинарь и скрипт. Время — в локальной зоне (TZ).
CRONTAB=/tmp/crontab
echo "${CRON_SCHEDULE} /usr/local/bin/python /app/digest.py" > "$CRONTAB"

# Baseline для HEALTHCHECK: до первого срабатывания считаем контейнер живым.
date -u +%Y-%m-%dT%H:%M:%SZ > "${HEARTBEAT_FILE}" 2>/dev/null || true

echo "morning-digest: schedule='${CRON_SCHEDULE}' TZ='${TZ:-?}'"
# -no-reap: на ядре Synology pid1-reaper supercronic фаталит ("Failed to fork
# exec") ещё до чтения crontab. Reaper не нужен — задача порождает один дочерний
# процесс в сутки, который завершается сам.
exec supercronic -no-reap "$CRONTAB"
