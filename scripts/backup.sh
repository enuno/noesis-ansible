#!/bin/bash
set -e
echo "Running NoesisPraxis backup..."
ansible-playbook -i inventory/local/hosts.ini playbooks/backup.yml
