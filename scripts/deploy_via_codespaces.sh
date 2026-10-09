#!/usr/bin/env bash
# Run from a Sushef GitHub Codespace on fix/chef-warmth-direct-answers-formatting-20261010.
# Tests run in Codespaces; deployment goes over SSH to 155.212.162.47.
# NO GitHub Actions and no interaction with ServGo / AI Growth OS.
set -Eeuo pipefail
umask 077

say() { printf '[Sushef Codespaces] %s\n' "$*"; }
die() { printf '[Sushef Codespaces ERROR] %s\n' "$*" >&2; exit 1; }
command -v git >/dev/null || die "Git is missing."
command -v python3 >/dev/null || die "Python 3 is missing."
command -v ssh >/dev/null || die "SSH client is missing."
command -v scp >/dev/null || die "SCP client is missing."

project="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Run inside grunvald91/Sushef."
cd "$project"
[ "$(basename "$project")" = Sushef ] || die "Open the grunvald91/Sushef Codespace (not Ai_growth_os)."
branch="$(git symbolic-ref -q --short HEAD)" || die "Checkout a branch rather than a detached HEAD."
[ "$branch" = "fix/chef-warmth-direct-answers-formatting-20261010" ] || die "Switch to fix/chef-warmth-direct-answers-formatting-20261010 before deployment."
[ -z "$(git status --porcelain)" ] || die "Commit/stash your local changes before deploying the exact committed SHA."
sha="$(git rev-parse HEAD)"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "Invalid commit SHA"
[ -f scripts/remote_sushef_apply.sh ] || die "Missing remote rollout script."
# Parse both scripts before any SSH or server side effects.
bash -n scripts/deploy_via_codespaces.sh scripts/remote_sushef_apply.sh || die "Invalid Bash syntax."

host="${SUSHEF_SERVER_HOST:-155.212.162.47}"
user="${SUSHEF_SERVER_USER:-root}"
port="${SUSHEF_SERVER_PORT:-22}"
[[ "$host" =~ ^[A-Za-z0-9.:-]+$ ]] || die "Invalid server hostname."
[[ "$user" =~ ^[a-z_][a-z0-9_-]*$ ]] || die "Invalid server username."
[[ "$port" =~ ^[0-9]+$ ]] || die "Invalid SSH port."

say "Validating Python syntax and running test suite in Codespaces..."
venv="$project/.venv"
if [ ! -x "$venv/bin/python" ]; then
  python3 -m venv "$venv" || die "Python venv could not be created."
fi
"$venv/bin/python" -m pip install --disable-pip-version-check -q -r requirements-dev.txt
PYTHONPATH="$project/src" "$venv/bin/python" -m compileall -q src tests migrations
PYTHONPATH="$project/src" "$venv/bin/python" -m pytest -q
PYTHONPATH="$project/src" "$venv/bin/python" scripts/audit_professional_cards.py
say "Unit tests passed; no GitHub Actions minutes used."

tmp="$(mktemp -d)"
chmod 700 "$tmp"
trap 'rm -rf "$tmp"' EXIT
key_arg=()
if [ -n "${SERVER_SSH_KEY:-}" ]; then
  printf '%s\n' "$SERVER_SSH_KEY" > "$tmp/server_id"
  chmod 600 "$tmp/server_id"
  key_arg=(-i "$tmp/server_id")
else
  say "SERVER_SSH_KEY absent: trying SSH agent / preconfigured Codespaces identity."
fi

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
# accept-new is TOFU; previously-pinned host key changes will be rejected.
ssh_opts=(-p "$port" -o BatchMode=yes -o ConnectTimeout=12
          -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$HOME/.ssh/known_hosts")
scp_opts=(-P "$port" -o BatchMode=yes -o ConnectTimeout=12
          -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$HOME/.ssh/known_hosts")
if [ "${#key_arg[@]}" -gt 0 ]; then
  ssh_opts+=("${key_arg[@]}")
  scp_opts+=("${key_arg[@]}")
fi

remote="$user@$host"
say "Checking SSH to $user@$host (no secrets printed)..."
ssh "${ssh_opts[@]}" "$remote" 'test "$(id -u)" -eq 0 && docker compose version >/dev/null' ||
  die "Server SSH/Docker unavailable. Check Codespaces secret SERVER_SSH_KEY and authorized_keys."

say "Checking the isolated Sushef directory on the server..."
ssh "${ssh_opts[@]}" "$remote" \
  'set -eu;
   if [ -d /opt/sushef ] && [ ! -d /opt/sushef/releases ]; then
     if [ -n "$(find /opt/sushef -mindepth 1 -maxdepth 1 -print -quit)" ]; then
       echo "Non-Sushef data already exists under /opt/sushef" >&2; exit 1;
     fi
   fi
   test ! -e /opt/sushef/current || test -L /opt/sushef/current;
   install -d -m 700 /opt/sushef /opt/sushef/releases /opt/sushef/shared /opt/sushef/backups' ||
  die "/opt/sushef conflicts with an existing non-Sushef installation."

# Bootstrap secrets ONLY on first deployment. If the server already has a
# private .env, do not rewrite keys, password, or working configuration.
if ssh "${ssh_opts[@]}" "$remote" 'test -s /opt/sushef/shared/.env'; then
  say "Using the existing private /opt/sushef/shared/.env without overwriting it."
else
  [ -n "${TELEGRAM_BOT_TOKEN:-}" ] ||
    die "Set Codespaces secret TELEGRAM_BOT_TOKEN for the Sushef repository."
  [ -n "${CLAUDEHUB_API_KEY:-}" ] ||
    die "Set Codespaces secret CLAUDEHUB_API_KEY for the Sushef repository."
  # Print no keys. Values are validated and written to a temporary 0600 file.
  "$venv/bin/python" - "$tmp/prod.env" <<'PY'
import os
import re
import secrets
import sys
from pathlib import Path

token = os.environ["TELEGRAM_BOT_TOKEN"].strip()
key = os.environ["CLAUDEHUB_API_KEY"].strip()
model = os.environ.get("CLAUDEHUB_MODEL", "claude-opus-4-7").strip()
url = os.environ.get("CLAUDEHUB_BASE_URL", "https://api.claudehub.fun").strip()
password = os.environ.get("POSTGRES_PASSWORD", "").strip() or (
    secrets.token_hex(28)
)
for name, value in (("TELEGRAM_BOT_TOKEN", token),
                    ("CLAUDEHUB_API_KEY", key),
                    ("CLAUDEHUB_MODEL", model),
                    ("CLAUDEHUB_BASE_URL", url),
                    ("POSTGRES_PASSWORD", password)):
    if not value or any(ch in value for ch in "\r\n\x00") or value.endswith("\\"):
        raise SystemExit(f"Unsafe/empty secret value for {name}; refusing deploy")
if not re.fullmatch(r"[A-Za-z0-9_-]+", password):
    raise SystemExit("POSTGRES_PASSWORD must contain only A-Z, a-z, 0-9, _ or -")
if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]+", token):
    raise SystemExit("Telegram BotFather token format is unexpected")
if not url.startswith("https://"):
    raise SystemExit("ClaudeHub base URL must use HTTPS")
out = Path(sys.argv[1])
out.write_text(
    "\n".join((
        "TELEGRAM_BOT_TOKEN=" + token,
        "CLAUDEHUB_API_KEY=" + key,
        "CLAUDEHUB_BASE_URL=" + url,
        "CLAUDEHUB_MODEL=" + model,
        "POSTGRES_PASSWORD=" + password,
        "VISION_ENABLED=false",
        "",
    )), encoding="utf-8"
)
out.chmod(0o600)
print("Private server environment prepared without revealing credentials.")
PY
  scp "${scp_opts[@]}" "$tmp/prod.env" \
      "$remote:/opt/sushef/shared/.env.incoming-$sha"
  ssh "${ssh_opts[@]}" "$remote" \
      "set -eu; umask 077; test ! -e /opt/sushef/shared/.env; mv /opt/sushef/shared/.env.incoming-$sha /opt/sushef/shared/.env; chmod 600 /opt/sushef/shared/.env" ||
      die "Could not securely install server environment."
fi

# Archive the committed branch, not the Codespace worktree and not other repos.
say "Uploading Sushef $sha to an isolated versioned release directory..."
ssh "${ssh_opts[@]}" "$remote" "install -d -m 700 /opt/sushef/releases/$sha"
git archive --format=tar "$sha" |
  ssh "${ssh_opts[@]}" "$remote" "tar -xf - -C /opt/sushef/releases/$sha"
say "Starting guarded backup/migration/deployment on the server..."
ssh "${ssh_opts[@]}" "$remote" \
   "bash /opt/sushef/releases/$sha/scripts/remote_sushef_apply.sh $sha"
say "Deployment script completed. Validate /start, recipe and /timers in Telegram."
say "Check a real 1-minute timer and ClaudeHub answer before declaring production ready."
