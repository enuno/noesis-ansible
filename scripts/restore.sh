#!/bin/bash
# restore.sh — Restore registries, configs, and state from backup
# Usage: ./scripts/restore.sh [inventory] [backup-timestamp]
#   inventory: local (default), tailscale, production
#   backup-timestamp: Specific backup to restore (default: latest)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY="${1:-local}"
BACKUP_TIMESTAMP="${2:-latest}"

INVENTORY_PATH="${REPO_ROOT}/inventory/${INVENTORY}/hosts.ini"
VAULT_PASS_FILE="${REPO_ROOT}/.vault_pass"

if [[ ! -f "${INVENTORY_PATH}" ]]; then
    echo "ERROR: Inventory not found: ${INVENTORY_PATH}"
    exit 1
fi

echo "=== NoesisPraxis Restore ==="
echo "Inventory: ${INVENTORY}"
echo "Backup: ${BACKUP_TIMESTAMP}"
echo ""

# Confirm restore
echo "WARNING: This will overwrite current state with backup data."
read -p "Are you sure? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Restore cancelled."
    exit 0
fi

cd "${REPO_ROOT}"
ansible-playbook -i "${INVENTORY_PATH}" playbooks/restore.yml \
    --vault-password-file "${VAULT_PASS_FILE}" \
    -e "restore_timestamp=${BACKUP_TIMESTAMP}" 2>&1 || {
    echo "ERROR: Restore failed"
    exit 1
}

echo ""
echo "=== Restore Complete ==="
