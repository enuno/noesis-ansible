#!/bin/bash
# install-moshi-hooks-macos.sh — Install and configure Moshi hooks on macOS
#
# This script mirrors the current Moshi hook setup pattern:
# - install the Moshi hook daemon with Homebrew
# - pair the host with Moshi using a user token
# - install managed hook config for supported agents
# - start/restart the Homebrew-managed daemon
# - verify the daemon status at the end
#
# Usage:
#   ./scripts/install-moshi-hooks-macos.sh --token <moshi-pair-token>
#   ./scripts/install-moshi-hooks-macos.sh --token <token> --formula moshi-hook
#   MOSHI_PAIR_TOKEN=<token> ./scripts/install-moshi-hooks-macos.sh
#
# Assumptions:
# - macOS host with Homebrew installed
# - Homebrew formula name is moshi-hook (override with --formula if needed)
# - the Moshi CLI supports: moshi-hook pair, install, status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

FORMULA="${MOSHI_BREW_FORMULA:-moshi-hook}"
PAIR_TOKEN="${MOSHI_PAIR_TOKEN:-}"
SKIP_PAIR=false
VERBOSE=false

usage() {
    cat <<'EOF'
Usage: install-moshi-hooks-macos.sh [options]

Options:
  --token <token>     Moshi pairing token (or set MOSHI_PAIR_TOKEN)
  --formula <name>    Homebrew formula name to install (default: moshi-hook)
  --skip-pair         Skip the pairing step and only install/configure
  -v, --verbose       Print commands as they execute
  -h, --help          Show this help text
EOF
}

log() {
    printf '%s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

run() {
    if [[ "${VERBOSE}" == "true" ]]; then
        printf '+ %s\n' "$*"
    fi
    "$@"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --token)
            [[ $# -ge 2 ]] || die "--token requires a value"
            PAIR_TOKEN="$2"
            shift 2
            ;;
        --formula)
            [[ $# -ge 2 ]] || die "--formula requires a value"
            FORMULA="$2"
            shift 2
            ;;
        --skip-pair)
            SKIP_PAIR=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
    die "This installer is intended for macOS only."
fi

require_cmd brew

log "=== Moshi Hooks Installer (macOS) ==="
log "Repo: ${REPO_ROOT}"
log "Homebrew formula: ${FORMULA}"
log ""

log "Checking Homebrew formula availability..."
if ! brew info "${FORMULA}" >/dev/null 2>&1; then
    die "Homebrew formula '${FORMULA}' was not found. Set --formula or install the correct Moshi formula first."
fi

if ! command -v moshi-hook >/dev/null 2>&1; then
    log "Installing ${FORMULA} via Homebrew..."
    run brew install "${FORMULA}"
else
    log "moshi-hook already present on PATH; ensuring the Homebrew formula is installed."
    if ! brew list --formula "${FORMULA}" >/dev/null 2>&1; then
        log "Formula is not listed as installed; installing it now."
        run brew install "${FORMULA}"
    fi
fi

require_cmd moshi-hook

if [[ "${SKIP_PAIR}" == "true" ]]; then
    log "Skipping pairing step (--skip-pair)."
else
    if [[ -z "${PAIR_TOKEN}" ]]; then
        die "Pairing token is required. Pass --token or set MOSHI_PAIR_TOKEN."
    fi
    log "Pairing this host with Moshi..."
    run moshi-hook pair --token "${PAIR_TOKEN}"
fi

log "Installing managed hook config..."
run moshi-hook install

log "Starting or restarting the Homebrew service..."
if run brew services restart "${FORMULA}"; then
    :
else
    run brew services start "${FORMULA}"
fi

log "Waiting briefly for the daemon to come up..."
sleep 2

log "Verifying daemon status..."
run moshi-hook status

log ""
log "=== Moshi hooks installed and configured successfully ==="
log "Next checks:"
log "  moshi-hook status --json"
log "  brew services list | grep '${FORMULA}'"
log ""
log "Managed hook locations should now be populated for supported agents such as Hermes, Claude Code, and Codex."
