#!/usr/bin/env python3
"""Helm post-renderer: constrain the MongoDB member containers.

The upstream umbrella chart renders a MongoDBCommunity custom resource but
only templates `global.nodeSelector` into it. The MongoDB Kubernetes
Operator builds the member StatefulSet from its OWN hardcoded defaults:
every container it creates gets 500m CPU / 400M memory requests, and the
member pod carries three such containers (mongod, mongodb-agent and the
operator-utilities sidecar). That is 1000m of CPU request for a
single-member replica set, which does not fit alongside the workloads
already committed on this node.

The operator merges `spec.statefulSet.spec.template.spec.containers` from
the custom resource into the StatefulSet it generates, matching containers
by name and replacing the resource requirements of a matched container
(mongodb-community-operator merge.ResourceRequirements). The CRD marks
`statefulSet.spec` with x-kubernetes-preserve-unknown-fields, so the API
server accepts the injected container list verbatim.

This post-renderer therefore rewrites the rendered MongoDBCommunity
manifest to carry explicit, small resource requests for the operator's
containers, and adds a nodeSelector so the member lands on the intended
node.

It is deliberately narrow: it touches ONLY the MongoDBCommunity resource
and leaves every other rendered manifest semantically intact. It is also
idempotent, so re-running it on an already-processed manifest is a no-op.

The resource values are passed in through the environment so the role
remains the single source of truth for the budget.

Usage: helm --post-renderer ./mongodb_resources.py
       (stdin = rendered manifest, stdout = rewritten manifest)
"""

import os
import sys

import yaml

# Container names the operator creates for a MongoDBCommunity member pod.
# From mongodb-community-operator controllers/construct/mongodbstatefulset.go:
#   MongdbName                      = "mongod"
#   AgentName                       = "mongodb-agent"
#   util.AgentContainerUtilitiesName = "mongodb-agent-operator-utilities"
# and, when init containers are used:
#   versionUpgradeHookName          = "mongod-posthook"
#   ReadinessProbeContainerName     = "mongodb-agent-readinessprobe"
#
# The operator only creates the utilities sidecar when it does NOT use init
# containers, so it is listed here defensively: a matched name has its
# resources replaced, and an unmatched one is merged in as a new container.
CONTAINER_ENV = {
    "mongod": ("MCP_GATEWAY_MONGOD_CPU", "MCP_GATEWAY_MONGOD_MEM", "250m", "400M"),
    "mongodb-agent": (
        "MCP_GATEWAY_MONGO_AGENT_CPU",
        "MCP_GATEWAY_MONGO_AGENT_MEM",
        "100m",
        "200M",
    ),
    "mongodb-agent-operator-utilities": (
        "MCP_GATEWAY_MONGO_SIDECAR_CPU",
        "MCP_GATEWAY_MONGO_SIDECAR_MEM",
        "50m",
        "64M",
    ),
}

INIT_CONTAINER_ENV = {
    "mongod-posthook": (
        "MCP_GATEWAY_MONGO_INIT_CPU",
        "MCP_GATEWAY_MONGO_INIT_MEM",
        "50m",
        "64M",
    ),
    "mongodb-agent-readinessprobe": (
        "MCP_GATEWAY_MONGO_INIT_CPU",
        "MCP_GATEWAY_MONGO_INIT_MEM",
        "50m",
        "64M",
    ),
}


def build_resources(spec):
    """Build a resource map from an env-var name -> (cpu, mem, default) spec."""
    out = {}
    for name, (cpu_key, mem_key, cpu_default, mem_default) in spec.items():
        out[name] = {
            "requests": {
                "cpu": os.environ.get(cpu_key, cpu_default),
                "memory": os.environ.get(mem_key, mem_default),
            }
        }
    return out


def patch_mongodbcommunity(doc):
    """Inject resource requests and a nodeSelector into a MongoDBCommunity."""
    if not isinstance(doc, dict) or doc.get("kind") != "MongoDBCommunity":
        return doc

    spec = doc.setdefault("spec", {})
    sts_spec = spec.setdefault("statefulSet", {}).setdefault("spec", {})
    pod_spec = sts_spec.setdefault("template", {}).setdefault("spec", {})

    pod_spec["nodeSelector"] = {
        "kubernetes.io/hostname": os.environ.get(
            "MCP_GATEWAY_NODE_NAME", "noesis-praxis"
        )
    }

    def apply(resources_by_name, key):
        entries = pod_spec.get(key) or []
        by_name = {
            e.get("name"): e
            for e in entries
            if isinstance(e, dict) and e.get("name")
        }
        for name, resources in resources_by_name.items():
            if name in by_name:
                by_name[name]["resources"] = resources
            else:
                entries.append({"name": name, "resources": resources})
        pod_spec[key] = entries

    apply(build_resources(CONTAINER_ENV), "containers")
    apply(build_resources(INIT_CONTAINER_ENV), "initContainers")

    return doc


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        sys.stdout.write(raw)
        return 0

    documents = list(yaml.safe_load_all(raw))
    patched = [patch_mongodbcommunity(d) for d in documents]

    sys.stdout.write(
        yaml.safe_dump_all(patched, default_flow_style=False, sort_keys=False)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
