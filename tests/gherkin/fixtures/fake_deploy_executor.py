#!/usr/bin/env python3
from __future__ import annotations

import json
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
    override = None
    for key, value in dict(__import__("os").environ).items():
        if key == "DEPLOYBOT_FAKE_REMOTE_ROOT":
            override = value
            break
    return Path(override).resolve() if override else root / "tests" / "gherkin" / "fixtures" / "remote_servers"


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
                if not package_dir.is_dir():
                    continue
                deployments.append(
                    {
                        "app_name": user_dir.name,
                        "package_name": package_dir.name,
                        "package_path": f"/home/{user_dir.name}/ROOT_DEPLOYBOT/{package_dir.name}",
                        "linux_user": user_dir.name,
                    }
                )
    print(json.dumps(deployments))
    return 0


def main() -> int:
    action, host, ip, username, password, *extra = sys.argv[1:]
    del ip
    if action == "deploy":
        return deploy(host, username, password, extra[0])
    if action == "list":
        return list_deployments(host, username, password)
    print(f"unsupported action: {action}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
