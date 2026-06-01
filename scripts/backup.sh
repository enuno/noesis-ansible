#!/bin/bash
# backup.sh — Backup registries, configs, and state
# Usage: ./scripts/backup.sh [inventory] [--full]
#   inventory: local (default), tailscale, production
#   --full: Include runtime data and logs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY="${1:-local}"
FULL_MODE=false

for arg in "$@"; do
    case "${arg}" in
        --full) FULL_MODE=true ;;
    esac
done

INVENTORY_PATH="${REPO_ROOT}/inventory/${INVENTORY}/hosts.ini"
VAULT_PASS_FILE="${REPO_ROOT}/.vault_pass"
BACKUP_TAG="backup"

if [[ "${FULL_MODE}" == "true" ]]; then
    BACKUP_TAG="backup,full"
fi

if [[ ! -f "${INVENTORY_PATH}" ]]; then
    echo "ERROR: Inventory not found: ${INVENTORY_PATH}"
    exit 1
fi

echo "=== NoesisPraxis Backup ==="
echo "Inventory: ${INVENTORY}"
echo "Full mode: ${FULL_MODE}"
echo ""

cd "${REPO_ROOT}"
ansible-playbook -i "${INVENTORY_PATH}" playbooks/backup.yml \
    --vault-password-file "${VAULT_PASS_FILE}" \
    --tags "${BACKUP_TAG}" 2>&1 || {
    echo "ERROR: Backup failed"
    exit 1
}

echo ""
echo "=== Backup Complete ==="
