#!/bin/sh
# Деплой morning-digest на Synology NAS по SSH.
# Синхронизирует код (без секретов) и пересобирает стек.
#
#   NAS_HOST  — ssh-alias или host (по умолчанию diskstation)
#   NAS_DIR   — каталог проекта на NAS (по умолчанию /volume2/docker/morning-digest)
#
# docker на Synology — root-only, поэтому через passwordless sudo
# (см. /etc/sudoers.d/docker-nopasswd). .env на NAS не трогаем — он исключён
# из rsync и переживает --delete.
set -eu

NAS="${NAS_HOST:-diskstation}"
DIR="${NAS_DIR:-/volume2/docker/morning-digest}"
DOCKER="sudo /usr/local/bin/docker"

echo "→ sync → ${NAS}:${DIR}"
rsync -az --delete \
  --exclude '.git' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude '.claude' --exclude '.env' \
  ./ "${NAS}:${DIR}/"

echo "→ up --build"
ssh "${NAS}" "cd '${DIR}' && ${DOCKER} compose up -d --build"

echo "→ status"
ssh "${NAS}" "cd '${DIR}' && ${DOCKER} compose ps"
