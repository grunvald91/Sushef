#!/usr/bin/env bash
# Codespaces -> dedicated Sushef only. No GitHub Actions.
set -Eeuo pipefail
umask 077
release_sha="$1"
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]] || exit 2
root=/opt/sushef
release="$root/releases/$release_sha"
env_file="$root/shared/.env"
current="$root/current"
old_release=""
paused=0
migrating=0
rollback_ready=0
probe=""
work=""
rollback_db=""
say() { printf '[Sushef deploy] %s\n' "$*"; }
fail() { say "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "Approved server identity required"
[ -f "$release/compose.yaml" ] || fail "Release missing"
[ -f "$release/scripts/verify_postgres_snapshot.py" ] || fail "Manifest verifier missing"
[ -s "$env_file" ] || fail "Private server environment missing"
docker compose version >/dev/null
[ -L "$current" ] || fail "Existing production release required for backup/recovery rehearsal"
old_release="$(readlink -f "$current")"
case "$old_release" in "$root/releases/"*) ;; *) fail "Unexpected production path";; esac
[ -f "$old_release/compose.yaml" ] || fail "Old compose missing"
docker volume inspect sushef_pgdata >/dev/null
ln -sfn "$env_file" "$release/.env"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
db_stamp="$(date -u +%Y%m%dt%H%M%Sz)"
work="$root/backups/verify-$stamp-$release_sha"
install -d -m 700 "$work"
new_image="sushef-release:$release_sha"
override="$work/new-image.yaml"
printf 'services:\n  bot:\n    image: %s\n' "$new_image" > "$override"
dc() { docker compose --project-name sushef --env-file "$env_file" -f "$release/compose.yaml" -f "$override" "$@"; }
old_dc() { docker compose --project-name sushef --env-file "$env_file" -f "$old_release/compose.yaml" "$@"; }
pgcid="$(old_dc ps --status running -q postgres)"
oldcid="$(old_dc ps --status running -q bot)"
[ -n "$pgcid" ] && [ -n "$oldcid" ] || fail "Existing PostgreSQL and bot must be running"
old_image="$(docker inspect -f '{{.Image}}' "$oldcid")"
old_override="$work/old-image.yaml"
printf 'services:\n  bot:\n    image: %s\n' "$old_image" > "$old_override"
recover_code() {
  docker compose --project-name sushef --env-file "$env_file" \
    -f "$old_release/compose.yaml" -f "$old_override" \
    up -d --no-build --no-deps bot
}
cleanup() {
  # Only this disposable, isolated rehearsal container, never production volumes.
  if [ -n "$probe" ]; then docker rm -f "$probe" >/dev/null 2>&1 || true; fi
}
recover() {
  set +e
  say "Deployment failed; recovering only Sushef."
  dc stop bot >/dev/null 2>&1
  if [ "$migrating" -eq 1 ]; then
    if [ "$rollback_ready" -ne 1 ]; then
      say "No validated rollback DB. Bot remains stopped; backup and DB retained."
      return 1
    fi
    failed_db="sushef_failed_$db_stamp"
    # Keep the failed database intact. Never DROP production or restore over it.
    if ! old_dc exec -T postgres psql -v ON_ERROR_STOP=1 -U sushef -d postgres \
      -c "ALTER DATABASE sushef RENAME TO $failed_db"; then
      say "Cannot isolate migrated DB; bot remains stopped. Manual recovery required."
      return 1
    fi
    if ! old_dc exec -T postgres psql -v ON_ERROR_STOP=1 -U sushef -d postgres \
      -c "ALTER DATABASE $rollback_db RENAME TO sushef"; then
      say "Validated recovery DB and original DB retained; manual rename required."
      return 1
    fi
    say "Validated pre-deploy database restored; failed DB retained as $failed_db"
  fi
  if recover_code; then
    say "Previous pinned bot image restarted."
  else
    say "Previous image restart failed; data and backups retained."
    return 1
  fi
}
on_error() {
  rc=$?
  trap - ERR
  if [ "$paused" -eq 1 ]; then recover || true; fi
  exit "$rc"
}
trap on_error ERR
trap cleanup EXIT
dump_db() {
  destination="$1"
  old_dc exec -T postgres pg_dump -U sushef -d sushef -Fc --no-owner --no-acl > "$destination.partial"
  test -s "$destination.partial"
  old_dc exec -T postgres pg_restore --list < "$destination.partial" >/dev/null
  mv "$destination.partial" "$destination"
  chmod 600 "$destination"
  say "BACKUP_OK $destination"
  sha256sum "$destination"
}
initial="$work/preflight.dump"
say "Creating and structurally checking PostgreSQL backup before any migration."
dump_db "$initial"
say "Building pinned release image while the production bot remains available."
dc build bot
pg_image="$(docker inspect -f '{{.Image}}' "$pgcid")"
short_sha="$(printf '%s' "$release_sha" | cut -c1-12)"
probe="sushef-rehearsal-$short_sha-$stamp"
say "Restoring into isolated PostgreSQL (no published ports, no production volume)."
docker run -d --name "$probe" --network none --memory 256m \
  -e POSTGRES_USER=sushef -e POSTGRES_DB=sushef \
  -e POSTGRES_HOST_AUTH_METHOD=trust "$pg_image" >/dev/null
ready=0
for attempt in $(seq 1 30); do
  if docker exec "$probe" pg_isready -U sushef -d sushef >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ "$ready" -eq 1 ] || { false; }
docker exec -i "$probe" pg_restore --exit-on-error --no-owner --no-acl -U sushef -d sushef < "$initial"
probe_verify() {
  docker run --rm --user 0 --network "container:$probe" \
    -e DATABASE_URL=postgresql+asyncpg://sushef@127.0.0.1:5432/sushef \
    -v "$release/scripts/verify_postgres_snapshot.py:/verify.py:ro" \
    -v "$work:/evidence" "$new_image" python /verify.py "$@"
}
probe_migrate() {
  docker run --rm --network "container:$probe" \
    -e DATABASE_URL="postgresql+asyncpg://sushef@127.0.0.1:5432/$1" \
    "$new_image" sh -c 'alembic upgrade head && alembic upgrade head'
}
probe_verify snapshot /evidence/preflight.json
say "Rehearsing migration and repeated upgrade on restored copy."
probe_migrate sushef
probe_verify migrated /evidence/preflight.json
docker exec "$probe" createdb -U sushef sushef_restore
docker exec -i "$probe" pg_restore --exit-on-error --no-owner --no-acl \
  -U sushef -d sushef_restore < "$initial"
probe_verify restored /evidence/preflight.json sushef_restore
say "RESTORE_AND_MIGRATION_REHEARSAL_OK"
# Writers remain paused from the final backup through deployment or recovery.
say "Pausing only Sushef bot for final consistent backup and deployment."
paused=1
old_dc stop bot
final="$work/final.dump"
dump_db "$final"
prod_verify() {
  dc run --rm --no-deps -T --user 0 \
    -v "$release/scripts/verify_postgres_snapshot.py:/verify.py:ro" \
    -v "$work:/evidence" bot python /verify.py "$@"
}
prod_verify snapshot /evidence/final.json
rollback_db="sushef_rollback_$db_stamp"
old_dc exec -T postgres createdb -U sushef "$rollback_db"
old_dc exec -T postgres pg_restore --exit-on-error --no-owner --no-acl \
  -U sushef -d "$rollback_db" < "$final"
prod_verify restored /evidence/final.json "$rollback_db"
rollback_ready=1
# Rehearse the exact final snapshot outside the production volume as well.
docker exec "$probe" createdb -U sushef sushef_final
docker exec -i "$probe" pg_restore --exit-on-error --no-owner --no-acl \
  -U sushef -d sushef_final < "$final"
probe_migrate sushef_final
probe_verify migrated /evidence/final.json sushef_final
say "FINAL_BACKUP_RESTORE_AND_MIGRATION_OK; validated rollback database ready."
migrating=1
dc run --rm --no-deps -T bot alembic upgrade head
prod_verify migrated /evidence/final.json
dc up -d --no-build --no-deps bot
for attempt in $(seq 1 12); do
  cid="$(dc ps --status running -q bot)"
  test -n "$cid"
  test "$(docker inspect -f '{{.State.Running}} {{.State.Restarting}} {{.RestartCount}}' "$cid")" = "true false 0"
  sleep 3
done
say "Checking live Telegram API and one minimal ClaudeHub response."
dc exec -T bot python -m sushef.smoke
ln -sfn "$release" "$current"
printf '%s\n' "$release_sha" > "$root/DEPLOYED_SHA"
chmod 600 "$root/DEPLOYED_SHA"
paused=0
say "DEPLOYED_OK sha=$release_sha"
say "Evidence and validated backup: $work"
say "Telegram/ClaudeHub smoke passed; only Sushef was changed."
