"""Project A deployment contracts; no secrets service, Docker mutation, or cluster calls."""
from pathlib import Path
import unittest
import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/unifi_mcp'
DEFAULTS = yaml.safe_load((ROLE / 'defaults/main.yml').read_text())


class DeploymentContract(unittest.TestCase):
    def test_selector_and_safe_defaults(self):
        main = (ROLE / 'tasks/main.yml').read_text()
        for mode in ('docker_single', 'compose_fleet', 'compose_fleet_scale', 'kubernetes_helm'):
            self.assertIn(mode, main)
        self.assertFalse(DEFAULTS['unifi_mcp_allow_apply'])
        self.assertFalse(DEFAULTS['unifi_mcp_allow_bws_create'])
        self.assertFalse(DEFAULTS['unifi_mcp_allow_expose'])

    def test_runtime_secret_excludes_owner_and_cloud_key(self):
        task = (ROLE / 'tasks/kubernetes.yml').read_text()
        runtime = task.split('unifi_mcp_runtime_data:', 1)[1].split('- name: Build owner-only', 1)[0]
        for forbidden in ('POSTGRES_PASSWORD:', 'RUNTIME_PASSWORD:', 'MIGRATION_DATABASE_URL:', 'UNIFI_CLOUD_API_KEY:'):
            self.assertNotIn(forbidden, runtime)
        self.assertIn('fleet.migrate=false', (ROOT / 'docs/unifi-mcp-k8s-runbook.md').read_text())
        self.assertIn('migrate: false', task)
        self.assertIn('unifi_mcp_database_secret_name', task)

    def test_role_grants_and_ordering(self):
        sql = (ROLE / 'templates/runtime-role.sql.j2').read_text()
        self.assertIn('GRANT SELECT, INSERT ON audit_log', sql)
        self.assertNotIn('DELETE ON audit_log', sql)
        self.assertNotIn('UPDATE ON audit_log', sql)
        task = (ROLE / 'tasks/kubernetes.yml').read_text()
        self.assertLess(task.index('Wait for successful migration and runtime grant'), task.index('Install pinned chart'))

    def test_k8s_resources_shape_and_readiness(self):
        rendered = Environment(undefined=StrictUndefined).from_string((ROLE / 'templates/fleet-resources.yml.j2').read_text()).render(
            unifi_mcp_namespace='test', unifi_mcp_postgres_image=DEFAULTS['unifi_mcp_postgres_image'],
            unifi_mcp_redis_image=DEFAULTS['unifi_mcp_redis_image'], unifi_mcp_storage_class='local-path',
            unifi_mcp_secret_name='app', unifi_mcp_database_secret_name='owner', unifi_mcp_redis_secret_name='redis',
            unifi_mcp_postgres_size='8Gi', unifi_mcp_redis_size='2Gi')
        resources = list(yaml.safe_load_all(rendered))
        pods = [x['spec']['template']['spec'] for x in resources if x['kind'] in ('Deployment', 'StatefulSet')]
        self.assertEqual(len(pods), 2)
        for pod in pods:
            self.assertTrue(pod['securityContext']['runAsNonRoot'])
            self.assertFalse(pod['automountServiceAccountToken'])
        redis = next(x for x in resources if x['kind'] == 'Deployment')['spec']['template']['spec']['containers'][0]
        self.assertIn('readinessProbe', redis)
        self.assertEqual(redis['env'][0]['valueFrom']['secretKeyRef']['name'], 'redis')

    def test_bootstrap_job_owner_isolation(self):
        rendered = Environment(undefined=StrictUndefined).from_string((ROLE / 'templates/bootstrap-job.yml.j2').read_text()).render(
            unifi_mcp_namespace='test', unifi_mcp_image=DEFAULTS['unifi_mcp_image'],
            unifi_mcp_image_tag=DEFAULTS['unifi_mcp_image_tag'],
            unifi_mcp_postgres_image=DEFAULTS['unifi_mcp_postgres_image'],
            unifi_mcp_database_secret_name='owner')
        job = yaml.safe_load(rendered)
        self.assertEqual(job['kind'], 'Job')
        pod = job['spec']['template']['spec']
        self.assertEqual(pod['initContainers'][0]['command'][-1], 'migrate')
        self.assertEqual(pod['containers'][0]['env'][3]['valueFrom']['secretKeyRef']['name'], 'owner')
        self.assertFalse(pod['automountServiceAccountToken'])

    def test_compose_placeholder_overridden(self):
        overlay = (ROLE / 'templates/compose-overlay.yml').read_text()
        self.assertIn('MIGRATION_DATABASE_URL', overlay)
        self.assertIn('RUNTIME_PASSWORD', overlay)
        self.assertIn('REDIS_URL', overlay)
        self.assertIn('runtime-role:', overlay)
        self.assertIn('!reset null', overlay)
        self.assertNotIn(':***@postgres', overlay.split('services:', 1)[1])


if __name__ == '__main__':
    unittest.main()
