#!/usr/bin/env bash
# Back up Sushef PostgreSQL without GitHub Actions.
set -euo pipefail
umask 077

OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"
chmod 700 "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_DIR/sushef-$STAMP.dump"
TMP="$OUT.partial"
trap 'rm -f "$TMP"' EXIT

# Requires docker compose on the host running compose.yaml.
docker compose exec -T postgres pg_dump -U sushef -d sushef --format=custom --no-owner --no-acl > "$TMP"
test -s "$TMP"
docker compose exec -T postgres pg_restore --list < "$TMP" > /dev/null
mv "$TMP" "$OUT"
trap - EXIT
echo "PostgreSQL backup created and archive structure checked: $OUT"
echo "Important: keep off-site encrypted copies and test restoration separately."
