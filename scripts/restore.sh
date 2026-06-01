#!/bin/bash
set -e
echo "Running NoesisPraxis restore..."
ansible-playbook -i inventory/local/hosts.ini playbooks/restore.yml
