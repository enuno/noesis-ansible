#!/bin/bash
set -e
echo "Bootstrapping NoesisPraxis Ansible..."
ansible-playbook -i inventory/local/hosts.ini playbooks/bootstrap.yml
