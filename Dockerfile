FROM python:3.12-slim

# TARGETARCH автоматически выставляется BuildKit (amd64 / arm64 — покрывает
# Intel и ARM модели Synology). SUPERCRONIC_VERSION пиним для воспроизводимости.
ARG TARGETARCH=amd64
ARG SUPERCRONIC_VERSION=v0.2.33

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Berlin

# tzdata — чтобы cron корректно считал локальное время; supercronic — планировщик.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl ca-certificates \
    && curl -fsSLo /usr/local/bin/supercronic \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY digest.py entrypoint.sh ./
# COPY сохраняет режим из контекста сборки (у автора файлы 600) — выставляем
# права явно, иначе non-root пользователь не сможет прочитать digest.py.
RUN chmod 0644 digest.py && chmod 0755 entrypoint.sh

# Непривилегированный пользователь
RUN useradd --create-home --uid 1000 app
USER app

ENV HEARTBEAT_FILE=/tmp/last_success \
    CRON_SCHEDULE="0 8 * * *"

# Нездоров, если успешной отправки не было > 25 часов (суточный цикл + запас).
HEALTHCHECK --interval=1h --timeout=10s --start-period=2m --retries=2 \
    CMD python -c "import os,time,sys; f=os.environ['HEARTBEAT_FILE']; sys.exit(0 if os.path.exists(f) and time.time()-os.path.getmtime(f) < 25*3600 else 1)"

ENTRYPOINT ["./entrypoint.sh"]
