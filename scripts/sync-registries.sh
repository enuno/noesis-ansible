#!/bin/bash
# sync-registries.sh — Cross-registry synchronization
# Usage: ./scripts/sync-registries.sh [inventory]
#   inventory: local (default), tailscale, production

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY="${1:-local}"

INVENTORY_PATH="${REPO_ROOT}/inventory/${INVENTORY}/hosts.ini"
VAULT_PASS_FILE="${REPO_ROOT}/.vault_pass"

if [[ ! -f "${INVENTORY_PATH}" ]]; then
    echo "ERROR: Inventory not found: ${INVENTORY_PATH}"
    exit 1
fi

echo "=== NoesisPraxis Registry Sync ==="
echo "Inventory: ${INVENTORY}"
echo ""

cd "${REPO_ROOT}"
ansible-playbook -i "${INVENTORY_PATH}" playbooks/master-stack.yml \
    --vault-password-file "${VAULT_PASS_FILE}" \
    --tags sync 2>&1 || {
    echo "ERROR: Registry sync failed"
    exit 1
}

echo ""
echo "=== Registry Sync Complete ==="
