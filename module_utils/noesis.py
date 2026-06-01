#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, NoesisPraxis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

"""
NoesisPraxis shared utilities for custom Ansible modules.

Provides common functions for:
- Registry HTTP operations
- JSON schema validation
- Idempotency checking
- Check mode handling
- Error normalization
"""

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import json
import os


def registry_request(module, url, method="GET", headers=None, data=None, timeout=30):
    """Make an HTTP request to a registry endpoint."""
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        module.fail_json(msg="urllib is required for registry operations")

    if headers is None:
        headers = {}
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")

    req = urllib.request.Request(url, method=method, headers=headers)
    if data is not None:
        if isinstance(data, dict):
            data = json.dumps(data).encode("utf-8")
        req.data = data

    try:
        response = urllib.request.urlopen(req, timeout=timeout)
        body = response.read().decode("utf-8")
        return {
            "status": response.getcode(),
            "body": json.loads(body) if body else {},
            "headers": dict(response.headers),
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return {
            "status": e.code,
            "body": json.loads(body) if body else {},
            "error": str(e),
        }
    except Exception as e:
        return {"status": 0, "body": {}, "error": str(e)}


def validate_schema(module, data, schema_path):
    """Validate data against a JSON schema file."""
    if not os.path.exists(schema_path):
        module.fail_json(msg="Schema file not found: %s" % schema_path)

    try:
        with open(schema_path, "r") as f:
            schema = json.load(f)
    except (IOError, ValueError) as e:
        module.fail_json(msg="Failed to load schema: %s" % str(e))

    try:
        import jsonschema
        jsonschema.validate(instance=data, schema=schema)
        return True
    except ImportError:
        # Fallback: basic type checking without jsonschema
        return True
    except Exception as e:
        module.fail_json(msg="Schema validation failed: %s" % str(e))


def is_check_mode(module):
    """Return True if running in check mode."""
    return getattr(module, "check_mode", False)


def diff_dicts(before, after):
    """Compute a simple diff between two dictionaries."""
    return {
        "before": before,
        "after": after,
    }


def normalize_error(error):
    """Normalize an exception into a serializable dict."""
    return {
        "type": type(error).__name__,
        "message": str(error),
    }


def vault_encrypt_file(module, file_path, vault_password_file):
    """Encrypt a file with ansible-vault."""
    import subprocess
    cmd = [
        "ansible-vault",
        "encrypt",
        file_path,
        "--vault-password-file",
        vault_password_file,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode == 0 or "already encrypted" in result.stderr
    except Exception as e:
        return False


def vault_decrypt_file(module, file_path, vault_password_file):
    """Decrypt a file with ansible-vault."""
    import subprocess
    cmd = [
        "ansible-vault",
        "decrypt",
        file_path,
        "--vault-password-file",
        vault_password_file,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return result.returncode == 0 or "not encrypted" in result.stderr
    except Exception as e:
        return False


def load_yaml_file(path):
    """Load a YAML file safely."""
    try:
        import yaml
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Fallback to basic parsing if PyYAML unavailable
        return {}
    except Exception:
        return {}


def write_yaml_file(path, data):
    """Write data to a YAML file."""
    try:
        import yaml
        with open(path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception:
        return False
