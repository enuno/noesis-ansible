#!/usr/bin/env python3
"""Offline checks for the Buzz Helm role. No cluster required."""
from __future__ import annotations

import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

try:
    import jinja2
except ImportError:  # pragma: no cover
    jinja2 = None

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "roles" / "buzz"
CHART = REPO / "charts" / "buzz" / "0.1.11"
TEMPLATE = ROLE / "templates" / "values-buzz.yml.j2"
DEFAULTS = ROLE / "defaults" / "main.yml"
EXAMPLE = REPO / "inventory" / "example" / "group_vars" / "buzz_k3s.yml"

PIN_SHA = "30ca980b49a7479dd89cb1ced0871af05ff1e12e"
PIN_VERSION = "0.1.11"
PIN_DIGEST = "sha256:9c0df32008f782064104ecec8552f348841f120852d49ace66966a56ba904348"
UNSUPPORTED = (
    "hostNetwork",
    "hostPort",
    "privileged",
    "tailscale",
    "funnel",
    "cert-manager",
    "NodePort",
    "LoadBalancer",
)


def load_yaml(path: Path):
    if yaml is None:
        raise unittest.SkipTest("PyYAML is not available")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def ansible_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "on"}
    return bool(value)


def render(variables: dict) -> str:
    if jinja2 is None:
        raise unittest.SkipTest("Jinja2 is not available")
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False)
    env.filters["bool"] = ansible_bool
    template = env.from_string(TEMPLATE.read_text(encoding="utf-8"))
    return template.render(**variables)


def merged_example() -> dict:
    values = dict(load_yaml(DEFAULTS))
    values.update(load_yaml(EXAMPLE))
    return values


class BuzzOfflineTests(unittest.TestCase):
    def test_chart_pin_files(self):
        chart = (CHART / "Chart.yaml").read_text(encoding="utf-8")
        lock = (CHART / "Chart.lock").read_text(encoding="utf-8")
        provenance = (CHART / "PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn("version: 0.1.11", chart)
        self.assertIn(f"digest: {PIN_DIGEST}", lock)
        self.assertIn("version: 0.19.5", lock)
        self.assertIn("version: 0.30.3", lock)
        self.assertIn(PIN_SHA, provenance)
        self.assertIn(PIN_DIGEST, provenance)
        self.assertTrue((CHART / "charts" / "postgres-0.19.5.tgz").is_file())
        self.assertTrue((CHART / "charts" / "redis-0.30.3.tgz").is_file())

    def test_defaults_pin_and_clusterip(self):
        defaults = load_yaml(DEFAULTS)
        self.assertEqual(defaults["buzz_chart_version"], PIN_VERSION)
        self.assertEqual(defaults["buzz_chart_git_revision"], PIN_SHA)
        self.assertEqual(defaults["buzz_chart_lock_digest"], PIN_DIGEST)
        self.assertEqual(defaults["buzz_profile"], "production")
        self.assertEqual(defaults["buzz_service_type"], "ClusterIP")
        self.assertFalse(defaults["buzz_exposure_enabled"])
        self.assertFalse(defaults["buzz_ingress_enabled"])
        self.assertFalse(defaults["buzz_httproute_enabled"])
        self.assertFalse(defaults["buzz_live_checks"])
        self.assertFalse(defaults["buzz_destroy_data"])
        self.assertFalse(defaults["buzz_helm_dependency_update"])
        self.assertEqual(defaults["buzz_existing_secret"], "")
        self.assertEqual(defaults["buzz_image_digest"], "")

    def test_example_inventory_is_placeholder_and_clusterip(self):
        hosts = (REPO / "inventory" / "example" / "hosts.ini").read_text(encoding="utf-8")
        self.assertIn("buzz-k3s.example.invalid", hosts)
        self.assertIn("CHANGE_ME", hosts)
        self.assertNotIn("31.97.209.57", hosts)
        example = load_yaml(EXAMPLE)
        self.assertEqual(example["buzz_service_type"], "ClusterIP")
        self.assertFalse(example["buzz_exposure_enabled"])
        self.assertFalse(example["buzz_ingress_enabled"])
        self.assertNotIn("password", example)

    def test_template_is_deterministic_and_secret_free(self):
        variables = merged_example()
        first = render(variables)
        second = render(variables)
        self.assertEqual(first, second)
        rendered = load_yaml_text(first)
        self.assertEqual(rendered["service"]["type"], "ClusterIP")
        self.assertFalse(rendered["ingress"]["enabled"])
        self.assertFalse(rendered["httproute"]["enabled"])
        self.assertFalse(rendered["postgresql"]["enabled"])
        self.assertFalse(rendered["redis"]["enabled"])
        self.assertFalse(rendered["minio"]["enabled"])
        self.assertEqual(rendered["secrets"]["existingSecret"], "change-me-buzz-secret")
        self.assertEqual(rendered["secrets"]["relayPrivateKey"], "")
        self.assertEqual(rendered["secrets"]["gitHookHmacSecret"], "")
        self.assertEqual(rendered["s3"]["accessKey"], "")
        self.assertEqual(rendered["s3"]["secretKey"], "")
        self.assertEqual(rendered["externalPostgresql"]["url"], "")
        self.assertEqual(rendered["externalRedis"]["url"], "")
        self.assertNotIn("BEGIN ", first)
        self.assertNotIn("postgres://", first)
        self.assertNotIn("redis://", first)

    def test_unsupported_keys_absent(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        rendered = render(merged_example())
        for blob in (template, rendered):
            for key in UNSUPPORTED:
                self.assertNotIn(key, blob)
        parsed = load_yaml_text(rendered)
        flat = set(flatten_keys(parsed))
        for key in ("hostNetwork", "hostPort", "privileged", "tailscale", "funnel"):
            self.assertNotIn(key, flat)
        default_keys = set(flatten_keys(load_yaml(DEFAULTS)))
        for key in ("hostNetwork", "hostPort", "privileged"):
            self.assertFalse(any(item.endswith(key) for item in default_keys))

    def test_quickstart_persistence_uses_verified_subchart_storage_class(self):
        variables = merged_example()
        variables["buzz_profile"] = "quickstart"
        variables["buzz_existing_secret"] = ""
        variables["buzz_s3_endpoint"] = ""
        rendered = load_yaml_text(render(variables))
        self.assertTrue(rendered["quickstart"])
        self.assertTrue(rendered["postgresql"]["persistence"]["enabled"])
        self.assertEqual(rendered["postgresql"]["persistence"]["storageClass"], "CHANGE_ME_STORAGE_CLASS")
        self.assertEqual(rendered["redis"]["persistence"]["storageClass"], "CHANGE_ME_STORAGE_CLASS")
        self.assertNotIn("storageClass", rendered["minio"]["persistence"])
        self.assertEqual(rendered["secrets"]["relayPrivateKey"], "")
        self.assertEqual(rendered["s3"]["accessKey"], "")

    def test_deploy_refuses_helm_without_ownership_check(self):
        playbook = (REPO / "playbooks" / "deploy_buzz.yml").read_text(encoding="utf-8")
        install = (ROLE / "tasks" / "install.yml").read_text(encoding="utf-8")
        preflight = (ROLE / "tasks" / "preflight-live.yml").read_text(encoding="utf-8")
        self.assertIn("buzz_live_checks: true", playbook)
        self.assertLess(
            install.index("buzz_release_ownership_checked"),
            install.index("kubernetes.core.helm:"),
        )
        self.assertIn("buzz_release_ownership_checked: true", preflight)
        self.assertIn("match('^buzz-')", preflight)


def load_yaml_text(text: str):
    if yaml is None:
        raise unittest.SkipTest("PyYAML is not available")
    return yaml.safe_load(text)


def flatten_keys(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path
            yield from flatten_keys(child, path)
    elif isinstance(value, list):
        for item in value:
            yield from flatten_keys(item, prefix)


if __name__ == "__main__":
    unittest.main()
