#!/usr/bin/env bash
# Existing production backup then full local tests; NO DEPLOY.
set -Eeuo pipefail
umask 077
die() { printf '[Sushef ERROR] %s\n' "$*" >&2; exit 1; }
say() { printf '[Sushef] %s\n' "$*"; }
for cmd in git python3 ssh; do command -v "$cmd" >/dev/null || die "Missing $cmd"; done
repo="$(git rev-parse --show-toplevel)" || die "Not a Git repository"
cd "$repo"
[ "$(basename "$repo")" = Sushef ] || die "Wrong repository"
branch="$(git symbolic-ref --short -q HEAD)" || die "Detached HEAD"
[ "$branch" = "fix/rich-dialog-real-answers-20261010" ] || die "Wrong branch"
[ -z "$(git status --porcelain)" ] || die "Uncommitted changes; refusing"
sha="$(git rev-parse HEAD)"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "Invalid SHA"
bash -n scripts/check_and_backup_codespaces.sh || die "Bash syntax error"
say "Preparing independent server-side backup before any test run or deployment."


host="${SUSHEF_SERVER_HOST:-155.212.162.47}"
port="${SUSHEF_SERVER_PORT:-22}"
user="${SUSHEF_SERVER_USER:-root}"
[[ "$host" =~ ^[A-Za-z0-9.:-]+$ ]] || die "Invalid SSH host"
[[ "$port" =~ ^[0-9]+$ ]] || die "Invalid SSH port"
[[ "$user" =~ ^[a-z_][a-z0-9_-]*$ ]] || die "Invalid SSH user"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
chmod 700 "$tmpdir"
key_args=()
if [ -n "${SERVER_SSH_KEY:-}" ]; then
  printf '%s\n' "$SERVER_SSH_KEY" > "$tmpdir/key"
  chmod 600 "$tmpdir/key"
  key_args=(-i "$tmpdir/key")
fi
say "Backing up only the existing Sushef PostgreSQL, if it is positively identified..."
ssh -p "$port" -o BatchMode=yes -o ConnectTimeout=12 \
  -o StrictHostKeyChecking=yes "${key_args[@]}" "$user@$host" bash -s -- "$sha" <<'REMOTE'
set -Eeuo pipefail
umask 077
fail() { printf '[Sushef remote ERROR] %s\n' "$*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "Approved privileged account required"
sha="$1"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid SHA"
root=/opt/sushef
[ -L "$root/current" ] || fail "Current release symlink missing"
release="$(readlink -f "$root/current")"
case "$release" in /opt/sushef/releases/*) ;; *) fail "Unexpected release path";; esac
[ -f "$release/compose.yaml" ] || fail "Missing compose file"
[ -s "$root/shared/.env" ] || fail "Existing env not found"
command -v docker >/dev/null || fail "Docker missing"
docker compose version >/dev/null || fail "Docker Compose missing"
docker volume inspect sushef_pgdata >/dev/null 2>&1 || fail "Unexpected DB volume; refusing to guess"
dc() { docker compose --project-name sushef --env-file "$root/shared/.env" -f "$release/compose.yaml" "$@"; }
[ -n "$(dc ps --status running -q postgres)" ] || fail "Postgres not running"
install -d -m 700 "$root/backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$root/backups/sushef-$stamp-$sha.dump"
tmp="$archive.partial"
[ ! -e "$archive" ] || fail "Backup collision"
trap 'rm -f "$tmp"' EXIT
dc exec -T postgres pg_dump -U sushef -d sushef -Fc --no-owner --no-acl > "$tmp" || fail "pg_dump failed"
[ -s "$tmp" ] || fail "Empty backup"
dc exec -T postgres pg_restore --list < "$tmp" >/dev/null || fail "Invalid dump structure"
mv "$tmp" "$archive"
chmod 600 "$archive"
trap - EXIT
printf 'BACKUP_OK path=%s\n' "$archive"
sha256sum "$archive"
stat -c 'bytes=%s' "$archive"
echo 'verified=archive_readable; full_restore_test=NOT_RUN'
echo 'production_deploy=NOT_PERFORMED; migrations=NOT_PERFORMED'
REMOTE

say "Running local tests without GitHub Actions..."
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements-dev.txt
PYTHONPATH=src .venv/bin/python -m compileall -q src tests migrations
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python scripts/audit_professional_cards.py
say "Full test suite passed. Production bot and schema were not changed."

