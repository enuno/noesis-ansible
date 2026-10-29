# LibreChat deployment (prepared, not activated)

This repo supplies two separate, opt-in Ansible entry points. They are also
wired into `master-stack.yml` (and thus `site.yml`) as Phase 11/12, but both
orchestrator paths require their own default-off `noesispraxis_enable_librechat_*`
toggle AND the corresponding `librechat_*_live_changes` gate. Prefer the
standalone playbooks for targeted operations: `site.yml` runs other phases and
is not a LibreChat-only command. Neither path installs a Docker daemon, k3s,
or Helm; install those prerequisites by your approved host baseline first. Both
paths deploy the core LibreChat web app with MongoDB and Meilisearch. RAG,
pgvector and the admin panel are intentionally disabled/not included; their
`latest` images and database credentials in the upstream Compose example are
not suitable pins for an unattended rollout. To add those features, design a
separate scoped change with their images, storage, authentication and backups.

Source: LibreChat git tag `v0.8.8`, commit
`e8f3be08623663d4ad7f7241e693c94469b63bb0`. The official published
OCI Helm chart is `oci://ghcr.io/librechat-ai/librechat-chart/librechat`,
version `2.0.17`, appVersion `v0.8.8` (observed OCI digest
`sha256:5694dee97ecc1abcd51521a398d92249e4b740b7053eea48ce2af496674f2a69`).
The chart bundles MongoDB 16.5.45 and Meilisearch 0.11.0; its RAG and Redis
subcharts are disabled. Compose pins LibreChat `v0.8.8`, Mongo `8.0.20` and
Meilisearch `v1.35.1` by tag (tags can still move; digest pinning is a separate
hardening step). Compare these with published registries before every rollout.
Upstream references:
https://github.com/LibreChat-AI/LibreChat/blob/v0.8.8/docker-compose.yml
https://github.com/LibreChat-AI/LibreChat/blob/v0.8.8/helm/librechat/Chart.yaml
https://github.com/LibreChat-AI/LibreChat/blob/v0.8.8/helm/librechat/readme.md

## Target and secrets prerequisites

Do not assume this host or the ambient kubectl context is the deploy target.
Copy `inventory/librechat-example/hosts.ini` into an operator-controlled
inventory, replace the `.invalid` placeholders, and keep ONLY the selected
method's group populated. Check `ansible-inventory -i <inventory> --graph` and
`ansible-playbook -i <inventory> playbooks/librechat-{compose,helm}.yml
--list-hosts` before the first live task. Do not add a second alias for the
same host to one group. Root/sudo access on the selected host is required.

Generate unique persistent credentials with a trusted secret manager or
`openssl rand -hex 32` for `CREDS_KEY`, `JWT_SECRET`, `JWT_REFRESH_SECRET` and
`MEILI_MASTER_KEY`, and `openssl rand -hex 16` for `CREDS_IV`. Never regenerate
these on an upgrade. Add a provider API key separately as required by your
model configuration. Keep credentials out of git, shell arguments, Ansible
extra-vars and logs. Back up encrypted secrets and persistent volumes before
upgrading. Default MongoDB uses `--noauth` (upstream bundled contract) and
must remain on an isolated private Docker/Kubernetes network; use an externally
managed authenticated MongoDB for multi-tenant or untrusted clusters. Do not
expose the database or Meilisearch ports. Restrict cluster east-west access with
NetworkPolicy where supported. Choose a storage class with sufficient capacity
and a tested restore procedure.

Compose: pre-provision `/opt/librechat/.env` on the TARGET with owner root and
mode 0600. Its five required keys are `CREDS_KEY`, `CREDS_IV`, `JWT_SECRET`,
`JWT_REFRESH_SECRET`, and `MEILI_MASTER_KEY`. Configure `DOMAIN_CLIENT` and
`DOMAIN_SERVER` for the intended browser URL (for local-only default:
`http://localhost:3080`); a proxy must provide TLS and the matching origin.
The role never reads provider keys into Ansible output, writes an example
secret, or creates passwords. The web port binds 127.0.0.1 by default; access
it through an approved SSH tunnel or explicitly designed HTTPS proxy.
Named Docker volumes contain Mongo data, search data, uploaded files and
application data; a `docker compose down -v` DELETES them.

Helm: pre-create the namespace and TWO Secrets in it: the LibreChat Secret
`librechat-credentials-env` (or override `librechat_helm_secret`) with the five
keys above, and a distinct `librechat-meili-secret` (or override
`librechat_helm_meili_secret`) containing ONLY `MEILI_MASTER_KEY`, with the
same value as the LibreChat Secret. For example, prepare two protected dotenv
files outside the repo and, using the EXACT target kube context, run:

    kubectl --kubeconfig <target-kubeconfig> --context <target-context> create namespace librechat
    kubectl --kubeconfig <target-kubeconfig> --context <target-context> -n librechat create secret generic librechat-credentials-env --from-env-file=<secure-librechat-env-file>
    kubectl --kubeconfig <target-kubeconfig> --context <target-context> -n librechat create secret generic librechat-meili-secret --from-env-file=<secure-meili-env-file>

The two secret files must have matching MEILI_MASTER_KEY values. Their contents
must not be printed or committed. For an approved rotation, update both
Secrets and rerun the Helm play: the role hashes their current data into pod
annotations, triggering rollouts without exposing raw values.

The Secret creation commands are for first provision only; use an approved
secret-manager workflow for rotation, not an Ansible rerun to generate values.
The role checks both Secrets and matching Meilisearch keys but never generates
or changes them. The managed host must have Helm, a readable kubeconfig with the named context, and Python
`kubernetes` client in Ansible's target interpreter (`kubernetes.core` module
requirement). The controller needs `kubernetes.core` and `community.docker`
collections (see `requirements.yml`). Ensure the cluster can pull the OCI
chart and the registry images including Bitnami legacy MongoDB. `librechat.imageVolume`, the role-created uploads PVC, and MongoDB /
Meilisearch PVCs need a working default storage class (or set
`librechat_helm_storage_class`). The upload claim defaults to 10Gi and is
retained if the Helm release is removed; back it up and never prune it as a
routine cleanup. The single-replica chart uses `Recreate` on upgrades so its
ReadWriteOnce images/uploads volumes detach before replacement on multi-node
clusters (expect brief downtime). Other optional feature state (RAG, logs,
skills) is not covered by these two PVCs.

## Preview and deploy

Copy the placeholder inventory to a private operator location, replace every
`.example.invalid` host, and set the kubeconfig/context on the actual Helm
executor. The included `group_vars/all.yml` keeps both orchestrator toggles
and both live-change gates false. For an orchestrated run, target only one
role with `--tags librechat-compose` or `--tags librechat-helm` and explicitly
set the matching `noesispraxis_enable_librechat_*` toggle as well as the
matching `librechat_*_live_changes` flag. The shared bootstrap and validation
phases carry `always` tags; review their effects before using the full
orchestrator on a production inventory. A tag alone will not deploy LibreChat.

Preview offline syntax with the example inventory (no SSH or Kubernetes calls):

    ANSIBLE_CONFIG=<minimal-config-with-roles_path> ansible-playbook -i inventory/librechat-example/hosts.ini playbooks/librechat-compose.yml --syntax-check
    ANSIBLE_CONFIG=<minimal-config-with-roles_path> ansible-playbook -i inventory/librechat-example/hosts.ini playbooks/librechat-helm.yml --syntax-check

For a real deployment, replace `<inventory>`, `<kubeconfig>` and `<context>`
with approved values. The K8s kubeconfig path is on the MANAGED HOST, not
necessarily the controller. Run `--check` with the same overrides before the
live run; check mode checks inputs and configuration shapes but intentionally
skips the secret lookup, pull, Helm install and runtime health checks.

    ansible-playbook -i <inventory> playbooks/librechat-compose.yml --check
    ansible-playbook -i <inventory> playbooks/librechat-compose.yml -e librechat_compose_live_changes=true

    ansible-playbook -i <inventory> playbooks/librechat-helm.yml --check -e librechat_helm_kubeconfig=<kubeconfig> -e librechat_helm_context=<context>
    ansible-playbook -i <inventory> playbooks/librechat-helm.yml -e librechat_helm_kubeconfig=<kubeconfig> -e librechat_helm_context=<context> -e librechat_helm_live_changes=true

The Compose role verifies an HTTP 200 and `OK` from `/readyz` on the target
loopback (upstream's `/health` is liveness-only).
The Helm role waits for Helm and checks release status plus Deployment
availability. These checks do NOT prove external reachability, registration,
model-provider functionality, or backup recovery; verify each explicitly
through the intended client path after an authorized rollout. The chart is
private ClusterIP with ingress off by default. To opt in to ingress, provide
`librechat_helm_ingress` via a reviewed inventory vars file with `enabled:
true`, a real `className`, `hosts`, and a cluster-appropriate TLS arrangement.
Do not accept upstream `chat.example.com` as an actual hostname. A Tailscale
IngressClass manages TLS differently from an ordinary Ingress TLS Secret.

## Failure and rollback

Stop on a failed preflight. Inspect `docker compose -f /opt/librechat/compose.yaml
--project-directory /opt/librechat ps` and logs on the target for Compose;
`helm -n librechat history librechat`, `kubectl -n librechat get pods,pvc`,
and `kubectl -n librechat describe pod <pod>` for Kubernetes. A Helm atomic
upgrade attempts rollback on failure; verify the deployed revision and pod
readiness rather than assuming rollback worked. If rollback is needed, choose
an observed good revision and execute `helm -n librechat rollback librechat
<revision> --wait` only under an approved recovery action. Reapply the prior
Ansible variables for a future controlled upgrade. Never delete PVCs or use
`docker compose down -v` as routine cleanup. Prune old image caches and Helm
history only after checking retention and restore requirements; no pruning is
automated here. Record target, revision/tag, check output, service observation,
secret escrow location (not its value), and any residual risks in an incident
or change record. Fleet rollout: use a distinct inventory group, namespace,
release, credential set and storage per cluster; canary one cluster and verify
client/backup behavior before scaling. Do not reuse this single-node set of
unauthenticated databases across tenants.
