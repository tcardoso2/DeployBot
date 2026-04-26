from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .apps import find_local_apps


def _build_remote_target(target: str, destination: str, user: str | None) -> str:
    host = f"{user}@{target}" if user else target
    return f"{host}:{destination}"


def deploy_app(
    workspace_dir: Path,
    app_name: str,
    target: str,
    destination: str,
    user: str | None = None,
    dry_run: bool = False,
) -> int:
    apps = {app.name: app for app in find_local_apps(workspace_dir)}
    app = apps.get(app_name)
    if app is None:
        print(f"App '{app_name}' was not found in sibling folders next to {workspace_dir}.")
        return 1

    remote_target = _build_remote_target(target, destination, user)

    if shutil.which("rsync"):
        cmd = ["rsync", "-avz", "--delete", f"{app.path}/", remote_target]
    elif shutil.which("scp"):
        cmd = ["scp", "-r", str(app.path), remote_target]
    else:
        print("Neither rsync nor scp is available on this machine, so deployment cannot run.")
        return 1

    if dry_run:
        print("Dry run deployment command:")
        print(" ".join(cmd))
        return 0

    completed = subprocess.run(cmd, check=False)
    return completed.returncode
