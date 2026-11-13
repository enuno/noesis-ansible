"""Offline validation for the n8n public HTTPS edge.

Non-mutating: no ACME issuance, no firewall change, no service restart. It
renders the role's real templates and runs the REAL `nginx -t` against them in
a throwaway prefix, so a config that cannot load fails here rather than at
deploy time with nginx refusing to start.

Run:  python3 tests/n8n_public_edge/test_offline.py
"""

import ipaddress
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml
from jinja2 import Environment, FileSystemLoader

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROLE = os.path.join(REPO, "roles", "n8n_public_edge")
K8S_ROLE = os.path.join(REPO, "roles", "n8n_k8s")
DEFAULTS = os.path.join(ROLE, "defaults", "main.yml")
TASKS = os.path.join(ROLE, "tasks", "main.yml")
INV = os.path.join(REPO, "inventory", "n8n-k8s", "group_vars", "all.yml")
PLAYBOOK = os.path.join(REPO, "playbooks", "n8n-k8s.yml")

FQDN = "n8n.hashgrid.net"
ORIGIN_IP = "31.97.209.57"

failures = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
        print("  PASS  %s" % name)
    else:
        failures.append("%s %s" % (name, detail))
        print("  FAIL  %s %s" % (name, detail))


def read(path):
    with open(path) as fh:
        return fh.read()


def _bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "yes", "on", "1")


defaults = yaml.safe_load(read(DEFAULTS))
inv = yaml.safe_load(read(INV))
tasks_text = read(TASKS)
tasks = yaml.safe_load(tasks_text)
playbook = read(PLAYBOOK)

env = Environment(loader=FileSystemLoader(os.path.join(ROLE, "templates")))
env.filters["bool"] = _bool


def ctx(**over):
    c = dict(defaults)
    c.update({k: v for k, v in inv.items() if k.startswith("n8n_public_edge_")})
    # defaults/main.yml references other vars in its own values
    c["n8n_public_edge_cert_dir"] = "/etc/letsencrypt/live/%s" % c["n8n_public_edge_fqdn"]
    c["n8n_public_edge_upstream_ip"] = "10.43.34.208"
    c.update(over)
    return c


print("== defaults are restrictive, inventory opts in ==")
check("public edge is OFF by role default",
      defaults["n8n_public_edge_enabled"] is False)
check("inventory enables the public edge",
      inv.get("n8n_public_edge_enabled") is True)
check("inventory sets the public FQDN", inv.get("n8n_public_edge_fqdn") == FQDN)
check("inventory records the origin IP", inv.get("n8n_public_edge_origin_ip") == ORIGIN_IP)
check("role default FQDN is fully qualified", "." in defaults["n8n_public_edge_fqdn"])
check("origin is restricted to Cloudflare by default",
      defaults["n8n_public_edge_restrict_to_cloudflare"] is True)
check("inventory keeps the Cloudflare restriction",
      inv.get("n8n_public_edge_restrict_to_cloudflare") is True)
check("unknown-Host rejection is on by default",
      defaults["n8n_public_edge_reject_unknown_host"] is True)
check("ACME production by default (staging is opt-in)",
      defaults["n8n_public_edge_acme_staging"] is False)
check("DNS-01 propagation allows real propagation time",
      int(defaults["n8n_public_edge_acme_propagation_seconds"]) >= 30,
      defaults["n8n_public_edge_acme_propagation_seconds"])
# The pre-existing CLOUDFLARE_API_KEY is Zone:Read only; Cloudflare refuses it
# on DNS records (API code 10000), so naming it would fail at challenge time.
check("the DNS-01 credential is NOT the Zone:Read-only record",
      defaults["n8n_public_edge_cloudflare_bw_key"] != "CLOUDFLARE_API_KEY")
check("the role refuses that record in its own preflight",
      "n8n_public_edge_cloudflare_bw_key != 'CLOUDFLARE_API_KEY'" in tasks_text)
check("the Bitwarden key follows the N8N_K3S_DEFAULT_* family",
      defaults["n8n_public_edge_cloudflare_bw_key"].startswith("N8N_K3S_DEFAULT_"),
      defaults["n8n_public_edge_cloudflare_bw_key"])
check("approved Bitwarden project is pinned",
      defaults["n8n_public_edge_bitwarden_project_id"] == "72974d0e-81af-4678-bab7-b46000985859")

print("\n== Cloudflare origin allow-list ==")
v4 = defaults["n8n_public_edge_cloudflare_ipv4"]
v6 = defaults["n8n_public_edge_cloudflare_ipv6"]
# Anchored to an INDEPENDENT reference, not to the file under test. Checking
# the rendered config against the same vendored list is self-consistent: it
# stays green as the list shrinks, so a range silently disappearing - which
# would lock part of Cloudflare out of the origin and stop real_ip working
# for it - was invisible. These are Cloudflare's long-standing published
# prefixes and the set size at the recorded etag; if upstream genuinely
# changes, refresh the ranges AND update these constants in the same commit.
EXPECTED_V4_COUNT = 15
EXPECTED_V6_COUNT = 7
MUST_INCLUDE_V4 = ["104.16.0.0/13", "172.64.0.0/13", "173.245.48.0/20",
                   "162.158.0.0/15", "131.0.72.0/22"]
MUST_INCLUDE_V6 = ["2400:cb00::/32", "2606:4700::/32"]
check("ipv4 ranges are present", len(v4) > 0)
check("ipv6 ranges are present", len(v6) > 0)
check("the full ipv4 set is vendored (none silently dropped)",
      len(v4) == EXPECTED_V4_COUNT, "got %d, expected %d" % (len(v4), EXPECTED_V4_COUNT))
check("the full ipv6 set is vendored (none silently dropped)",
      len(v6) == EXPECTED_V6_COUNT, "got %d, expected %d" % (len(v6), EXPECTED_V6_COUNT))
check("known Cloudflare ipv4 prefixes are all present",
      all(c in v4 for c in MUST_INCLUDE_V4),
      str([c for c in MUST_INCLUDE_V4 if c not in v4]))
check("known Cloudflare ipv6 prefixes are all present",
      all(c in v6 for c in MUST_INCLUDE_V6),
      str([c for c in MUST_INCLUDE_V6 if c not in v6]))
check("every vendored range is a valid CIDR",
      all(ipaddress.ip_network(c, strict=True) for c in v4 + v6))
check("ipv4 list holds v4 networks only",
      all(ipaddress.ip_network(c).version == 4 for c in v4))
check("ipv6 list holds v6 networks only",
      all(ipaddress.ip_network(c).version == 6 for c in v6))
check("the ranges' provenance etag is recorded",
      bool(str(defaults.get("n8n_public_edge_cloudflare_ips_etag", "")).strip()))
check("a refresh script exists for the vendored ranges",
      os.path.isfile(os.path.join(REPO, "files", "scripts", "refresh_cloudflare_ips.py")))
check("the role refuses an empty allow-list",
      "the vendored Cloudflare" in tasks_text and "n8n_public_edge_cloudflare_ipv4 | length > 0" in tasks_text)

print("\n== task ordering is safe ==")
names = [t.get("name", "") for t in tasks]


def idx(fragment):
    for i, n in enumerate(names):
        if fragment.lower() in n.lower():
            return i
    return -1


i_cert = idx("Obtain the Let's Encrypt certificate")
i_require_cert = idx("Require the certificate to exist")
i_site = idx("Install the n8n public site")
i_fw_cf = idx("Allow Cloudflare ranges")
i_verify = idx("Verify the edge serves n8n")
for label, i in [("certbot", i_cert), ("cert gate", i_require_cert),
                 ("site", i_site), ("firewall", i_fw_cf), ("verify", i_verify)]:
    check("task present: %s" % label, i >= 0)
# nginx cannot start a TLS server block whose certificate is absent, so writing
# the site before the cert exists would take the whole web server down.
check("the certificate is obtained BEFORE the TLS site is written", i_cert < i_site)
check("a gate asserts the certificate exists before the site is written",
      i_require_cert < i_site)
check("the firewall opens only AFTER the site is in place", i_site < i_fw_cf)
check("verification runs after the firewall is configured", i_fw_cf < i_verify)
check("the default distribution site is removed (duplicate default_server)",
      idx("Remove the distribution default site") >= 0)
check("nginx config is validated before the service is (re)started",
      idx("Validate the full nginx configuration") < idx("Enable and start nginx"))
check("handlers are flushed before the firewall opens",
      idx("Flush nginx reload") < i_fw_cf)
check("the renewal timer is enabled",
      "certbot.timer" in tasks_text)
check("the renewal carries a deploy hook that reloads nginx",
      "--deploy-hook" in tasks_text and "reload nginx" in tasks_text)
check("the Cloudflare credentials file is written 0600",
      "mode: '0600'" in tasks_text)
def flatten(ts):
    out = []
    for t in ts:
        out.append(t)
        for key in ("block", "rescue", "always"):
            if isinstance(t.get(key), list):
                out.extend(flatten(t[key]))
    return out


all_tasks = flatten(tasks)
# Only the tasks that HANDLE the token value. The escrow-presence assert also
# mentions it by name but must stay logged: no_log there would hide the
# message that tells the operator which Bitwarden record to create.
SECRET_TASK_NAMES = {
    "Read the Cloudflare DNS token id from Bitwarden",
    "Fetch the Cloudflare DNS token",
    "Write the certbot Cloudflare credentials file",
}
secret_tasks = [t for t in all_tasks if t.get("name") in SECRET_TASK_NAMES]
check("the secret-bearing tasks were found", len(secret_tasks) == 3,
      str([t.get("name") for t in secret_tasks]))
check("every secret-bearing task is no_log",
      bool(secret_tasks) and all(t.get("no_log") is True for t in secret_tasks),
      str([(t.get("name"), t.get("no_log")) for t in secret_tasks]))
check("playbook runs the edge role gated on its flag",
      "n8n_public_edge" in playbook and "n8n_public_edge_enabled | bool" in playbook)

print("\n== rendered nginx config ==")
site = env.get_template("nginx-site.conf.j2").render(**ctx())
upgrade_map = env.get_template("nginx-upgrade-map.conf.j2").render(**ctx())
check("site renders with no unresolved markers", "{{" not in site)
check("site serves the public FQDN", "server_name %s;" % FQDN in site)
check("port 80 redirects to https", "return 301 https://$host$request_uri;" in site)
check("TLS listens on 443 with http2", "listen 443 ssl;" in site and "http2 on;" in site)
check("certificate path matches the ACME cert-name",
      "/etc/letsencrypt/live/%s/fullchain.pem" % FQDN in site)
check("proxies to the resolved upstream", "proxy_pass http://10.43.34.208:5678;" in site)
# n8n's editor push channel is a websocket upgrade; without these the UI
# connects and then reports itself offline while pages load fine.
check("websocket upgrade headers are set",
      "proxy_set_header Upgrade           $http_upgrade;" in site
      and "$connection_upgrade" in site)
check("the upgrade map is provided in the http context",
      "map $http_upgrade $connection_upgrade" in upgrade_map)
check("forwarded proto is pinned to https, not $scheme",
      "X-Forwarded-Proto https;" in site and "X-Forwarded-Proto $scheme" not in site)
check("buffering is off so the push channel streams",
      "proxy_buffering off;" in site)
check("upload body limit is raised above nginx's 1m default",
      "client_max_body_size %s;" % defaults["n8n_public_edge_client_max_body_size"] in site)
check("long read timeout for long-running executions",
      "proxy_read_timeout %s;" % defaults["n8n_public_edge_proxy_read_timeout"] in site)
check("HSTS is sent", "Strict-Transport-Security" in site)
# n8n answers 200 to ANY Host header, so nginx owns host isolation entirely.
check("a catch-all drops unexpected hostnames", "return 444;" in site)
check("the catch-all is the default_server", "default_server" in site)
check("real client IP is taken from CF-Connecting-IP",
      "real_ip_header CF-Connecting-IP;" in site)
check("EVERY vendored Cloudflare range is trusted for real_ip",
      all("set_real_ip_from %s;" % c in site for c in v4 + v6))
check("no range outside the vendored lists is trusted",
      len(re.findall(r"set_real_ip_from ", site)) == len(v4) + len(v6))

print("\n== rendered config loads in REAL nginx ==")
nginx_bin = shutil.which("nginx") or "/usr/sbin/nginx"
if not os.path.exists(nginx_bin):
    check("nginx binary available for -t", False, "nginx not installed")
else:
    tmp = tempfile.mkdtemp(prefix="n8n-edge-nginx-")
    try:
        certdir = os.path.join(tmp, "live", FQDN)
        os.makedirs(certdir)
        # Throwaway self-signed pair ONLY so nginx can load a TLS block. This
        # never touches /etc/letsencrypt and is not an ACME operation.
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", os.path.join(certdir, "privkey.pem"),
             "-out", os.path.join(certdir, "fullchain.pem"),
             "-days", "1", "-subj", "/CN=%s" % FQDN],
            check=True, capture_output=True)
        site_tmp = env.get_template("nginx-site.conf.j2").render(
            **ctx(n8n_public_edge_cert_dir=certdir))
        os.makedirs(os.path.join(tmp, "conf.d"))
        with open(os.path.join(tmp, "conf.d", "upgrade-map.conf"), "w") as fh:
            fh.write(upgrade_map)
        with open(os.path.join(tmp, "site.conf"), "w") as fh:
            fh.write(site_tmp)
        for d in ("logs", "body"):
            os.makedirs(os.path.join(tmp, d), exist_ok=True)

        def nginx_t(include_map):
            conf = os.path.join(tmp, "nginx.conf")
            with open(conf, "w") as fh:
                fh.write(
                    "worker_processes 1;\n"
                    "error_log %s/logs/error.log;\n"
                    "pid %s/nginx.pid;\n"
                    "events { worker_connections 64; }\n"
                    "http {\n"
                    "  client_body_temp_path %s/body;\n"
                    "  access_log off;\n"
                    "%s"
                    "  include %s/site.conf;\n"
                    "}\n" % (
                        tmp, tmp, tmp,
                        ("  include %s/conf.d/*.conf;\n" % tmp) if include_map else "",
                        tmp))
            # `nginx -t` opens the listening sockets, so testing a config
            # that binds 80/443 needs privilege. Prefer testing the EXACT
            # rendered config under sudo; fall back to a port-shifted copy so
            # the suite still validates syntax without root.
            cmd = [nginx_bin, "-t", "-c", conf, "-p", tmp]
            if shutil.which("sudo"):
                r = subprocess.run(["sudo", "-n"] + cmd, capture_output=True, text=True)
                if "sudo:" not in r.stderr:
                    return r
            shifted = conf + ".unpriv"
            with open(conf) as fh:
                body = fh.read()
            with open(shifted, "w") as fh:
                fh.write(body.replace("%s/site.conf" % tmp, "%s/site.unpriv.conf" % tmp))
            with open(os.path.join(tmp, "site.conf")) as fh:
                sc = fh.read()
            sc = sc.replace("listen 80", "listen 8080").replace("listen [::]:80", "listen [::]:8080")
            sc = sc.replace("listen 443", "listen 8443").replace("listen [::]:443", "listen [::]:8443")
            with open(os.path.join(tmp, "site.unpriv.conf"), "w") as fh:
                fh.write(sc)
            return subprocess.run([nginx_bin, "-t", "-c", shifted, "-p", tmp],
                                  capture_output=True, text=True)

        ok = nginx_t(include_map=True)
        check("nginx -t accepts the rendered config", ok.returncode == 0,
              ok.stderr.strip()[-300:])
        # Negative control: the $connection_upgrade map is load-bearing. Drop it
        # and nginx must refuse, which proves the check is measuring something
        # and that shipping the site without the map would break the server.
        bad = nginx_t(include_map=False)
        check("nginx -t REJECTS the config without the upgrade map",
              bad.returncode != 0 and "connection_upgrade" in bad.stderr,
              bad.stderr.strip()[-200:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print("\n== n8n canonical hostname wiring (n8n_k8s role) ==")
k8s_defaults = yaml.safe_load(read(os.path.join(K8S_ROLE, "defaults", "main.yml")))
k8s_tasks = read(os.path.join(K8S_ROLE, "tasks", "main.yml"))
values_tpl = read(os.path.join(K8S_ROLE, "templates", "values.yml.j2"))
check("a canonical hostname variable exists",
      "n8n_k8s_canonical_hostname" in k8s_defaults)
check("its default is fully qualified (tailnet FQDN)",
      "n8n_k8s_tailnet_domain" in str(k8s_defaults["n8n_k8s_canonical_hostname"]))
check("inventory makes the PUBLIC name canonical",
      inv.get("n8n_k8s_canonical_hostname") == FQDN)
check("the role asserts the canonical name is fully qualified",
      "'.' in n8n_k8s_canonical_hostname" in k8s_tasks)
# The chart derives both URLs from the first ingress host - the SHORT tailnet
# name - which rendered the unresolvable `https://n8n`. Setting them explicitly
# is the fix; losing either override reintroduces the bug.
check("webhook.url is set explicitly from the canonical name",
      "webhook:" in values_tpl
      and "url: \"https://{{ n8n_k8s_canonical_hostname }}\"" in values_tpl)
check("editor.url is set explicitly from the canonical name",
      "editor:" in values_tpl
      and values_tpl.count("url: \"https://{{ n8n_k8s_canonical_hostname }}\"") == 2)
check("the ingress host stays the SHORT name the Tailscale operator needs",
      "host: \"{{ n8n_k8s_hostname }}\"" in values_tpl)
# These two keys were set in the Secret and silently ignored by the chart, so
# the pod ran `https://n8n`. Re-adding them would look like a fix and do nothing.
# Strip comments first: the role documents WHY those keys were removed and
# names them, so a raw substring search matches its own explanation.
k8s_tasks_code = "\n".join(l for l in k8s_tasks.splitlines()
                           if not l.lstrip().startswith("#"))
check("the dead N8N_EDITOR_BASE_URL Secret key is gone",
      "N8N_EDITOR_BASE_URL" not in k8s_tasks_code)
check("the dead N8N_WEBHOOK_URL Secret key is gone",
      "N8N_WEBHOOK_URL" not in k8s_tasks_code)
check("N8N_HOST is driven by the canonical name",
      "N8N_HOST: \"{{ n8n_k8s_canonical_hostname }}\"" in k8s_tasks)
check("proxy hops are configurable and default to unset",
      k8s_defaults["n8n_k8s_proxy_hops"] == 0)
check("inventory sets 2 hops (Cloudflare edge, then nginx)",
      inv.get("n8n_k8s_proxy_hops") == 2)
check("proxy hops render only when above zero",
      "n8n_k8s_proxy_hops | int > 0" in values_tpl)

print("\n== summary ==")
print("passed=%d failed=%d" % (passes, len(failures)))
if failures:
    for f in failures:
        print(" - %s" % f)
    sys.exit(1)
print("OK")
sys.exit(0)
