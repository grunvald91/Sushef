#!/usr/bin/env bash
# Run on 155.212.162.47 over SSH, invoked by deploy_via_codespaces.sh.
# Only touches the dedicated sushef Compose project and /opt/sushef.
set -Eeuo pipefail
umask 077

release_sha="${1:-}"
[[ "$release_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid release SHA" >&2; exit 2; }

root=/opt/sushef
release="$root/releases/$release_sha"
shared="$root/shared"
backups="$root/backups"
current="$root/current"
compose_file="$release/compose.yaml"
env_file="$shared/.env"
old_release=""
had_running_bot=0

fail() { printf '[Sushef deploy] %s\n' "$*" >&2; exit 1; }
info() { printf '[Sushef deploy] %s\n' "$*"; }
[ "$(id -u)" -eq 0 ] || fail "Run with the dedicated approved SSH identity (currently root)."
[ -f "$compose_file" ] || fail "Release directory not staged."
[ -s "$env_file" ] || fail "Secrets file is missing/empty on the server."
command -v docker >/dev/null || fail "Docker is not installed."
docker compose version >/dev/null || fail "Docker Compose V2 is required."

if [ -L "$current" ]; then
  old_release="$(readlink -f "$current")"
  case "$old_release" in "$root/releases/"*) ;; *) fail "Unexpected current symlink; refusing to modify.";; esac
  [ -f "$old_release/compose.yaml" ] || fail "Previous release compose.yaml missing."
elif [ -e "$current" ]; then
  fail "Existing current path isn't our release symlink; refusing to overwrite it."
fi

# Existing .env is preserved. A release only points to the private shared file.
ln -s "$env_file" "$release/.env"
chmod 700 "$root" "$root/releases" "$shared" "$backups"
chmod 600 "$env_file"

dc() {
  docker compose --project-name sushef --env-file "$env_file" -f "$compose_file" "$@"
}
old_dc() {
  docker compose --project-name sushef --env-file "$env_file" -f "$old_release/compose.yaml" "$@"
}

# Important: never run the migration on an existing PostgreSQL volume without
# a successful pre-deployment pg_dump of that very DB.
if docker volume inspect sushef_pgdata >/dev/null 2>&1; then
  [ -n "$old_release" ] || fail "Existing sushef_pgdata volume without current release; manual recovery required."
  [ -n "$(old_dc ps --status running -q postgres)" ] || fail "PostgreSQL volume exists but database isn't running; cannot back up safely."
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  archive="$backups/sushef-$stamp-$release_sha.dump"
  part="$archive.partial"
  trap 'rm -f "$part"' EXIT
  info "Backing up the existing Sushef database..."
  old_dc exec -T postgres pg_dump -U sushef -d sushef -Fc --no-owner --no-acl > "$part"
  test -s "$part" || fail "Database backup is empty."
  old_dc exec -T postgres pg_restore --list < "$part" >/dev/null || fail "Backup archive failed structural check."
  mv -n "$part" "$archive"
  trap - EXIT
  info "Backup stored in protected directory."
else
  [ -z "$old_release" ] || fail "A previous release exists without expected postgres volume; investigate before proceeding."
  info "No existing Sushef PostgreSQL volume: first installation."
fi

# Build before switching code: no interruption on failure.
info "Building only Sushef bot container..."
dc build bot

info "Starting Sushef PostgreSQL and bot with pinned Compose project..."
dc up -d --no-build

# Verify the new bot doesn't instantly exit or restart.
# The check is Docker-level, not a live ClaudeHub API check.
for attempt in $(seq 1 12); do
  cid="$(dc ps -q bot)"
  if [ -n "$cid" ]; then
    running="$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || true)"
    restarting="$(docker inspect -f '{{.State.Restarting}}' "$cid" 2>/dev/null || true)"
    if [ "$running" = "true" ] && [ "$restarting" = "false" ]; then
      sleep 3
      continue
    fi
  fi
  info "Bot isn't running steadily. Recent Sushef logs (secrets should remain hidden):"
  dc logs --tail=25 bot | sed -E 's/(bot[0-9]+:)[A-Za-z0-9_-]+/\1[REDACTED]/g' || true
  if [ -n "$old_release" ] && [ -f "$old_release/compose.yaml" ]; then
    info "Attempting code-only recovery from previous release (no DB downgrade)."
    old_dc up -d --build bot || true
  else
    dc stop bot || true
  fi
  fail "Container check failed. Database retained; manual inspection needed."
done

ln -sfn "$release" "$current"
printf '%s\n' "$release_sha" > "$root/DEPLOYED_SHA"
chmod 600 "$root/DEPLOYED_SHA"
info "Deployed revision $release_sha to dedicated /opt/sushef."
info "Container check passed; verify /start, /timers and ClaudeHub responses in Telegram."
info "No other Docker project was modified. GitHub Actions not used."
