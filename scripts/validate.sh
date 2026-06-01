#!/bin/bash
set -e
echo "Validating NoesisPraxis stack..."
ansible-playbook -i inventory/local/hosts.ini playbooks/validate.yml
