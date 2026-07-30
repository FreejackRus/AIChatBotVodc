#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_ENCRYPTION_PASSWORD:?BACKUP_ENCRYPTION_PASSWORD is required}"
: "${BACKUP_DIRECTORY:?BACKUP_DIRECTORY is required}"

retention_days="${BACKUP_RETENTION_DAYS:-14}"
umask 077
mkdir -p "${BACKUP_DIRECTORY}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_DIRECTORY}/vodc-${timestamp}.dump.gz.enc"

pg_dump --format=custom "${DATABASE_URL}" \
    | gzip \
    | openssl enc -aes-256-cbc -pbkdf2 -salt \
        -pass env:BACKUP_ENCRYPTION_PASSWORD \
        -out "${target}"

find "${BACKUP_DIRECTORY}" -maxdepth 1 -type f \
    -name 'vodc-*.dump.gz.enc' -mtime "+${retention_days}" -delete

echo "Encrypted backup created: ${target}"
