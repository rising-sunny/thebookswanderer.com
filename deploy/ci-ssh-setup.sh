#!/bin/bash
# Shared by the GitHub Actions workflows: load the deploy key and pin the host.
set -euo pipefail
: "${VPS_SSH_KEY:?VPS_SSH_KEY secret is not set}"
mkdir -p ~/.ssh
chmod 700 ~/.ssh
printf '%s\n' "$VPS_SSH_KEY" > ~/.ssh/id_ed25519
chmod 600 ~/.ssh/id_ed25519
if [ -n "${VPS_KNOWN_HOSTS:-}" ]; then
  printf '%s\n' "$VPS_KNOWN_HOSTS" > ~/.ssh/known_hosts
else
  ssh-keyscan -t ed25519 "${VPS_HOST#*@}" > ~/.ssh/known_hosts 2>/dev/null
fi
