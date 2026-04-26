#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path


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


def package_manifest_for(host: str, linux_user: str, package_name: str) -> dict:
    manifest_path = remote_root() / host / "users" / linux_user / "ROOT_DEPLOYBOT" / package_name / "deploybot-manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def deterministic_port(package_name: str) -> int:
    return 41000 + sum(ord(char) for char in package_name) % 1000


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
    port = deterministic_port(package_name)
    payload = {
        "package_name": package_name,
        "linux_user": linux_user,
        "package_path": f"/home/{linux_user}/ROOT_DEPLOYBOT/{package_name}",
        "port": port,
        "pid": 5000 + len(package_name),
        "runtime": manifest.get("runtime", "unknown"),
    }
    runtime_file.write_text(json.dumps(payload), encoding="utf-8")
    print(f"Started app as {linux_user} on port {port}")
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


def main() -> int:
    action, host, ip, username, password, *extra = sys.argv[1:]
    del ip
    if action == "deploy":
        return deploy(host, username, password, extra[0])
    if action == "list":
        return list_deployments(host, username, password)
    if action == "start":
        return start(host, username, password, extra[0])
    if action == "stop":
        return stop(host, username, password, extra[0])
    if action == "running":
        return running(host, username, password)
    print(f"unsupported action: {action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
