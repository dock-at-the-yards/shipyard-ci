#!/usr/bin/env bash
# Ephemeral self-hosted runner loop.
# Registers a runner with --ephemeral (runs one job then exits), then repeats.
# Requires: REPO (owner/repo), TOKEN (PAT with repo scope), RUNNER_DIR.

set -euo pipefail

REPO="${REPO:?set REPO=owner/repo}"
TOKEN="${TOKEN:?set TOKEN=github PAT}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
LABELS="${LABELS:-self-hosted,ephemeral}"

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ARCH="x64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  armv7l) ARCH="arm" ;;
esac
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
RUNNER_VER="2.317.0"
TARBALL="actions-runner-${OS}-${ARCH}-${RUNNER_VER}.tar.gz"
URL="https://github.com/actions/runner/releases/download/v${RUNNER_VER}/${TARBALL}"

if [ ! -f ./config.sh ]; then
  curl -sL "$URL" -o "$TARBALL"
  tar xzf "$TARBALL"
fi

while true; do
  REG_TOKEN="$(curl -sX POST -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/${REPO}/actions/runners/registration-token" | \
    python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')"

  ./config.sh --url "https://github.com/${REPO}" \
    --token "$REG_TOKEN" \
    --name "ephemeral-$(hostname)-$$" \
    --labels "$LABELS" \
    --ephemeral \
    --unattended \
    --replace

  ./run.sh
  # runner exits after one job; loop registers again
done
