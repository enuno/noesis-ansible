#!/bin/bash
# validate.sh — Validate the NoesisPraxis stack health, schema, and connectivity
# Usage: ./scripts/validate.sh [inventory] [--full]
#   inventory: local (default), tailscale, production
#   --full: Run extended validation including connectivity tests

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
INVENTORY="${1:-local}"
FULL_MODE=false

# Parse args
for arg in "$@"; do
    case "${arg}" in
        --full) FULL_MODE=true ;;
    esac
done

INVENTORY_PATH="${REPO_ROOT}/inventory/${INVENTORY}/hosts.ini"
VAULT_PASS_FILE="${REPO_ROOT}/.vault_pass"

if [[ ! -f "${INVENTORY_PATH}" ]]; then
    echo "ERROR: Inventory not found: ${INVENTORY_PATH}"
    exit 1
fi

echo "=== NoesisPraxis Validation ==="
echo "Inventory: ${INVENTORY}"
echo "Full mode: ${FULL_MODE}"
echo ""

# Syntax check all playbooks
echo "Checking playbook syntax..."
cd "${REPO_ROOT}"
for playbook in playbooks/*.yml; do
    ansible-playbook -i "${INVENTORY_PATH}" "${playbook}" --syntax-check \
        --vault-password-file "${VAULT_PASS_FILE}" 2>&1 || {
        echo "ERROR: Syntax check failed for ${playbook}"
        exit 1
    }
done
echo "  All playbooks passed syntax check"

# Run validation playbook
echo ""
echo "Running validation playbook..."
VALIDATION_ARGS=""
if [[ "${FULL_MODE}" == "true" ]]; then
    VALIDATION_ARGS="--tags validate,connectivity"
fi

ansible-playbook -i "${INVENTORY_PATH}" playbooks/validate.yml \
    --vault-password-file "${VAULT_PASS_FILE}" ${VALIDATION_ARGS} 2>&1 || {
    echo "ERROR: Validation failed"
    exit 1
}

echo ""
echo "=== Validation Complete ==="
