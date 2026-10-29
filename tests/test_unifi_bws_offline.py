"""Offline contract tests; no BWS calls or cluster access."""
import importlib.util
import base64
import unittest
from types import SimpleNamespace as NS
from uuid import UUID

spec = importlib.util.spec_from_file_location("resolver", "scripts/unifi_bws_resolve.py")
assert spec is not None and spec.loader is not None
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)
PROJECT = UUID("72974d0e-81af-4678-bab7-b46000985859")
ORG = UUID("93331de5-0000-4000-8000-000000000000")


class FakeClient:
    def __init__(self, entries):
        self.entries = entries
        self.writes = []

    def projects(self):
        return NS(get=lambda _: NS(data=NS(organization_id=ORG)))

    def secrets(self):
        return self

    def list(self, _):
        return NS(data=NS(data=[NS(key=e.key, id=e.id,
                                   project_ids=e.project_ids) for e in self.entries]))

    def get(self, id):
        return NS(data=next(e for e in self.entries if str(e.id) == id))

    def create(self, org, key, value, note, projects):
        assert org == ORG and projects == [PROJECT] and value
        entry = NS(id=UUID("00000000-0000-4000-8000-000000000001"), key=key,
                   value=value, project_id=PROJECT, project_ids=projects)
        self.entries.append(entry)
        self.writes.append(key)
        return NS(data=entry)


class ResolverTest(unittest.TestCase):
    def test_reuse_never_writes(self):
        e = NS(id=UUID("00000000-0000-4000-8000-000000000002"), key="EXISTING",
               value="retained", project_id=PROJECT, project_ids=[PROJECT])
        c = FakeClient([e])
        self.assertEqual(resolver.resolve(c, PROJECT, ORG, {"API": "EXISTING"}, {}, False)["values"]["API"], "retained")
        self.assertEqual(c.writes, [])

    def test_missing_without_gate_fails(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            resolver.resolve(FakeClient([]), PROJECT, ORG, {"MCP_AUTH_TOKEN": "SCOPED"}, {}, False)

    def test_create_then_reuse(self):
        c = FakeClient([])
        req = {"MCP_AUTH_TOKEN": "SCOPED"}
        first = resolver.resolve(c, PROJECT, ORG, req, {}, True)
        second = resolver.resolve(c, PROJECT, ORG, req, {}, True)
        self.assertEqual(first["values"], second["values"])
        self.assertEqual(first["created"], ["MCP_AUTH_TOKEN"])
        self.assertEqual(c.writes, ["SCOPED"])

    def test_duplicates_fail_closed(self):
        entries = [NS(id=UUID(int=i), key="DUP", value="secret", project_id=PROJECT,
                      project_ids=[PROJECT]) for i in (1, 2)]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            resolver.resolve(FakeClient(entries), PROJECT, ORG, {"API": "DUP"}, {}, False)

    def test_fleet_key_is_fernet_compatible_and_reused(self):
        client = FakeClient([])
        first = resolver.resolve(client, PROJECT, ORG,
                                 {"UNIFI_FLEET_CREDENTIAL_KEY": "SCOPED_FLEET"}, {}, True)
        value = first["values"]["UNIFI_FLEET_CREDENTIAL_KEY"]
        self.assertEqual(len(base64.urlsafe_b64decode(value)), 32)
        self.assertEqual(resolver.resolve(client, PROJECT, ORG,
                         {"UNIFI_FLEET_CREDENTIAL_KEY": "SCOPED_FLEET"}, {}, True)["values"]["UNIFI_FLEET_CREDENTIAL_KEY"], value)

    def test_wrong_project_fails(self):
        e = NS(id=UUID(int=3), key="EXISTING", value="secret", project_ids=[])
        with self.assertRaisesRegex(ValueError, "missing"):
            resolver.resolve(FakeClient([e]), PROJECT, ORG, {"API": "EXISTING"}, {}, False)


if __name__ == "__main__":
    unittest.main()
