#!/bin/bash
# bootstrap.sh — Bootstrap the NoesisPraxis control node and fetch secrets
# Usage: ./scripts/bootstrap.sh [inventory]
#   inventory: local (default), tailscale, production

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY="${1:-local}"
INVENTORY_PATH="${REPO_ROOT}/inventory/${INVENTORY}/hosts.ini"

if [[ ! -f "${INVENTORY_PATH}" ]]; then
    echo "ERROR: Inventory not found: ${INVENTORY_PATH}"
    echo "Usage: $0 [local|tailscale|production]"
    exit 1
fi

echo "=== NoesisPraxis Bootstrap ==="
echo "Inventory: ${INVENTORY}"
echo "Path: ${INVENTORY_PATH}"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
command -v ansible-playbook >/dev/null 2>&1 || { echo "ERROR: ansible-playbook not found"; exit 1; }
command -v bws >/dev/null 2>&1 || { echo "WARNING: bws (Bitwarden Secrets CLI) not found — secrets bootstrap will be skipped"; }

# Check vault password file
VAULT_PASS_FILE="${REPO_ROOT}/.vault_pass"
if [[ ! -f "${VAULT_PASS_FILE}" ]]; then
    echo "WARNING: Vault password file not found at ${VAULT_PASS_FILE}"
    echo "Create it with: echo 'your-password' > ${VAULT_PASS_FILE} && chmod 600 ${VAULT_PASS_FILE}"
fi

# Run bootstrap playbook
echo ""
echo "Running bootstrap playbook..."
cd "${REPO_ROOT}"
ansible-playbook -i "${INVENTORY_PATH}" playbooks/bootstrap.yml \
    --vault-password-file "${VAULT_PASS_FILE}" 2>&1 || {
    echo "ERROR: Bootstrap failed"
    exit 1
}

echo ""
echo "=== Bootstrap Complete ==="
echo "Next steps:"
echo "  Deploy full stack:  ansible-playbook -i ${INVENTORY_PATH} playbooks/site.yml"
echo "  Deploy by phase:    ansible-playbook -i ${INVENTORY_PATH} playbooks/master-stack.yml --tags foundation"
echo "  Validate health:    ansible-playbook -i ${INVENTORY_PATH} playbooks/validate.yml"
