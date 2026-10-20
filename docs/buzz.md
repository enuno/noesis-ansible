# Buzz on an existing k3s cluster

Thin Ansible wrapper around the official Block Buzz Helm chart. It does not
install k3s, does not copy kubeconfig, and does not modify Tailscale roles.

This document is an operator guide. It is not evidence that a cluster was
contacted. Offline syntax checks are not runtime proof.

## Provenance

| Field | Value |
| --- | --- |
| Repository | https://github.com/block/buzz |
| Chart path | `deploy/charts/buzz` |
| Git revision | `30ca980b49a7479dd89cb1ced0871af05ff1e12e` |
| Chart version | `0.1.11` |
| App version | `0.1.0` |
| Chart.lock digest | `sha256:9c0df32008f782064104ecec8552f348841f120852d49ace66966a56ba904348` |
| Vendored tree | `charts/buzz/0.1.11/` |
| Provenance file | `charts/buzz/0.1.11/PROVENANCE.md` |

Distribution mechanism: unpacked chart directory copied to the managed host.
The role does not pull `oci://ghcr.io/block/buzz/charts/buzz` at apply time.
That OCI tag `0.1.11` was observed in the research artifact. This tree is git
`30ca980b49a7479dd89cb1ced0871af05ff1e12e`, not the `chart-v0.1.11` commit
`5a93e862ee28b8804f681ae15997a00bdc45d1bf`. It is not claimed byte-identical
to the published OCI layer.

Dependencies were taken from `Chart.lock` without changing versions:

| Name | Locked version | Repository |
| --- | --- | --- |
| postgres | 0.19.5 | `oci://registry-1.docker.io/cloudpirates` |
| redis | 0.30.3 | `oci://registry-1.docker.io/cloudpirates` |

`helm dependency build` with Helm v4.3.1 exited 1 (Docker Hub 401) before it
wrote the tarballs. The same lock coordinates were fetched from the anonymous
registry API and checked against the returned layer digests. `Chart.lock` was
not rewritten. `helm dependency list` then reported both dependencies `ok`.
Do not run `helm dependency update` on this tree.

## Execution model

One model only. Do not mix it with localhost delegation.

| Step | Where it runs |
| --- | --- |
| Read `charts/buzz/0.1.11` and render `values-buzz.yml.j2` | Controller, as the source side of Ansible `copy` / `template` |
| Write `/opt/buzz-chart/0.1.11` and `/opt/buzz-stage/values-buzz.yml` | Managed host in group `buzz_k3s` |
| `kubernetes.core.helm`, `helm_info`, and `k8s_info` | Managed host. Collection pin: `requirements/buzz.yml` (`kubernetes.core` 5.2.0) |
| Kubernetes API | Contacted only from that managed host, using `buzz_kubeconfig_path` and `buzz_kube_context` |

The play never copies kubeconfig to the controller, never prints it, and never
changes its mode. If a live check finds it world-readable, the role fails.

The play does not install Helm and does not include `roles/helm`. Helm must
already exist on the managed host at `buzz_helm_binary_path` (default
`/usr/local/bin/helm`). This role does not install k3s.

## Safe default

`inventory/example` selects this default. It is placeholders only
(`buzz-k3s.example.invalid`, `CHANGE_ME`). A real play rejects that host.

| Control | Default |
| --- | --- |
| Profile | `production` |
| Service | `ClusterIP` |
| Ingress | disabled |
| HTTPRoute | disabled |
| Pairing relay | disabled |
| `buzz_exposure_enabled` | `false` |
| Inline secret values | empty strings, not variables |
| Live API checks | `false` |

Non-ClusterIP, Ingress, HTTPRoute, or the pairing relay require
`buzz_exposure_enabled: true` and a chart-supported value. The chart has no
`hostNetwork`, `hostPort`, privileged, or Tailscale Funnel key. This role does
not invent those keys and does not set cert-manager issuer annotations.

Tailnet exposure is an operator follow-up. Do not expect this role to change
Tailscale Serve or Funnel. With the default, the Service is ClusterIP only.

## Variable reference

Set these in inventory group vars for `buzz_k3s`. Do not put secret values here.

| Variable | Chart key | Default | Notes |
| --- | --- | --- | --- |
| `buzz_kubeconfig_path` | module `kubeconfig` | `/etc/rancher/k3s/k3s.yaml` | Path on the managed host. Not file contents. |
| `buzz_kube_context` | module `context` | empty, required | Explicit context. `CHANGE_ME` is rejected. |
| `buzz_release_name` | Helm release name | `buzz` | DNS label. Service name follows the chart fullname helper. |
| `buzz_namespace` | `release_namespace` | `buzz` | Created by Helm `create_namespace` when the play actually runs. |
| `buzz_chart_version` | vendored `Chart.yaml` | `0.1.11` | Must stay on the pin. |
| `buzz_chart_git_revision` | provenance | `30ca980b49a7479dd89cb1ced0871af05ff1e12e` | Must stay on the pin. |
| `buzz_chart_lock_digest` | `Chart.lock` `digest` | `sha256:9c0df32008f782064104ecec8552f348841f120852d49ace66966a56ba904348` | Must stay on the pin. |
| `buzz_profile` | `quickstart`, `postgresql.enabled`, `redis.enabled`, `minio.enabled` | `production` | `quickstart` is eval-only and opt-in. |
| `buzz_relay_url` | `relayUrl` | empty, required | Chart requires it. Use `wss://`. Not an Ingress by itself. |
| `buzz_media_base_url` | `mediaBaseUrl` | empty | Omitted when empty. Chart can derive it. |
| `buzz_owner_pubkey` | `ownerPubkey` / `RELAY_OWNER_PUBKEY` | empty, required | 64 lowercase hex. Not a private key. |
| `buzz_existing_secret` | `secrets.existingSecret` | empty | Name only. Required for production. |
| `buzz_s3_endpoint` | `s3.endpoint` | empty | Required `https://` URL in production. Not a credential. |
| `buzz_s3_bucket` | `s3.bucket` | `buzz-media` | Chart default. |
| `buzz_s3_region` | `s3.region` | `us-east-1` | Chart default. Set the provider region when it differs. |
| `buzz_s3_addressing_style` | `s3.addressingStyle` | `path` | `path` or `virtual` only. |
| `buzz_replica_count` | `replicaCount` | `1` | Greater than 1 needs Redis. See below. |
| `buzz_relay_cpu_request` | `relay.resources.requests.cpu` | `500m` | Chart default. |
| `buzz_relay_memory_request` | `relay.resources.requests.memory` | `512Mi` | Chart default. |
| `buzz_relay_cpu_limit` | `relay.resources.limits.cpu` | `2` | Chart default. |
| `buzz_relay_memory_limit` | `relay.resources.limits.memory` | `2Gi` | Chart default. |
| `buzz_image_repository` | `image.repository` | `ghcr.io/block/buzz` | Chart default. |
| `buzz_image_tag` | `image.tag` | empty | Empty uses `Chart.appVersion` (`0.1.0`). Not an immutable pin — and the `0.1.0` relay (2026-06-14 build) predates the `BUZZ_AUTO_MIGRATE` startup flow the chart documents: it crash-loops on an empty schema (`relation "events" does not exist`). Do not deploy empty-tag outside quickstart. |
| `buzz_image_digest` | `image.digest` | empty | Production pin: `sha256:55574cb818f7f809e8d38b1d9ae883d2d6103a7a139f84615b9c55840b6bb956` (`ghcr.io/block/buzz` `main` rev `6e6173acd580`, verified on praxis 2026-10-20). Set only a digest you verified. `sha256:` plus 64 hex. |
| `buzz_git_persistence_enabled` | `persistence.git.enabled` | `true` | Scratch PVC. See persistence. |
| `buzz_git_persistence_size` | `persistence.git.size` | `10Gi` | Chart default. |
| `buzz_git_persistence_access_mode` | `persistence.git.accessMode` | `ReadWriteOnce` | Chart enum. |
| `buzz_git_existing_claim` | `persistence.git.existingClaim` | empty | Name only. |
| `buzz_storage_class` | `persistence.git.storageClass` | empty, required when the git PVC is created | Also passed to bundled Postgres/Redis only in quickstart. |
| `buzz_exposure_enabled` | gate, not a chart key | `false` | Required before any non-default exposure. |
| `buzz_service_type` | `service.type` | `ClusterIP` | `NodePort` or `LoadBalancer` need the exposure gate. |
| `buzz_ingress_enabled` | `ingress.enabled` | `false` | Needs the exposure gate and `buzz_ingress_class_name`. |
| `buzz_httproute_enabled` | `httproute.enabled` | `false` | Mutually exclusive with Ingress. |
| `buzz_ingress_tls_secret_name` | `ingress.tls[].secretName` | empty | Name only. Chart does not issue certificates. |
| `buzz_ingress_tls_hosts` | `ingress.tls[].hosts` | `[]` | Required if the TLS secret name is set. |
| `buzz_helm_timeout` | module `timeout` | `10m0s` | Go duration. Mutually exclusive with `wait_timeout`, which is not used. |
| `buzz_helm_wait` | module `wait` | `true` | |
| `buzz_helm_atomic` | module `atomic` | `true` | See rollback. |
| `buzz_helm_history_max` | module `history_max` | `10` | |
| `buzz_live_checks` | gate, not a chart key | `false` | API reads. Not runtime proof when false. |
| `buzz_destroy_data` | refused | `false` | The role fails if this is true. |

Not variables, on purpose: `DATABASE_URL`, `REDIS_URL`, `BUZZ_RELAY_PRIVATE_KEY`,
`BUZZ_GIT_HOOK_HMAC_SECRET`, `BUZZ_S3_ACCESS_KEY`, `BUZZ_S3_SECRET_KEY`,
`secrets.relayPrivateKey`, `secrets.gitHookHmacSecret`, `s3.accessKey`,
`s3.secretKey`, `externalPostgresql.url`, `externalRedis.url`. Those stay empty
or live only in the Secret named by `buzz_existing_secret`.

`buzz_helm_dependency_update` must stay false. The install task also hard-codes
`dependency_update: false`.

## Profiles

Production, the default, matches the chart's production tier: bundled
Postgres, Redis, and MinIO stay disabled. The chart accepts that only when
`secrets.existingSecret` is set (it treats that Secret as the Postgres and S3
credential source). Create the Secret out of band before a live deploy. Expected
keys, from `deploy/charts/buzz/examples/secret-sample.yaml` at this revision:

- `BUZZ_RELAY_PRIVATE_KEY`
- `BUZZ_GIT_HOOK_HMAC_SECRET` (required by the chart when `replicaCount > 1`)
- `DATABASE_URL`
- `READ_DATABASE_URL` (optional)
- `REDIS_URL` (required by the chart when `replicaCount > 1`; upstream also says even quickstart needs real Redis)
- `BUZZ_S3_ACCESS_KEY`
- `BUZZ_S3_SECRET_KEY`
- `BUZZ_KLIPY_API_KEY` (optional)

`s3.endpoint`, `s3.bucket`, `s3.region`, and `s3.addressingStyle` are still
rendered as non-secret env. A Secret name alone does not set the endpoint.

Quickstart sets `quickstart: true` plus `postgresql.enabled`, `redis.enabled`,
and `minio.enabled`. Upstream says this profile auto-generates relay secrets
via Helm `lookup`, is not GitOps-safe, and is single-replica evaluation only.
This role still refuses inline secret values. Do not use quickstart for a
durable relay identity.

## Persistence and what extra nodes do not do

| State | Where it lives | This chart revision |
| --- | --- | --- |
| Events, membership, repo-name uniqueness | PostgreSQL | External in production. Bundled subchart PVC only in quickstart. |
| Pub/sub and cache | Redis | External URL inside the Secret in production. Bundled subchart PVC only in quickstart. Not a durable event store. |
| Media and git objects | S3-compatible bucket | External in production. Bundled MinIO PVC only in quickstart. |
| Git working files | `persistence.git` PVC or emptyDir | Enabled by default. Chart values say no persistent git state lives here. `NOTES.txt` still lists the git PVC as a backup item. |

`persistence.git` is `ReadWriteOnce`. It binds to one node. Adding nodes does
not replicate that volume, the bundled Postgres/Redis/MinIO volumes, or
external databases. There is no chart key for shared RWX git storage in the
default, and the chart removed the old RWX requirement because git state is
object-store-backed.

Storage class:

- Git PVC: `persistence.git.storageClass`. Required when the role creates that PVC.
- Bundled Postgres and Redis, quickstart only: `persistence.storageClass` on the vendored subcharts (postgres 0.19.5, redis 0.30.3), passed through the parent alias. The parent `values.yaml` does not list that key; the subchart values do.
- Bundled MinIO: `templates/quickstart-minio.yaml` sets no `storageClassName`. The role cannot choose a class for that PVC. It uses the cluster default.

## Install

1. Confirm the managed host is the kubeconfig host, Helm is already installed at `buzz_helm_binary_path`, and `buzz_kube_context` is the context you mean. This play does not install Helm.
2. Create the namespace if you are not letting Helm create it, then create the Secret named by `buzz_existing_secret`. Do not commit the Secret.
3. Set inventory variables. Replace every placeholder. The all-zero pubkey from upstream's Argo CD example is rejected here because it is not an operator key.
4. Keep `buzz_exposure_enabled: false` unless you have a reviewed reason and the chart supports the knob.
5. Run:

```bash
ansible-playbook -i inventory/<your-inventory> playbooks/deploy_buzz.yml
```

`playbooks/deploy_buzz.yml` sets `buzz_live_checks: true`. Inventory cannot
turn that off for this play. Helm install refuses unless the unrelated-release
guard set `buzz_release_ownership_checked` in the same run. Secret and
StorageClass reads run on that same path. `--syntax-check` does not execute
them and is not runtime proof. This workspace did not execute a live deploy.

## Config change

Edit inventory variables and run the same play. `reset_values: true` and
`reuse_values: false` are set, so the rendered values file replaces prior
user values for this release. Keys this role does not render fall back to the
vendored chart defaults. The role does not rotate credentials.

## Pinned upgrade

Do not float the chart.

1. Fetch a new immutable revision of `https://github.com/block/buzz` and confirm `deploy/charts/buzz/Chart.yaml`.
2. Vendor that tree under `charts/buzz/<version>/`.
3. Resolve dependencies from that revision's `Chart.lock` without `helm dependency update`.
4. Change `buzz_chart_version`, `buzz_chart_git_revision`, `buzz_chart_lock_digest`, and the chart source path together. Update `docs/buzz.md` and `charts/buzz/<version>/PROVENANCE.md`.
5. Diff `values.schema.json`. Remove any key this role renders that the new schema rejects.
6. Re-run `playbooks/deploy_buzz.yml`.

Upstream chart README: schema migrations run at startup when
`migrate.autoMigrate` is true (this role leaves the chart default `true`).
`helm upgrade` is the chart's upgrade procedure. Migration 0032 is a hard
compatibility boundary described in that README. `helm rollback` does not undo
a SQL migration.

## Backup prerequisites

From the chart README and `NOTES.txt` at this revision. Losing any of these is
data loss. This role does not take backups.

1. `BUZZ_RELAY_PRIVATE_KEY` — relay identity. Rotating it is a new identity.
2. PostgreSQL database. In quickstart this is the bundled PVC. In production it is external.
3. S3 bucket (`buzz-media` unless you changed `buzz_s3_bucket`).
4. Git PVC (`<fullname>-git`). Upstream `NOTES.txt` lists it even though `values.yaml` calls it scratch.
5. Owner private key. Held by the operator, not by the chart. Restore by re-installing with the same `ownerPubkey`.

Take those backups before upgrade, rollback, or any manual deletion. A
ReadWriteOnce volume cannot be backed up by adding a node.

## Restore

This role does not restore data.

1. Restore PostgreSQL and the S3 bucket with the tools that own those systems.
2. Restore `BUZZ_RELAY_PRIVATE_KEY` into the same Secret name. Do not generate a new one if you need the same relay identity.
3. Re-run the deploy play with the same `buzz_owner_pubkey`, chart pin, and Secret name.
4. Upstream: "Owner private key — held by the operator, not by this chart. Restore by re-installing with the same `ownerPubkey`."

A Helm rollback does not restore database rows, bucket objects, or PVC bytes.

## Helm rollback limitations

`kubernetes.core` 5.2.0 documents `atomic` as: "If set, the installation
process deletes the installation on failure." This role sets `atomic: true`.
That module text does not promise an upgrade rollback. Helm's own `--atomic`
flag rolls a failed upgrade back to the previous revision and deletes a failed
first install. Do not treat those as the same guarantee.

Other limits:

- Rollback restores Kubernetes manifests from release history, not Postgres, Redis, S3, or PVC data.
- `history_max` is 10. Older revisions cannot be rolled back.
- `reset_values: true` means a later upgrade does not keep values that disappeared from the rendered file.
- SQL migrations applied at startup are not reversed by `helm rollback`.
- Chart-managed Secrets use `helm.sh/resource-policy: keep` and Helm `lookup`. Rollback must not be used to rotate them.
- `buzz_image_digest` empty means the chart uses appVersion `0.1.0`, which is a mutable tag. Rollback of the chart does not pin that image.

This role has no rollback task. An operator who needs one runs `helm rollback`
on the managed host against the same kubeconfig path and context, after reading
`helm history`.

## Uninstall data retention

This role never sets `release_state: absent` and never deletes PVCs.

Verified from this chart revision's templates:

| Object | `helm.sh/resource-policy: keep` | Uninstall behavior |
| --- | --- | --- |
| Chart-managed Secret (`templates/secret-chart.yaml`) | yes | Kept. Rendered only when `secrets.existingSecret` is empty. |
| Git PVC (`templates/pvc-git.yaml`) | no | Deleted with the release. |
| Quickstart MinIO PVC (`templates/quickstart-minio.yaml`) | yes | Kept. |
| Operator-managed Secret named by `buzz_existing_secret` | n/a | Not part of the release. Kept. |
| External Postgres and S3 | n/a | Untouched by Helm. |
| Vendored postgres 0.19.5 and redis 0.30.3 templates | no `resource-policy` match | Assume Helm deletes those PVCs. Confirm before uninstall. |

`helm uninstall` also removes the release history unless `--keep-history` is
used. This role does not run uninstall.

## Destructive data removal (not executed by this role)

`buzz_destroy_data` must stay false. If it is true, `validate-inputs.yml` fails
before Helm runs. There is no task that deletes data.

Operator-owned procedure, only after the backups above, and only with a
separate change review. Run it by hand on the managed host. Do not add it to
this role.

1. `helm uninstall <release> --namespace <namespace> --kubeconfig <path> --kube-context <context>`
2. If the git PVC was not removed, `kubectl delete pvc <fullname>-git -n <namespace>` using the same kubeconfig and context.
3. If quickstart MinIO was used, the MinIO PVC is kept. Delete that PVC only if the bucket is already backed up or intentionally discarded.
4. Delete the operator Secret only if relay identity and database URLs are already stored elsewhere. Deleting `BUZZ_RELAY_PRIVATE_KEY` without a copy is identity loss.
5. Drop the external database and bucket in those systems. Helm will not do it.
6. Confirm `kubectl get pvc,secret -n <namespace>` before leaving.

## Initial owner and admin bootstrap

Upstream does not document a finished key-generation command in the chart.
This role does not generate a keypair, does not set `BUZZ_ADMIN_HOST`, and does
not create the first admin account. What this revision actually says:

Chart README, required inputs:

> `ownerPubkey` — 64-char lowercase hex Nostr pubkey of the relay operator. Required when `relay.requireRelayMembership=true` (default).

Chart README backups:

> Owner private key — held by the operator, not by this chart. Restore by re-installing with the same `ownerPubkey`.

The chart template sets `RELAY_OWNER_PUBKEY` from `ownerPubkey`
(`templates/deployment.yaml`).

Compose README, which is not the install path this role uses:

> The bootstrap script should eventually replace manual `.env` editing for normal users. It is responsible for generating stable secrets and, optionally, an owner keypair.

> `RELAY_OWNER_PUBKEY` is intentionally not prefixed with `BUZZ_`; it must be a 64-character hex Nostr pubkey when closed relay mode is enabled.

Admin dashboard (`docs/admin/README.md` at this revision), not enabled by the chart values this role renders:

> Configure `BUZZ_ADMIN_HOST` to activate the dashboard. A private ingress limits access to the operator VPN or approved source IPs.

> `BUZZ_ADMIN_AUTH=nip98` (default when unset) or `disabled`.

> Owner fallback is an implicit Operator grant for self-hosters that do not yet have an operator configured. It activates only when the configured `RELAY_OPERATOR_PUBKEYS` list is empty, and it is evaluated from config at request time.

This role does not set `BUZZ_ADMIN_HOST` or `RELAY_OPERATOR_PUBKEYS`. Doing so
would be an extra exposure surface and those names are not chart value keys.
After the relay is up, an operator who wants the dashboard follows
`docs/admin/README.md` in the pinned Buzz revision and supplies those env vars
themselves. Membership stays required (`relay.requireRelayMembership: true`).

## Collection interface

`requirements/buzz.yml` pins `kubernetes.core` 5.2.0. Options used were read
from that installed collection. The root `requirements.yml` was not modified.

Helm module options used: `chart_ref`, `release_name`, `release_namespace`,
`release_state: present`, `values_files`, `create_namespace`, `wait`,
`timeout`, `atomic`, `reset_values`, `reuse_values`, `dependency_update`,
`history_max`, `binary_path`, `context`, `kubeconfig`.

`chart_version` and `chart_repo_url` are not set. The chart is a local
directory. Passing a version can make Helm look for a repository copy.

## Offline mode

`buzz_live_checks` defaults false in the role, and `playbooks/buzz-verify.yml`
then prints `NOT RUN` for live reads. `playbooks/deploy_buzz.yml` overrides
that to true and `install.yml` refuses Helm unless release ownership was
checked in the same run. `--syntax-check` does not contact a cluster and is
not runtime proof of install, idempotence, backup, or restore.
