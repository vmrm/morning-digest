#!/bin/sh
set -eu

# Рендерим crontab из переменной окружения и запускаем supercronic.
# CRON_SCHEDULE — стандартное cron-выражение (по умолчанию каждый день в 08:00).
# Время интерпретируется в локальной зоне контейнера (TZ).

CRONTAB=/tmp/crontab
echo "${CRON_SCHEDULE} cd /app && python digest.py" > "$CRONTAB"

# Baseline для HEALTHCHECK: до первого срабатывания считаем контейнер живым.
date -u +%Y-%m-%dT%H:%M:%SZ > "${HEARTBEAT_FILE}" 2>/dev/null || true

echo "morning-digest: schedule='${CRON_SCHEDULE}' TZ='${TZ:-?}'"
exec supercronic "$CRONTAB"
