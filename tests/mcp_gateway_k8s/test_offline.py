#!/usr/bin/env python3
"""Offline checks for the MCP Gateway Registry k8s role.

Every check here exists because something it guards was actually broken, or
because the equivalent mistake has bitten a sibling role. The reachability,
assert-parameter, key-casing and retry-placement checks in particular each
correspond to a real defect that the original three-test suite missed.
"""
from __future__ import annotations

import pathlib
import re
import sys
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROLE = ROOT / "roles" / "mcp_gateway_k8s"
TASKS = ROLE / "tasks"
PLAYBOOK = ROOT / "playbooks" / "mcp-gateway-k8s.yml"

FLEET_BW_PROJECT = "72974d0e-81af-4678-bab7-b46000985859"

# ansible.builtin.assert accepts exactly these. A typo'd extra key (the real
# bug: `fail_msg2`) is NOT caught by --syntax-check and only fails when the
# task finally runs - here, after a ~20 minute stack deploy.
ASSERT_ALLOWED = {"that", "fail_msg", "msg", "success_msg", "quiet"}


def flatten(tasks):
    out = []
    for t in tasks or []:
        if not isinstance(t, dict):
            continue
        out.append(t)
        for key in ("block", "rescue", "always"):
            if isinstance(t.get(key), list):
                out.extend(flatten(t[key]))
    return out


def load_tasks(path: pathlib.Path):
    return flatten(yaml.safe_load(path.read_text()) or [])


def all_task_files():
    return sorted(p for p in TASKS.glob("*.yml"))


def every_task():
    for path in all_task_files():
        for task in load_tasks(path):
            yield path.name, task


def rendered_helm_values():
    for task in load_tasks(TASKS / "install.yml"):
        fact = task.get("ansible.builtin.set_fact") or {}
        if "mcp_gateway_k8s_helm_values" in fact:
            return fact["mcp_gateway_k8s_helm_values"]
    return None


class TestDefaults(unittest.TestCase):
    def setUp(self):
        self.text = (ROLE / "defaults" / "main.yml").read_text()
        self.defaults = yaml.safe_load(self.text)

    def test_defaults_are_off(self) -> None:
        self.assertRegex(self.text, r"mcp_gateway_k8s_enabled:\s+false")
        self.assertRegex(self.text, r"mcp_gateway_k8s_expose_enabled:\s+false")
        self.assertNotRegex(self.text, r"mcp_gateway_k8s_image_tag:\s+[\"']latest[\"']")
        sha = re.search(r"mcp_gateway_k8s_git_version:\s+[\"']([0-9a-f]+)[\"']", self.text)
        self.assertIsNotNone(sha)
        self.assertGreaterEqual(len(sha.group(1)), 40)

    def test_rollback_is_default_off_with_no_default_revision(self) -> None:
        # A rollback that can fire on an untagged run, or that guesses which
        # revision to go back to, is worse than one that refuses.
        self.assertIs(self.defaults.get("mcp_gateway_k8s_rollback_enabled"), False)
        self.assertNotIn("mcp_gateway_k8s_rollback_revision", self.defaults)

    def test_escrow_project_is_enforced_not_defaulted(self) -> None:
        self.assertEqual(
            self.defaults.get("mcp_gateway_k8s_required_bw_project_id"), FLEET_BW_PROJECT
        )
        # An unset id means "escrow not configured here"; it must not silently
        # default to the real project.
        self.assertEqual(self.defaults.get("mcp_gateway_k8s_bw_project_id"), "")
        self.assertIs(self.defaults.get("mcp_gateway_k8s_allow_bitwarden_write"), False)

    def test_target_is_never_implicit(self) -> None:
        self.assertEqual(self.defaults.get("mcp_gateway_k8s_kubeconfig"), "")
        self.assertEqual(self.defaults.get("mcp_gateway_k8s_context"), "")

    def test_mongodb_is_single_member_on_a_single_node(self) -> None:
        # 3 members of a replica set on one node can never elect a writable
        # primary, and the install asserts this too.
        self.assertEqual(self.defaults.get("mcp_gateway_k8s_mongodb_replicas"), 1)


class TestPlaybook(unittest.TestCase):
    def setUp(self):
        self.text = PLAYBOOK.read_text()

    def test_playbook_does_not_mention_mcpjungle_mutation(self) -> None:
        self.assertIn("Does not modify MCPJungle", self.text)
        self.assertNotIn("mcpjungle_k8s_enabled", self.text)

    def test_playbook_has_exactly_one_pre_tasks_block(self) -> None:
        # YAML keeps the LAST duplicate key, so a second pre_tasks silently
        # discards the first - which is how the fail-fast target assertion
        # went missing once already.
        self.assertEqual(len(re.findall(r"^\s{2}pre_tasks:", self.text, re.M)), 1)

    def test_every_documented_tag_is_reachable(self) -> None:
        documented = set(re.findall(r"^#   (\w+)\s+\S", self.text, re.M))
        wired = set()
        for _, task in every_task():
            wired.update(task.get("tags") or [])
        missing = documented - wired
        self.assertFalse(missing, f"documented but unreachable tags: {sorted(missing)}")


class TestTaskWiring(unittest.TestCase):
    def setUp(self):
        self.main = load_tasks(TASKS / "main.yml")
        self.included = {
            t["ansible.builtin.include_tasks"]
            for t in self.main
            if isinstance(t.get("ansible.builtin.include_tasks"), str)
        }

    def test_no_task_file_is_orphaned(self) -> None:
        # The real bug: bw_escrow.yml and rollback.yml existed, were correct,
        # and were unreachable - so the advertised `secrets` phase never ran
        # and the release's generated credentials were never escrowed.
        reachable = {"main.yml"}
        for path in all_task_files():
            for task in load_tasks(path):
                inc = task.get("ansible.builtin.include_tasks")
                if isinstance(inc, str):
                    reachable.add(inc)
        orphans = {p.name for p in all_task_files()} - reachable
        self.assertFalse(orphans, f"task files nothing includes: {sorted(orphans)}")

    def test_every_include_target_exists(self) -> None:
        for name in self.included:
            self.assertTrue((TASKS / name).is_file(), f"missing include target: {name}")

    def test_escrow_runs_after_install_and_before_expose(self) -> None:
        # The chart generates its own credentials, so they cannot be escrowed
        # before install; but escrow must still precede exposure, or a
        # credential is reachable from the tailnet before it is backed up.
        order = [t.get("ansible.builtin.include_tasks") for t in self.main]
        order = [o for o in order if isinstance(o, str)]
        self.assertLess(order.index("install.yml"), order.index("bw_escrow.yml"))
        self.assertLess(order.index("bw_escrow.yml"), order.index("expose_tailscale.yml"))

    def test_rollback_is_gated_on_its_flag_not_only_its_tag(self) -> None:
        rb = [t for t in self.main
              if t.get("ansible.builtin.include_tasks") == "rollback.yml"]
        self.assertEqual(len(rb), 1)
        self.assertIn("mcp_gateway_k8s_rollback_enabled", str(rb[0].get("when", "")))

    def test_escrow_is_gated_on_the_project_id(self) -> None:
        esc = [t for t in self.main
               if t.get("ansible.builtin.include_tasks") == "bw_escrow.yml"]
        self.assertEqual(len(esc), 1)
        self.assertIn("mcp_gateway_k8s_bw_project_id", str(esc[0].get("when", "")))


class TestTaskHygiene(unittest.TestCase):
    def test_assert_tasks_use_only_real_parameters(self) -> None:
        bad = []
        for fname, task in every_task():
            spec = task.get("ansible.builtin.assert")
            if isinstance(spec, dict):
                extra = set(spec) - ASSERT_ALLOWED
                if extra:
                    bad.append((fname, task.get("name"), sorted(extra)))
        self.assertFalse(bad, f"invalid assert parameters: {bad}")

    def test_no_snake_case_kubernetes_status_keys(self) -> None:
        # kubernetes.core returns the API object verbatim, so these are
        # camelCase. A predicate written against the snake_case name tests an
        # attribute that is never defined and silently measures nothing.
        offenders = []
        for path in all_task_files():
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if re.search(r"\b(container_statuses|load_balancer|cluster_ip)\b", line):
                    offenders.append(f"{path.name}:{n}")
        self.assertFalse(offenders, f"snake_case k8s keys: {offenders}")

    def test_retries_only_on_tasks_that_re_read_state(self) -> None:
        # An `until` on an assert/debug re-evaluates an already-registered
        # variable, so it can never change its mind: it burns every retry and
        # then fails.
        NON_READING = ("ansible.builtin.assert", "ansible.builtin.debug",
                       "ansible.builtin.set_fact", "ansible.builtin.fail")
        bad = []
        for fname, task in every_task():
            if "until" in task or "retries" in task:
                for mod in NON_READING:
                    if mod in task:
                        bad.append((fname, task.get("name"), mod))
        self.assertFalse(bad, f"retry/until on a task that re-reads nothing: {bad}")

    def test_retry_loops_are_guarded_against_check_mode(self) -> None:
        # --check does not install the release, so a readiness wait can never
        # succeed; unguarded it spends retries x delay before failing the
        # preview, which is meant to be the cheap, safe path.
        bad = []
        for fname, task in every_task():
            if "until" in task and "ansible_check_mode" not in str(task.get("when", "")):
                bad.append((fname, task.get("name")))
        self.assertFalse(bad, f"unguarded retry loop in check mode: {bad}")

    def test_secret_bearing_tasks_are_no_log(self) -> None:
        bad = []
        for fname, task in every_task():
            blob = str(task)
            touches_secret = (
                "BWS_ACCESS_TOKEN" in blob
                or "bws_access_token" in blob
                or "value-file" in blob
            )
            # An assert that only length-checks the token is exempt: Ansible
            # prints `that` as literal Jinja rather than resolved values, and
            # no_log there would suppress the message telling the operator
            # which Bitwarden record to create. Everything that PASSES the
            # secret onward (environment:, cmd:, value-file) is not exempt.
            if "ansible.builtin.assert" in task:
                continue
            if touches_secret and not task.get("no_log"):
                bad.append((fname, task.get("name")))
        self.assertFalse(bad, f"secret-bearing task without no_log: {bad}")

    def test_no_hardcoded_credential_literals(self) -> None:
        pat = re.compile(
            r"(password|secret|token|api[_-]?key)\s*[:=]\s*[\"'][A-Za-z0-9/+_-]{12,}[\"']",
            re.I,
        )
        allowed = re.compile(r"lookup|bw_|bitwarden|existingSecret|secretKeyRef|"
                             r"PLACEHOLDER|change-me|example|\{\{")
        bad = []
        for path in all_task_files() + [ROLE / "defaults" / "main.yml"]:
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if pat.search(line) and not allowed.search(line):
                    bad.append(f"{path.name}:{n}")
        self.assertFalse(bad, f"possible hardcoded credential: {bad}")


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.text = (TASKS / "install.yml").read_text()
        self.tasks = load_tasks(TASKS / "install.yml")
        self.rendered = rendered_helm_values()
        assert self.rendered is not None, "no task renders mcp_gateway_k8s_helm_values"

    def test_install_pins_git_and_disables_telemetry(self) -> None:
        self.assertIn("mcpTelemetryDisabled: true", self.text)
        self.assertIn("ansible.builtin.git", self.text)
        self.assertIn("kubernetes.core.helm", self.text)

    def test_all_upstream_telemetry_channels_are_disabled(self) -> None:
        # Upstream defaults every one of these to false, i.e. telemetry ON:
        # a startup ping plus a daily heartbeat. Disabling only
        # `mcpTelemetryDisabled` leaves the opt-out and the IMDS
        # cloud-detection probe at their upstream values.
        self.assertIsNotNone(self.rendered, "no task renders mcp_gateway_k8s_helm_values")
        app = self.rendered["registry"]["app"]
        self.assertIs(app.get("mcpTelemetryDisabled"), True)
        self.assertIs(app.get("mcpTelemetryOptOut"), True)
        self.assertIs(app.get("mcpTelemetryImdsProbeDisabled"), True)

    def test_helm_release_is_pinned_in_the_deploying_task(self) -> None:
        # Scoped to the task that actually deploys: a file-wide grep stays
        # green after the apply-time pin is deleted, because the same strings
        # also live in defaults and comments.
        helm = [t for t in self.tasks if "kubernetes.core.helm" in t]
        self.assertEqual(len(helm), 1)
        spec = helm[0]["kubernetes.core.helm"]
        self.assertTrue(spec.get("atomic"), "release must roll back on failure")
        self.assertTrue(spec.get("wait"))
        self.assertIn("mcp_gateway_k8s_release_name", str(spec.get("name")))
        self.assertIs(spec.get("create_namespace"), False)

    def test_values_dict_is_actually_populated(self) -> None:
        # A `values:` that nothing builds means the install silently succeeds
        # on chart defaults and no documented variable has any effect.
        helm = [t for t in self.tasks if "kubernetes.core.helm" in t][0]
        self.assertIn("mcp_gateway_k8s_helm_values",
                      str(helm["kubernetes.core.helm"].get("values")))
        self.assertIsNotNone(self.rendered)

    def test_chart_ingress_is_disabled_so_the_operator_owns_exposure(self) -> None:
        # The upstream registry Ingress is ALB-shaped (alb.* annotations, no
        # spec.tls) and can never satisfy the Tailscale operator, so it must
        # stay off and the role's own Ingress must own exposure.
        self.assertIs(self.rendered["registry"]["ingress"]["enabled"], False)
        self.assertIs(self.rendered["auth-server"]["ingress"]["enabled"], False)

    def test_readiness_is_measured_on_container_ready_not_mere_presence(self) -> None:
        # The original predicate rejected pods whose containerStatuses were
        # *defined*, so it only ever proved pods HAD statuses - it never
        # looked at `ready` at all.
        #
        # Scoped to each task's own expression on purpose: a file-wide grep
        # for rejectattr('ready') stays green when the WAIT loop is weakened,
        # because the assert below it still contains the string. That exact
        # mutation slipped through until this was task-scoped.
        wait = [t for t in self.tasks
                if "until" in t and "kubernetes.core.k8s_info" in t
                and "Pod" == (t["kubernetes.core.k8s_info"] or {}).get("kind")]
        self.assertEqual(len(wait), 1, "expected exactly one pod-readiness wait loop")
        self.assertIn("rejectattr('ready')", str(wait[0]["until"]),
                      "the wait loop does not test container readiness")

        gate = [t for t in self.tasks
                if isinstance(t.get("ansible.builtin.assert"), dict)
                and "containerStatuses" in str(t["ansible.builtin.assert"].get("that"))]
        self.assertEqual(len(gate), 1, "expected exactly one pod-readiness assert")
        self.assertIn("rejectattr('ready')", str(gate[0]["ansible.builtin.assert"]["that"]),
                      "the readiness assert does not test container readiness")


    def test_read_only_probes_consumed_downstream_run_in_check_mode(self) -> None:
        # --check skips `command` by default. A read-only probe whose output a
        # later assert consumes therefore registers nothing, and the assert
        # fails on empty data - so the preview dies early and previews almost
        # nothing. The fix is check_mode: false on the READ. The write in the
        # same sequence (`helm dependency update`) must NOT get it.
        text = (TASKS / "install.yml").read_text()
        reads = ("rev-parse", "helm dependency list")
        for task in load_tasks(TASKS / "install.yml"):
            cmd = str((task.get("ansible.builtin.command") or {}).get("cmd", ""))
            if any(r in cmd for r in reads):
                self.assertIs(
                    task.get("check_mode"), False,
                    f"read-only probe missing check_mode: false: {task.get('name')}",
                )
        # And the mutating counterpart must stay preview-safe.
        for task in load_tasks(TASKS / "install.yml"):
            cmd = str((task.get("ansible.builtin.command") or {}).get("cmd", ""))
            if "helm dependency update" in cmd:
                self.assertNotIn("check_mode", task,
                                 "the dependency FETCH must stay skipped in --check")
        self.assertIn("check_mode: false", text)

    def test_pin_assertion_survives_a_missing_register(self) -> None:
        # `.stdout.strip()` raises when the probe was skipped; the default
        # keeps the failure message readable instead of an undefined-attr
        # traceback.
        text = (TASKS / "install.yml").read_text()
        self.assertNotIn(".stdout.strip()", text)


    def test_no_set_fact_references_its_own_sibling_key(self) -> None:
        # Ansible resolves every argument of a task before applying any of
        # them, so a set_fact key cannot reference another key defined in the
        # SAME task - it fails with "... is undefined" on the real run, not
        # only in --check. Split such computations across two tasks.
        bad = []
        for fname, task in every_task():
            fact = task.get("ansible.builtin.set_fact")
            if not isinstance(fact, dict):
                continue
            keys = set(fact)
            for key, value in fact.items():
                for other in keys - {key}:
                    if other in str(value):
                        bad.append((fname, task.get("name"), f"{key} -> {other}"))
        self.assertFalse(bad, f"set_fact key referencing its own sibling: {bad}")


    def test_from_json_always_has_a_default_for_empty_stdout(self) -> None:
        # A registered command's stdout is empty whenever the task was skipped
        # (--check) or the thing it queried is absent. from_json then raises
        # "Expecting value: line 1 column 1 (char 0)", which reads like
        # corrupt output rather than "nothing there". This bit twice: once in
        # bw_escrow.yml and once in validate.yml.
        bad = []
        for path in all_task_files():
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if line.lstrip().startswith("#") or "from_json" not in line:
                    continue
                if ".stdout" in line and "default(" not in line:
                    bad.append(f"{path.name}:{n}")
        self.assertFalse(bad, f"from_json on stdout without a default: {bad}")


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    sys.exit(0 if result.wasSuccessful() else 1)
