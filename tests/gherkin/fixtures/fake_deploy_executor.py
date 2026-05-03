#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploybot_pkg.startup import materialize_startup_points


def sanitize_linux_username(app_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", app_name.lower()).strip("-_")
    if not normalized:
        normalized = "deploybotapp"
    if not normalized[0].isalpha():
        normalized = f"app-{normalized}"
    return normalized[:32]


def remote_root() -> Path:
    root = Path.cwd()
    override = os.environ.get("DEPLOYBOT_FAKE_REMOTE_ROOT")
    return Path(override).resolve() if override else root / "tests" / "gherkin" / "fixtures" / "remote_servers"


def runtime_root(host: str, linux_user: str) -> Path:
    return remote_root() / host / "users" / linux_user / "ROOT_DEPLOYBOT" / ".deploybot-runtime"


def tunnel_root(host: str, linux_user: str) -> Path:
    return remote_root() / host / "users" / linux_user / "ROOT_DEPLOYBOT" / ".deploybot-tunnels"


def package_manifest_for(host: str, linux_user: str, package_name: str) -> dict:
    manifest_path = remote_root() / host / "users" / linux_user / "ROOT_DEPLOYBOT" / package_name / "deploybot-manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def deterministic_port(package_name: str) -> int:
    return 41000 + sum(ord(char) for char in package_name) % 1000


def normalize_subdomain(subdomain: str) -> tuple[str, str]:
    if "." in subdomain:
        short = subdomain.split(".", 1)[0]
        host = subdomain
    else:
        short = subdomain
        host = f"{subdomain}.ngrok.app"
    return short, f"https://{host}"


def check_auth(username: str, password: str) -> bool:
    return username == "admin" and password == "secret"


def deploy(host: str, username: str, password: str, package_path_text: str) -> int:
    if not check_auth(username, password):
        print("authentication failed")
        return 1

    package_path = Path(package_path_text).resolve()
    manifest = json.loads((package_path / "deploybot-manifest.json").read_text(encoding="utf-8"))
    app_user = sanitize_linux_username(manifest["app_name"])
    remote_package_path = remote_root() / host / "users" / app_user / "ROOT_DEPLOYBOT" / package_path.name
    if remote_package_path.exists():
        shutil.rmtree(remote_package_path)
    remote_package_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_path, remote_package_path)
    (remote_package_path / "INSTALL_LOG.txt").write_text(
        "No extra runtime dependencies required for packaged static files.\n",
        encoding="utf-8",
    )
    (remote_package_path / ".owner").write_text(f"{app_user}:{app_user}\n", encoding="utf-8")
    print(f"Deployed as linux user {app_user}")
    print(f"Remote path: /home/{app_user}/ROOT_DEPLOYBOT/{package_path.name}")
    return 0


def list_deployments(host: str, username: str, password: str) -> int:
    if not check_auth(username, password):
        print("authentication failed", file=sys.stderr)
        return 1

    host_root = remote_root() / host / "users"
    deployments = []
    if host_root.exists():
        for user_dir in sorted(host_root.iterdir()):
            root_dir = user_dir / "ROOT_DEPLOYBOT"
            if not root_dir.exists():
                continue
            for package_dir in sorted(root_dir.iterdir()):
                if not package_dir.is_dir() or package_dir.name.startswith("."):
                    continue
                deployments.append(
                    {
                        "app_name": package_manifest_for(host, user_dir.name, package_dir.name).get("app_name", user_dir.name),
                        "package_name": package_dir.name,
                        "package_path": f"/home/{user_dir.name}/ROOT_DEPLOYBOT/{package_dir.name}",
                        "linux_user": user_dir.name,
                        "app_type": package_manifest_for(host, user_dir.name, package_dir.name).get("app_type", "unknown"),
                        "runtime": package_manifest_for(host, user_dir.name, package_dir.name).get("runtime", "unknown"),
                    }
                )
    print(json.dumps(deployments))
    return 0


def resolve_deployment(host: str, package_name: str) -> tuple[str, Path, dict]:
    host_root = remote_root() / host / "users"
    for user_dir in sorted(host_root.iterdir()):
        package_dir = user_dir / "ROOT_DEPLOYBOT" / package_name
        if package_dir.exists():
            return user_dir.name, package_dir, package_manifest_for(host, user_dir.name, package_name)
    raise FileNotFoundError(package_name)


def start(host: str, username: str, password: str, package_name: str) -> int:
    if not check_auth(username, password):
        print("authentication failed")
        return 1
    linux_user, package_dir, manifest = resolve_deployment(host, package_name)
    runtime_dir = runtime_root(host, linux_user)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = runtime_dir / f"{package_name}.json"
    startup_points = materialize_startup_points(manifest, package_name)
    if not startup_points:
        print(f"Unsupported runtime for start-app: {manifest.get('runtime', 'unknown')}")
        return 1
    primary = next((point for point in startup_points if point.get("role") == "primary"), startup_points[0])
    port = int(primary.get("port") or 0)
    processes = []
    for index, point in enumerate(startup_points, start=1):
        processes.append(
            {
                "name": point.get("name", f"process-{index}"),
                "role": point.get("role", "companion"),
                "command": point.get("command", ""),
                "port": point.get("port"),
                "pid": 5000 + len(package_name) + index,
            }
        )
    payload = {
        "package_name": package_name,
        "linux_user": linux_user,
        "package_path": f"/home/{linux_user}/ROOT_DEPLOYBOT/{package_name}",
        "port": port,
        "pid": processes[0]["pid"],
        "runtime": manifest.get("runtime", "unknown"),
        "processes": processes,
    }
    runtime_file.write_text(json.dumps(payload), encoding="utf-8")
    if port:
        print(f"Started app as {linux_user} on port {port}")
    else:
        print(f"Started app as {linux_user}")
    return 0


def start_custom(host: str, username: str, password: str, package_name: str, custom_command: str) -> int:
    if not check_auth(username, password):
        print("authentication failed")
        return 1
    linux_user, package_dir, _manifest = resolve_deployment(host, package_name)
    runtime_dir = runtime_root(host, linux_user)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_file = runtime_dir / f"{package_name}.json"
    pid = 7000 + len(package_name)
    payload = {
        "package_name": package_name,
        "linux_user": linux_user,
        "package_path": f"/home/{linux_user}/ROOT_DEPLOYBOT/{package_name}",
        "port": 0,
        "pid": pid,
        "runtime": "custom-command",
        "processes": [
            {
                "name": "custom",
                "role": "primary",
                "command": custom_command,
                "port": None,
                "pid": pid,
                "working_directory": str(package_dir),
            }
        ],
    }
    runtime_file.write_text(json.dumps(payload), encoding="utf-8")
    print(f"Started custom command as {linux_user}")
    return 0


def stop(host: str, username: str, password: str, package_name: str) -> int:
    if not check_auth(username, password):
        print("authentication failed")
        return 1
    linux_user, _package_dir, _manifest = resolve_deployment(host, package_name)
    runtime_file = runtime_root(host, linux_user) / f"{package_name}.json"
    runtime_file.unlink(missing_ok=True)
    print(f"Stopped {package_name} as {linux_user}")
    return 0


def running(host: str, username: str, password: str) -> int:
    if not check_auth(username, password):
        print("authentication failed", file=sys.stderr)
        return 1
    host_root = remote_root() / host / "users"
    apps = []
    if host_root.exists():
        for user_dir in sorted(host_root.iterdir()):
            run_dir = user_dir / "ROOT_DEPLOYBOT" / ".deploybot-runtime"
            if not run_dir.exists():
                continue
            for runtime_file in sorted(run_dir.glob("*.json")):
                apps.append(json.loads(runtime_file.read_text(encoding="utf-8")))
    print(json.dumps(apps))
    return 0


def startup_points(host: str, username: str, password: str, package_name: str) -> int:
    if not check_auth(username, password):
        print("authentication failed", file=sys.stderr)
        return 1
    linux_user, package_dir, manifest = resolve_deployment(host, package_name)
    payload = {
        "manifest": manifest,
        "startup_points": materialize_startup_points(manifest, package_name),
        "package_path": f"/home/{linux_user}/ROOT_DEPLOYBOT/{package_name}",
    }
    del package_dir
    print(json.dumps(payload))
    return 0


def services(host: str, username: str, password: str) -> int:
    del host
    if not check_auth(username, password):
        print("authentication failed", file=sys.stderr)
        return 1
    print(json.dumps([{"name": "ngrok", "installed": True}]))
    return 0


def start_tunnel(host: str, username: str, password: str, package_name: str, subdomain: str) -> int:
    if not check_auth(username, password):
        print("authentication failed")
        return 1
    linux_user, _package_dir, _manifest = resolve_deployment(host, package_name)
    runtime_file = runtime_root(host, linux_user) / f"{package_name}.json"
    if not runtime_file.exists():
        print(f"Deployment {package_name} is not running on {host}.")
        return 1
    running_payload = json.loads(runtime_file.read_text(encoding="utf-8"))
    short_subdomain, url = normalize_subdomain(subdomain)
    t_root = tunnel_root(host, linux_user)
    t_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "package_name": package_name,
        "linux_user": linux_user,
        "subdomain": short_subdomain,
        "url": url,
        "port": int(running_payload["port"]),
        "pid": 9000 + len(package_name) + len(short_subdomain),
    }
    (t_root / f"{package_name}-{short_subdomain}.json").write_text(json.dumps(payload), encoding="utf-8")
    print(f"Started tunnel at {url}")
    return 0


def stop_tunnel(host: str, username: str, password: str, package_name: str, subdomain: str) -> int:
    if not check_auth(username, password):
        print("authentication failed")
        return 1
    linux_user, _package_dir, _manifest = resolve_deployment(host, package_name)
    short_subdomain, _url = normalize_subdomain(subdomain)
    tunnel_file = tunnel_root(host, linux_user) / f"{package_name}-{short_subdomain}.json"
    tunnel_file.unlink(missing_ok=True)
    print(f"Stopped tunnel for {package_name} on {short_subdomain}")
    return 0


def list_tunnels(host: str, username: str, password: str) -> int:
    if not check_auth(username, password):
        print("authentication failed", file=sys.stderr)
        return 1
    host_root = remote_root() / host / "users"
    tunnels = []
    if host_root.exists():
        for user_dir in sorted(host_root.iterdir()):
            t_root = user_dir / "ROOT_DEPLOYBOT" / ".deploybot-tunnels"
            if not t_root.exists():
                continue
            for tunnel_file in sorted(t_root.glob("*.json")):
                tunnels.append(json.loads(tunnel_file.read_text(encoding="utf-8")))
    print(json.dumps(tunnels))
    return 0


def main() -> int:
    action, host, ip, username, password, *extra = sys.argv[1:]
    del ip
    if action == "deploy":
        return deploy(host, username, password, extra[0])
    if action == "list":
        return list_deployments(host, username, password)
    if action == "start":
        return start(host, username, password, extra[0])
    if action == "start-custom":
        return start_custom(host, username, password, extra[0], extra[1])
    if action == "stop":
        return stop(host, username, password, extra[0])
    if action == "running":
        return running(host, username, password)
    if action == "startup-points":
        return startup_points(host, username, password, extra[0])
    if action == "services":
        return services(host, username, password)
    if action == "start-tunnel":
        return start_tunnel(host, username, password, extra[0], extra[1])
    if action == "stop-tunnel":
        return stop_tunnel(host, username, password, extra[0], extra[1])
    if action == "list-tunnels":
        return list_tunnels(host, username, password)
    print(f"unsupported action: {action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
