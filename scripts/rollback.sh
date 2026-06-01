#!/bin/bash
# rollback.sh — Controlled rollback to previous state
# Usage: ./scripts/rollback.sh [inventory] [phase]
#   inventory: local (default), tailscale, production
#   phase: bootstrap, foundation, security, runtime, macos, telegram, tailscale

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY="${1:-local}"
PHASE="${2:-}"

INVENTORY_PATH="${REPO_ROOT}/inventory/${INVENTORY}/hosts.ini"
VAULT_PASS_FILE="${REPO_ROOT}/.vault_pass"

if [[ ! -f "${INVENTORY_PATH}" ]]; then
    echo "ERROR: Inventory not found: ${INVENTORY_PATH}"
    exit 1
fi

if [[ -z "${PHASE}" ]]; then
    echo "ERROR: Phase required"
    echo "Usage: $0 [inventory] [phase]"
    echo "Phases: bootstrap, foundation, security, runtime, macos, telegram, tailscale"
    exit 1
fi

echo "=== NoesisPraxis Rollback ==="
echo "Inventory: ${INVENTORY}"
echo "Phase: ${PHASE}"
echo ""

# Confirm rollback
echo "WARNING: This will rollback the ${PHASE} phase."
read -p "Are you sure? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Rollback cancelled."
    exit 0
fi

cd "${REPO_ROOT}"
ansible-playbook -i "${INVENTORY_PATH}" playbooks/rollback.yml \
    --vault-password-file "${VAULT_PASS_FILE}" \
    -e "rollback_phase=${PHASE}" 2>&1 || {
    echo "ERROR: Rollback failed"
    exit 1
}

echo ""
echo "=== Rollback Complete ==="
