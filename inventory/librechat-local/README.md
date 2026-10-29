# Local LibreChat k3s deployment

This inventory targets only the local `noesis-praxis` k3s cluster and is
specifically for `playbooks/librechat-helm.yml`. It does not create credentials,
provision the Tailscale operator, or select a model provider. The required
`librechat-credentials-env` and `librechat-meili-secret` Secrets were escrowed
before the initial deployment; never commit their values here.

Run from the repository root on the k3s node. The Ansible controller must run
as root because the Kubernetes action plugin reads the root-owned kubeconfig
before the play's `become` takes effect. The inventory's live-change gate is
false until explicitly overridden for an authorized run:

    sudo -n env ANSIBLE_CONFIG="$PWD/inventory/librechat-local/ansible.cfg" \
      ansible-playbook -i inventory/librechat-local/hosts.ini \
      playbooks/librechat-helm.yml --check

    sudo -n env ANSIBLE_CONFIG="$PWD/inventory/librechat-local/ansible.cfg" \
      ansible-playbook -i inventory/librechat-local/hosts.ini \
      playbooks/librechat-helm.yml -e librechat_helm_live_changes=true

`--check` validates inputs but intentionally skips Secret lookup, Helm changes
and runtime health. The site inventory sets `ALLOW_REGISTRATION: 'true'` and
publishes the application only through the Tailscale Ingress. Its `tls.hosts`
must match the Ingress rule's short `host` even though the operator manages the
TLS certificate; otherwise the operator rejects the backend. The trailing
dots in the MongoDB/Meilisearch cluster DNS names are intentional: they avoid
the observed Node.js lookup failure caused by this cluster's DNS search path.

After a live run, check the Helm release and Deployment, then request
`https://librechat.tailf99a0.ts.net/readyz` and `/api/config` from a tailnet
client. `/api/config` should report `registrationEnabled: true`. A new
operator-created proxy may need Tailnet Lock signing before the hostname is
reachable; verify its exact name and node key before signing. Registration
allows people permitted by the tailnet policy to create accounts. The optional
cluster-to-tailnet egress target list remains empty until a specific model
endpoint is selected and its provider configuration is supplied.
