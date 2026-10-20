#!/usr/bin/env python3
"""Deploy Inspector only; additive DNS/proxy integration, no paid-service restarts."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from setup_stripe import env_file, private_write

DOMAIN = "inspector.contentsweep.ai"


def ssh_args(root):
    host = json.loads((root / ".mcp-products/beta-host.json").read_text())["ipv4"]
    return ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-o", "UserKnownHostsFile=" + str(root / ".mcp-products/beta_known_hosts"), "-i", str(root / "ops/secrets/beta_ed25519")], host


def remote(root, script, timeout=60):
    options, host = ssh_args(root)
    result = subprocess.run(["ssh", *options, "root@" + host, "python3 -"], input=script, text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError("Inspector remote operation failed; private diagnostics withheld")
    return result.stdout.strip()


def copy(root, source, target):
    options, host = ssh_args(root)
    result = subprocess.run(["scp", "-q", *options, str(source), "root@" + host + ":" + target], capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError("Inspector artifact transfer failed")


def dns(root):
    settings = env_file(root / "ops/secrets/mcp-products.env")
    token = settings["CLOUDFLARE_API_TOKEN"]
    _, host = ssh_args(root)
    def api(path, body=None):
        request = Request("https://api.cloudflare.com/client/v4/" + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        if not result.get("success"):
            raise RuntimeError("DNS operation failed")
        return result["result"]
    zones = api("zones?" + urlencode({"name": "contentsweep.ai"}))
    if len(zones) != 1:
        raise ValueError("exact owned DNS zone required")
    path = "zones/" + zones[0]["id"] + "/dns_records"
    records = api(path + "?" + urlencode({"name": DOMAIN}))
    if records:
        if len(records) != 1 or records[0]["type"] != "A" or records[0]["content"] != host or records[0]["proxied"]:
            raise ValueError("existing DNS record differs; refusing overwrite")
        record = records[0]
    else:
        record = api(path, {"type": "A", "name": DOMAIN, "content": host, "ttl": 300, "proxied": False, "comment": "Inspector independent service"})
    private_write(root / ".mcp-products/inspector/dns.private.json", json.dumps({"name": DOMAIN, "record_id": record["id"], "host": host}))
    return {"name": DOMAIN, "record_verified": True, "new_paid_resource": False}


def deploy(root, *, activate=False):
    runtime = root / ".mcp-products/inspector"
    manifest = json.loads((runtime / "dist/manifest.json").read_text())
    name = "contentsweep_prodcheck-0.3.0-py3-none-any.whl"
    wheel = runtime / "dist" / name
    sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if manifest["artifacts"].get(name) != sha:
        raise ValueError("reviewed wheel identity mismatch")
    release = sha[:20]
    image = "contentsweep-inspector:" + release
    target = "/opt/contentsweep-inspector/releases/" + release
    env = env_file(runtime / "hosted-live.env")
    if any("SETUP" in key for key in env):
        raise ValueError("setup credentials are forbidden in runtime")
    setup_key = env_file(root / "ops/secrets/mcp-products.env").get("STRIPE_LIVE_SETUP_KEY")
    if setup_key and setup_key in env.values():
        raise ValueError("setup key must remain local")
    env["INSPECTOR_BILLING_ENABLED"] = "true" if activate else "false"
    env["INSPECTOR_RELEASE"] = release
    details = json.loads(remote(root, """import json,subprocess
network=json.loads(subprocess.check_output(['docker','network','inspect','mcp-products-beta_default']))[0]
print(json.dumps({'subnet':network['IPAM']['Config'][0]['Subnet']}))
"""))
    env["INSPECTOR_TRUSTED_PROXY_NETWORK"] = details["subnet"]
    if activate:
        qualification = json.loads((runtime / "qualification/commercial-https.private.json").read_text())
        if not qualification.get("https_reports_passed") or qualification.get("release") != release:
            raise ValueError("matching deployed HTTPS qualification required before activation")
        sandbox = json.loads((runtime / "qualification/sandbox-payment.private.json").read_text())
        restore = json.loads((runtime / "qualification/restore.private.json").read_text())
        provider = json.loads((runtime / "qualification/provider-live.private.json").read_text())
        if not (sandbox.get("actual_sandbox_checkout_paid") and sandbox.get("actual_sandbox_refund_succeeded") and sandbox.get("signed_test_delivery_observed") and sandbox.get("hundred_credit_grant_and_revocation") and restore.get("restore_passed") and provider.get("live_checkout_created_unpaid_and_expired")):
            raise ValueError("payment/refund, signed delivery, restore and live unpaid qualification required")
    private_write(runtime / "deployment.env", "\n".join(key + "=" + value for key, value in env.items()) + "\n")
    remote(root, f"""from pathlib import Path
base=Path('/opt/contentsweep-inspector')
target=Path({target!r})
assert target.is_relative_to(base)
target.mkdir(parents=True,exist_ok=True,mode=0o700)
(base/'config').mkdir(exist_ok=True,mode=0o700)
(base/'data').mkdir(exist_ok=True,mode=0o700)
import os
os.chown(base/'data',10001,10001)
""")
    for source in [wheel, runtime / "dist/contentsweep_prodcheck-0.3.0.tar.gz", runtime / "dist/manifest.json", root / "ops/inspector/Dockerfile", root / "ops/inspector/requirements-hosted.txt"]:
        copy(root, source, target + "/" + source.name)
    copy(root, runtime / "deployment.env", "/opt/contentsweep-inspector/config/live.env")
    script = """import hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
target=Path(TARGET)
base=Path('/opt/contentsweep-inspector')
env=base/'config/live.env';env.chmod(0o600)
assert hashlib.sha256((target/WHEEL).read_bytes()).hexdigest()==EXPECTED
def run(args):
 p=subprocess.run(args,capture_output=True,text=True,check=False,timeout=240)
 if p.returncode:
  (base/'operation.private.log').write_text(p.stdout+'\\n'+p.stderr)
  raise RuntimeError('Owned deployment command failed; inspect private product log')
 return p.stdout.strip()
def preserved():
 names=run(['docker','ps','--format','{{.Names}}']).splitlines()
 out={}
 for name in names:
  if name=='contentsweep-inspector-api':continue
  item=json.loads(run(['docker','inspect',name]))[0]
  out[name]={'id':item['Id'],'started':item['State']['StartedAt'],'restarts':item['RestartCount'],'image':item['Image']}
 return out
before=preserved()
run(['docker','build','-t',IMAGE,str(target)])
exists=subprocess.run(['docker','inspect','contentsweep-inspector-api'],capture_output=True).returncode==0
if exists:
 item=json.loads(run(['docker','inspect','contentsweep-inspector-api']))[0]
 assert item['Config']['Labels'].get('mcp.product')=='production-readiness-inspector'
 run(['docker','stop','contentsweep-inspector-api'])
 run(['docker','rm','contentsweep-inspector-api'])
run(['docker','run','-d','--name','contentsweep-inspector-api','--label','mcp.product=production-readiness-inspector','--restart','unless-stopped','--network','mcp-products-beta_default','--memory','512m','--cpus','0.5','--pids-limit','128','--cap-drop','ALL','--security-opt','no-new-privileges','--read-only','--tmpfs','/tmp:rw,size=32m','-p','127.0.0.1:18183:8080','--env-file',str(env),'-v',str(base/'data')+':/data',IMAGE])
health=None
for _ in range(30):
 try:
  request=urllib.request.Request('http://127.0.0.1:18183/inspector/health',headers={'Host':'inspector.contentsweep.ai'})
  health=json.load(urllib.request.urlopen(request,timeout=3))
  if health.get('ready'):break
 except Exception:time.sleep(1)
assert health and health['release']==RELEASE
caddy=Path('/opt/mcp-products/ops/Caddyfile'); original=caddy.read_text()
marker='# BEGIN contentsweep-inspector'
addition='\\n'+marker+'\\ninspector.contentsweep.ai {\\n    encode zstd gzip\\n    request_body {\\n        max_size 2MB\\n    }\\n    reverse_proxy contentsweep-inspector-api:8080 {\\n        header_up X-Inspector-Client-IP {remote_host}\\n    }\\n}\\n# END contentsweep-inspector\\n'
if marker not in original:
 (base/'caddy-before.private.txt').write_text(original)
 candidate=original+addition
 assert caddy.read_text()==original
 caddy.write_text(candidate)
 try:
  run(['docker','exec','mcp-products-beta-reverse-proxy-1','caddy','validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
  run(['docker','exec','mcp-products-beta-reverse-proxy-1','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
 except Exception:
  caddy.write_text(original)
  raise
else:
 assert addition.strip() in original
after=preserved()
assert before==after
result={'release':RELEASE,'image':IMAGE,'billing_enabled':health['billing_enabled'],'existing_containers_unchanged':True,'caddy_reloaded_without_restart':True,'hosted_health':health,'setup_key_uploaded':False}
(base/'active.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
"""
    # Substitute only validated local literal metadata, never a credential.
    for key, value in {"TARGET": target, "WHEEL": name, "EXPECTED": sha, "IMAGE": image, "RELEASE": release}.items():
        script = script.replace(key, repr(value))
    result = json.loads(remote(root, script, timeout=600))
    private_write(runtime / "deployment.private.json", json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    if not args.apply:
        print(json.dumps({"domain": DOMAIN, "product_directory": "/opt/contentsweep-inspector", "new_paid_resources": False, "restarts_existing_services": False, "activates_billing": args.activate}))
        return 0
    try:
        print(json.dumps({"dns": dns(root), "deployment": deploy(root, activate=args.activate)}, indent=2))
    except Exception as exc:  # noqa: BLE001 - remote/provider diagnostics may contain secrets
        print(json.dumps({"error": "inspector_deployment_failed", "error_class": type(exc).__name__}))
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
