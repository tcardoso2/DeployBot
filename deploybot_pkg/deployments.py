from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .packages import read_package_manifest, resolve_package
from .remote import prompt_password, prompt_username, resolve_device, run_scp_with_password, run_ssh_with_password, shell_quote


@dataclass(frozen=True)
class RemoteDeployment:
    app_name: str
    package_name: str
    package_path: str
    linux_user: str
    app_type: str = "unknown"
    runtime: str = "unknown"


@dataclass(frozen=True)
class RunningApp:
    package_name: str
    linux_user: str
    package_path: str
    port: int
    pid: int


@dataclass(frozen=True)
class RemoteService:
    name: str
    installed: bool


@dataclass(frozen=True)
class TunnelInfo:
    package_name: str
    linux_user: str
    subdomain: str
    url: str
    port: int
    pid: int


def _sanitize_linux_username(app_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", app_name.lower())
    normalized = normalized.strip("-_")
    if not normalized:
        normalized = "deploybotapp"
    if not normalized[0].isalpha():
        normalized = f"app-{normalized}"
    return normalized[:32]


def _fake_deploy_executor() -> str | None:
    return os.environ.get("DEPLOYBOT_DEPLOY_EXECUTOR")


def _run_fake_deploy(action: str, device, username: str, password: str, extra: list[str]) -> int | str:
    executor = _fake_deploy_executor()
    if not executor:
        return -1
    import subprocess

    completed = subprocess.run(
        [executor, action, device.host, device.ip, username, password, *extra],
        text=True,
        capture_output=True,
        check=False,
    )
    if action in {"deploy", "start", "stop", "start-tunnel", "stop-tunnel"} and completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if action in {"deploy", "start", "stop", "start-tunnel", "stop-tunnel"}:
        return completed.returncode
    if completed.returncode != 0:
        return completed.returncode
    return completed.stdout


def _remote_runtime_dir(app_user: str) -> str:
    return f"/home/{app_user}/ROOT_DEPLOYBOT/.deploybot-runtime"


def _remote_runtime_file(app_user: str, package_name: str) -> str:
    return f"{_remote_runtime_dir(app_user)}/{package_name}.json"


def _remote_tunnel_dir(app_user: str) -> str:
    return f"/home/{app_user}/ROOT_DEPLOYBOT/.deploybot-tunnels"


def _remote_tunnel_file(app_user: str, package_name: str, subdomain: str) -> str:
    safe_subdomain = re.sub(r"[^a-zA-Z0-9_-]+", "-", subdomain)
    return f"{_remote_tunnel_dir(app_user)}/{package_name}-{safe_subdomain}.json"


def _remote_setup_script(app_user: str, package_name: str, manifest: dict) -> str:
    app_root = f"/home/{app_user}/ROOT_DEPLOYBOT"
    package_dir = f"{app_root}/{package_name}"
    return f"""
set -eu
SUDO_PASS={shell_quote(os.environ.get("DEPLOYBOT_SUDO_PASSWORD", ""))}
APP_USER={shell_quote(app_user)}
APP_ROOT={shell_quote(app_root)}
PACKAGE_DIR={shell_quote(package_dir)}
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  printf '%s\n' "$SUDO_PASS" | sudo -S useradd -m -s /bin/bash "$APP_USER"
fi
printf '%s\n' "$SUDO_PASS" | sudo -S mkdir -p "$APP_ROOT"
printf '%s\n' "$SUDO_PASS" | sudo -S rm -rf "$PACKAGE_DIR"
printf '%s\n' "$SUDO_PASS" | sudo -S chown -R "$APP_USER:$APP_USER" "$APP_ROOT"
printf '%s\n' "$SUDO_PASS" | sudo -S chmod 750 "$APP_ROOT"
"""


def _remote_post_copy_script(app_user: str, package_name: str, manifest: dict) -> str:
    package_dir = f"/home/{app_user}/ROOT_DEPLOYBOT/{package_name}"
    upload_dir = f"/tmp/{package_name}"
    install_steps = []
    install_steps.append(f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S mkdir -p {shell_quote(package_dir)}")
    install_steps.append(
        f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S cp -R {shell_quote(upload_dir)}/. {shell_quote(package_dir)}/"
    )
    dependency_note = "No extra runtime dependencies required for packaged static files."
    if manifest.get("runtime") == "python-files":
        dependency_note = "Python runtime expected on remote host."
        install_steps.append(
            f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u {shell_quote(app_user)} sh -lc 'cd {shell_quote(package_dir)} && if [ -f requirements.txt ]; then python3 -m pip install --user -r requirements.txt; fi'"
        )
    install_steps.append(
        f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S sh -lc 'printf %s {shell_quote(dependency_note)} > {shell_quote(package_dir)}/INSTALL_LOG.txt'"
    )
    install_steps.append(
        f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S chown -R {shell_quote(app_user)}:{shell_quote(app_user)} {shell_quote(package_dir)}"
    )
    install_steps.append(
        f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S chmod -R u=rwX,g=rX,o= {shell_quote(package_dir)}"
    )
    install_steps.append(f"rm -rf {shell_quote(upload_dir)}")
    return "set -eu\n" + f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n" + "\n".join(install_steps) + "\n"


def deploy_package(workspace_dir: Path, server_number: int, package_number: int) -> int:
    device = resolve_device(workspace_dir, server_number)
    if device is None:
        print(f"Server number {server_number} was not found.")
        return 1

    package = resolve_package(workspace_dir, package_number)
    if package is None:
        print(f"Package number {package_number} was not found.")
        return 1

    try:
        manifest = read_package_manifest(package)
    except RuntimeError as exc:
        print(str(exc))
        return 1

    app_user = _sanitize_linux_username(str(manifest["app_name"]))
    username = prompt_username()
    password = prompt_password()
    os.environ.setdefault("DEPLOYBOT_SUDO_PASSWORD", password)

    print(f"Deploying {package.name} to {device.host} ({device.ip})...", flush=True)

    fake_result = _run_fake_deploy("deploy", device, username, password, [str(package.path)])
    if fake_result != -1:
        return int(fake_result)

    preflight = run_ssh_with_password(
        device,
        username,
        password,
        _remote_setup_script(app_user, package.name, manifest),
        capture_output=True,
    )
    if preflight.returncode != 0:
        print(preflight.stdout or "", end="")
        print(preflight.stderr or "", end="")
        return preflight.returncode

    upload_target = f"/tmp/{package.name}"
    cleanup = run_ssh_with_password(
        device,
        username,
        password,
        f"rm -rf {shell_quote(upload_target)}",
        capture_output=True,
    )
    if cleanup.returncode != 0:
        print(cleanup.stdout or "", end="")
        print(cleanup.stderr or "", end="")
        return cleanup.returncode

    scp_result = run_scp_with_password(device, username, password, package.path, upload_target)
    if scp_result.returncode != 0:
        print(scp_result.stdout or "", end="")
        print(scp_result.stderr or "", end="")
        return scp_result.returncode

    post_copy = run_ssh_with_password(
        device,
        username,
        password,
        _remote_post_copy_script(app_user, package.name, manifest),
        capture_output=True,
    )
    if post_copy.returncode != 0:
        print(post_copy.stdout or "", end="")
        print(post_copy.stderr or "", end="")
        return post_copy.returncode

    print(f"Deployed as linux user {app_user}")
    print(f"Remote path: /home/{app_user}/ROOT_DEPLOYBOT/{package.name}")
    return 0


def _parse_fake_deployments(payload: str) -> list[RemoteDeployment]:
    rows = json.loads(payload or "[]")
    return [RemoteDeployment(**row) for row in rows]


def _parse_fake_running_apps(payload: str) -> list[RunningApp]:
    rows = json.loads(payload or "[]")
    running_apps: list[RunningApp] = []
    for row in rows:
        running_apps.append(
            RunningApp(
                package_name=str(row.get("package_name", "")),
                linux_user=str(row.get("linux_user", "")),
                package_path=str(row.get("package_path", "")),
                port=int(row.get("port", 0)),
                pid=int(row.get("pid", 0)),
            )
        )
    return running_apps


def _parse_fake_services(payload: str) -> list[RemoteService]:
    rows = json.loads(payload or "[]")
    return [RemoteService(name=str(row.get("name", "")), installed=bool(row.get("installed", False))) for row in rows]


def _parse_fake_tunnels(payload: str) -> list[TunnelInfo]:
    rows = json.loads(payload or "[]")
    return [
        TunnelInfo(
            package_name=str(row.get("package_name", "")),
            linux_user=str(row.get("linux_user", "")),
            subdomain=str(row.get("subdomain", "")),
            url=str(row.get("url", "")),
            port=int(row.get("port", 0)),
            pid=int(row.get("pid", 0)),
        )
        for row in rows
    ]


def _prompt_remote_credentials() -> tuple[str, str]:
    username = prompt_username()
    password = prompt_password()
    os.environ.setdefault("DEPLOYBOT_SUDO_PASSWORD", password)
    return username, password


def _remote_list_command() -> str:
    return (
        "set -eu\n"
        f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S "
        "find /home -mindepth 3 -maxdepth 3 -type d -path '/home/*/ROOT_DEPLOYBOT/*' -print\n"
    )


def _load_remote_manifest_command(path: str) -> str:
    manifest_path = f"{path}/deploybot-manifest.json"
    return (
        "set -eu\n"
        f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
        f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S cat {shell_quote(manifest_path)}\n"
    )


def _collect_remote_deployments(device, username: str, password: str) -> tuple[int, list[RemoteDeployment] | None]:
    fake_result = _run_fake_deploy("list", device, username, password, [])
    if fake_result != -1:
        if not isinstance(fake_result, str):
            return int(fake_result), None
        return 0, _parse_fake_deployments(fake_result)

    completed = run_ssh_with_password(device, username, password, _remote_list_command(), capture_output=True)
    if completed.returncode != 0:
        print(completed.stdout or "", end="")
        print(completed.stderr or "", end="")
        return completed.returncode, None

    deployments: list[RemoteDeployment] = []
    for line in completed.stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        parts = Path(path).parts
        if len(parts) < 5:
            continue
        linux_user = parts[2]
        package_name = parts[-1]
        manifest_completed = run_ssh_with_password(
            device,
            username,
            password,
            _load_remote_manifest_command(path),
            capture_output=True,
        )
        app_name = linux_user
        app_type = "unknown"
        runtime = "unknown"
        if manifest_completed.returncode == 0 and (manifest_completed.stdout or "").strip():
            try:
                manifest = json.loads(manifest_completed.stdout)
                app_name = str(manifest.get("app_name", app_name))
                app_type = str(manifest.get("app_type", app_type))
                runtime = str(manifest.get("runtime", runtime))
            except json.JSONDecodeError:
                pass
        deployments.append(
            RemoteDeployment(
                app_name=app_name,
                package_name=package_name,
                package_path=path,
                linux_user=linux_user,
                app_type=app_type,
                runtime=runtime,
            )
        )
    return 0, deployments


def list_remote_deployments(workspace_dir: Path, server_number: int) -> tuple[int, list[RemoteDeployment] | None]:
    device = resolve_device(workspace_dir, server_number)
    if device is None:
        print(f"Server number {server_number} was not found.")
        return 1, None

    username, password = _prompt_remote_credentials()
    return _collect_remote_deployments(device, username, password)


def _resolve_remote_deployment(workspace_dir: Path, server_number: int, deployment_number: int) -> tuple[int, object | None, RemoteDeployment | None, str | None, str | None]:
    device = resolve_device(workspace_dir, server_number)
    if device is None:
        print(f"Server number {server_number} was not found.")
        return 1, None, None, None, None
    username, password = _prompt_remote_credentials()
    code, deployments = _collect_remote_deployments(device, username, password)
    if code != 0 or deployments is None:
        return code, device, None, username, password
    if deployment_number < 1 or deployment_number > len(deployments):
        print(f"Deployment number {deployment_number} was not found on {device.host} ({device.ip}).")
        return 1, device, None, username, password
    return 0, device, deployments[deployment_number - 1], username, password


def _start_command_for_deployment(deployment: RemoteDeployment) -> tuple[str, int]:
    if deployment.runtime == "static-files":
        port = 41000 + sum(ord(char) for char in deployment.package_name) % 1000
        package_dir = deployment.package_path
        runtime_dir = _remote_runtime_dir(deployment.linux_user)
        runtime_file = _remote_runtime_file(deployment.linux_user, deployment.package_name)
        command = (
            "set -eu\n"
            f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
            f"RUNTIME_DIR={shell_quote(runtime_dir)}\n"
            f"RUNTIME_FILE={shell_quote(runtime_file)}\n"
            f"PACKAGE_DIR={shell_quote(package_dir)}\n"
            f"PORT={port}\n"
            f"APP_USER={shell_quote(deployment.linux_user)}\n"
            "printf '%s\\n' \"$SUDO_PASS\" | sudo -S mkdir -p \"$RUNTIME_DIR\"\n"
            "printf '%s\\n' \"$SUDO_PASS\" | sudo -S chown -R \"$APP_USER:$APP_USER\" \"$RUNTIME_DIR\"\n"
            "if [ -f \"$RUNTIME_FILE\" ]; then\n"
            "  OLD_PID=$(printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(\"pid\", \"\"))' \"$RUNTIME_FILE\" 2>/dev/null || true)\n"
            "  if [ -n \"$OLD_PID\" ] && kill -0 \"$OLD_PID\" >/dev/null 2>&1; then\n"
            "    printf 'App already running on port %s\\n' \"$PORT\"\n"
            "    exit 0\n"
            "  fi\n"
            "fi\n"
            "printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" sh -lc "
            + shell_quote(
                f"cd {package_dir} && nohup python3 -m http.server {port} --bind 0.0.0.0 >/tmp/{deployment.package_name}.log 2>&1 & echo $! >/tmp/{deployment.package_name}.pid"
            )
            + "\n"
            f"PID=$(printf '%s\\n' \"$SUDO_PASS\" | sudo -S cat /tmp/{deployment.package_name}.pid)\n"
            f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S rm -f /tmp/{deployment.package_name}.pid\n"
            "printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" python3 - <<'PY' \"$RUNTIME_FILE\" \"$PACKAGE_DIR\" \"$APP_USER\" \"$PORT\" \"$PID\"\n"
            "import json, sys\n"
            "from pathlib import Path\n"
            "payload = {\n"
            f"  'package_name': {deployment.package_name!r},\n"
            "  'package_path': sys.argv[2],\n"
            "  'linux_user': sys.argv[3],\n"
            "  'port': int(sys.argv[4]),\n"
            "  'pid': int(sys.argv[5]),\n"
            "}\n"
            "Path(sys.argv[1]).write_text(json.dumps(payload), encoding='utf-8')\n"
            "PY\n"
            "printf 'Started app as %s on port %s\\n' \"$APP_USER\" \"$PORT\"\n"
        )
        return command, port
    raise RuntimeError(f"Unsupported runtime for start-app: {deployment.runtime}")


def start_remote_app(workspace_dir: Path, server_number: int, deployment_number: int) -> int:
    code, device, deployment, username, password = _resolve_remote_deployment(workspace_dir, server_number, deployment_number)
    if code != 0 or device is None or deployment is None or username is None or password is None:
        return code
    print(f"Starting {deployment.package_name} on {device.host} ({device.ip})...", flush=True)
    fake_result = _run_fake_deploy("start", device, username, password, [deployment.package_name])
    if fake_result != -1:
        return int(fake_result)
    try:
        command, _port = _start_command_for_deployment(deployment)
    except RuntimeError as exc:
        print(str(exc))
        return 1
    completed = run_ssh_with_password(device, username, password, command, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    return completed.returncode


def _stop_command_for_deployment(deployment: RemoteDeployment) -> str:
    runtime_file = _remote_runtime_file(deployment.linux_user, deployment.package_name)
    return (
        "set -eu\n"
        f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
        f"RUNTIME_FILE={shell_quote(runtime_file)}\n"
        f"APP_USER={shell_quote(deployment.linux_user)}\n"
        "if [ ! -f \"$RUNTIME_FILE\" ]; then\n"
        f"  printf 'App {deployment.package_name} is not running\\n'\n"
        "  exit 0\n"
        "fi\n"
        "PID=$(printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"pid\"])' \"$RUNTIME_FILE\")\n"
        "if kill -0 \"$PID\" >/dev/null 2>&1; then\n"
        "  printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" sh -lc "
        + shell_quote("kill \"$PID\"")
        + "\n"
        "fi\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" rm -f \"$RUNTIME_FILE\"\n"
        f"printf 'Stopped {deployment.package_name} as %s\\n' \"$APP_USER\"\n"
    )


def stop_remote_app(workspace_dir: Path, server_number: int, deployment_number: int) -> int:
    code, device, deployment, username, password = _resolve_remote_deployment(workspace_dir, server_number, deployment_number)
    if code != 0 or device is None or deployment is None or username is None or password is None:
        return code
    print(f"Stopping {deployment.package_name} on {device.host} ({device.ip})...", flush=True)
    fake_result = _run_fake_deploy("stop", device, username, password, [deployment.package_name])
    if fake_result != -1:
        return int(fake_result)
    completed = run_ssh_with_password(device, username, password, _stop_command_for_deployment(deployment), capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    return completed.returncode


def _collect_running_apps(device, username: str, password: str) -> tuple[int, list[RunningApp] | None]:
    fake_result = _run_fake_deploy("running", device, username, password, [])
    if fake_result != -1:
        if not isinstance(fake_result, str):
            return int(fake_result), None
        return 0, _parse_fake_running_apps(fake_result)
    command = (
        "set -eu\n"
        f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S "
        "find /home -mindepth 4 -maxdepth 4 -type f -path '/home/*/ROOT_DEPLOYBOT/.deploybot-runtime/*.json' -print\n"
    )
    completed = run_ssh_with_password(device, username, password, command, capture_output=True)
    if completed.returncode != 0:
        print(completed.stdout or "", end="")
        print(completed.stderr or "", end="")
        return completed.returncode, None
    running_apps: list[RunningApp] = []
    for runtime_file in completed.stdout.splitlines():
        runtime_file = runtime_file.strip()
        if not runtime_file:
            continue
        cat_completed = run_ssh_with_password(
            device,
            username,
            password,
            (
                "set -eu\n"
                f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
                f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S cat {shell_quote(runtime_file)}\n"
            ),
            capture_output=True,
        )
        if cat_completed.returncode != 0 or not (cat_completed.stdout or "").strip():
            continue
        try:
            payload = json.loads(cat_completed.stdout)
        except json.JSONDecodeError:
            continue
        running_apps.append(
            RunningApp(
                package_name=str(payload.get("package_name", "")),
                linux_user=str(payload.get("linux_user", "")),
                package_path=str(payload.get("package_path", "")),
                port=int(payload.get("port", 0)),
                pid=int(payload.get("pid", 0)),
            )
        )
    return 0, running_apps


def _collect_remote_services(device, username: str, password: str) -> tuple[int, list[RemoteService] | None]:
    fake_result = _run_fake_deploy("services", device, username, password, [])
    if fake_result != -1:
        if not isinstance(fake_result, str):
            return int(fake_result), None
        return 0, _parse_fake_services(fake_result)

    command = "if command -v ngrok >/dev/null 2>&1; then printf 'installed\\n'; else printf 'missing\\n'; fi\n"
    completed = run_ssh_with_password(device, username, password, command, capture_output=True)
    if completed.returncode != 0:
        print(completed.stdout or "", end="")
        print(completed.stderr or "", end="")
        return completed.returncode, None
    installed = (completed.stdout or "").strip() == "installed"
    return 0, [RemoteService(name="ngrok", installed=installed)]


def list_remote_services(workspace_dir: Path, server_number: int) -> tuple[int, object | None, list[RemoteService] | None]:
    device = resolve_device(workspace_dir, server_number)
    if device is None:
        print(f"Server number {server_number} was not found.")
        return 1, None, None
    username, password = _prompt_remote_credentials()
    code, services = _collect_remote_services(device, username, password)
    return code, device, services


def _collect_remote_tunnels(device, username: str, password: str) -> tuple[int, list[TunnelInfo] | None]:
    fake_result = _run_fake_deploy("list-tunnels", device, username, password, [])
    if fake_result != -1:
        if not isinstance(fake_result, str):
            return int(fake_result), None
        return 0, _parse_fake_tunnels(fake_result)
    command = (
        "set -eu\n"
        f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S "
        "find /home -mindepth 5 -maxdepth 5 -type f -path '/home/*/ROOT_DEPLOYBOT/.deploybot-tunnels/*.json' -print\n"
    )
    completed = run_ssh_with_password(device, username, password, command, capture_output=True)
    if completed.returncode != 0:
        print(completed.stdout or "", end="")
        print(completed.stderr or "", end="")
        return completed.returncode, None
    tunnels: list[TunnelInfo] = []
    for tunnel_file in completed.stdout.splitlines():
        tunnel_file = tunnel_file.strip()
        if not tunnel_file:
            continue
        cat_completed = run_ssh_with_password(
            device,
            username,
            password,
            (
                "set -eu\n"
                f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
                f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S cat {shell_quote(tunnel_file)}\n"
            ),
            capture_output=True,
        )
        if cat_completed.returncode != 0 or not (cat_completed.stdout or "").strip():
            continue
        try:
            payload = json.loads(cat_completed.stdout)
        except json.JSONDecodeError:
            continue
        tunnels.append(
            TunnelInfo(
                package_name=str(payload.get("package_name", "")),
                linux_user=str(payload.get("linux_user", "")),
                subdomain=str(payload.get("subdomain", "")),
                url=str(payload.get("url", "")),
                port=int(payload.get("port", 0)),
                pid=int(payload.get("pid", 0)),
            )
        )
    return 0, tunnels


def list_running_apps(workspace_dir: Path, server_number: int) -> tuple[int, object | None, list[RunningApp] | None]:
    device = resolve_device(workspace_dir, server_number)
    if device is None:
        print(f"Server number {server_number} was not found.")
        return 1, None, None
    username, password = _prompt_remote_credentials()
    code, running_apps = _collect_running_apps(device, username, password)
    return code, device, running_apps


def _normalize_subdomain(subdomain: str) -> tuple[str, str]:
    if "." in subdomain:
        fqdn = subdomain
        short = subdomain.split(".", 1)[0]
    else:
        short = subdomain
        fqdn = f"{subdomain}.ngrok.app"
    return short, f"https://{fqdn}"


def _resolve_running_deployment(workspace_dir: Path, server_number: int, deployment_number: int) -> tuple[int, object | None, RemoteDeployment | None, RunningApp | None, str | None, str | None]:
    code, device, deployment, username, password = _resolve_remote_deployment(workspace_dir, server_number, deployment_number)
    if code != 0 or device is None or deployment is None or username is None or password is None:
        return code, device, deployment, None, username, password
    run_code, running_apps = _collect_running_apps(device, username, password)
    if run_code != 0 or running_apps is None:
        return run_code, device, deployment, None, username, password
    for running_app in running_apps:
        if running_app.package_name == deployment.package_name and running_app.linux_user == deployment.linux_user:
            return 0, device, deployment, running_app, username, password
    print(f"Deployment {deployment.package_name} is not running on {device.host} ({device.ip}).")
    return 1, device, deployment, None, username, password


def _start_tunnel_command(deployment: RemoteDeployment, running_app: RunningApp, subdomain: str) -> tuple[str, str]:
    short_subdomain, url = _normalize_subdomain(subdomain)
    tunnel_dir = _remote_tunnel_dir(deployment.linux_user)
    tunnel_file = _remote_tunnel_file(deployment.linux_user, deployment.package_name, short_subdomain)
    command = (
        "set -eu\n"
        f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
        f"TUNNEL_DIR={shell_quote(tunnel_dir)}\n"
        f"TUNNEL_FILE={shell_quote(tunnel_file)}\n"
        f"APP_USER={shell_quote(deployment.linux_user)}\n"
        f"URL={shell_quote(url)}\n"
        f"PORT={running_app.port}\n"
        "if ! command -v ngrok >/dev/null 2>&1; then\n"
        "  printf 'ngrok is not installed\\n'\n"
        "  exit 1\n"
        "fi\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S mkdir -p \"$TUNNEL_DIR\"\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S chown -R \"$APP_USER:$APP_USER\" \"$TUNNEL_DIR\"\n"
        "if [ -f \"$TUNNEL_FILE\" ]; then\n"
        "  OLD_PID=$(printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(\"pid\", \"\"))' \"$TUNNEL_FILE\" 2>/dev/null || true)\n"
        "  if [ -n \"$OLD_PID\" ] && kill -0 \"$OLD_PID\" >/dev/null 2>&1; then\n"
        "    printf 'Tunnel already running at %s\\n' \"$URL\"\n"
        "    exit 0\n"
        "  fi\n"
        "fi\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" sh -lc "
        + shell_quote(
            f"nohup ngrok http {running_app.port} --url {url} >/tmp/{deployment.package_name}-{short_subdomain}-ngrok.log 2>&1 & echo $! >/tmp/{deployment.package_name}-{short_subdomain}-ngrok.pid"
        )
        + "\n"
        f"PID=$(printf '%s\\n' \"$SUDO_PASS\" | sudo -S cat /tmp/{deployment.package_name}-{short_subdomain}-ngrok.pid)\n"
        f"printf '%s\\n' \"$SUDO_PASS\" | sudo -S rm -f /tmp/{deployment.package_name}-{short_subdomain}-ngrok.pid\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" python3 - <<'PY' \"$TUNNEL_FILE\" \"$URL\" \"$PORT\" \"$PID\"\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        "payload = {\n"
        f"  'package_name': {deployment.package_name!r},\n"
        f"  'linux_user': {deployment.linux_user!r},\n"
        f"  'subdomain': {short_subdomain!r},\n"
        "  'url': sys.argv[2],\n"
        "  'port': int(sys.argv[3]),\n"
        "  'pid': int(sys.argv[4]),\n"
        "}\n"
        "Path(sys.argv[1]).write_text(json.dumps(payload), encoding='utf-8')\n"
        "PY\n"
        "printf 'Started tunnel at %s\\n' \"$URL\"\n"
    )
    return command, url


def start_tunnel(workspace_dir: Path, server_number: int, deployment_number: int, subdomain: str) -> int:
    code, device, deployment, running_app, username, password = _resolve_running_deployment(workspace_dir, server_number, deployment_number)
    if code != 0 or device is None or deployment is None or running_app is None or username is None or password is None:
        return code
    print(f"Starting tunnel for {deployment.package_name} on {device.host} ({device.ip})...", flush=True)
    fake_result = _run_fake_deploy("start-tunnel", device, username, password, [deployment.package_name, subdomain])
    if fake_result != -1:
        return int(fake_result)
    command, _url = _start_tunnel_command(deployment, running_app, subdomain)
    completed = run_ssh_with_password(device, username, password, command, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    return completed.returncode


def _stop_tunnel_command(deployment: RemoteDeployment, subdomain: str) -> str:
    short_subdomain, _url = _normalize_subdomain(subdomain)
    tunnel_file = _remote_tunnel_file(deployment.linux_user, deployment.package_name, short_subdomain)
    return (
        "set -eu\n"
        f"SUDO_PASS={shell_quote(os.environ.get('DEPLOYBOT_SUDO_PASSWORD', ''))}\n"
        f"TUNNEL_FILE={shell_quote(tunnel_file)}\n"
        f"APP_USER={shell_quote(deployment.linux_user)}\n"
        "if [ ! -f \"$TUNNEL_FILE\" ]; then\n"
        f"  printf 'Tunnel for {deployment.package_name} and {short_subdomain} is not running\\n'\n"
        "  exit 0\n"
        "fi\n"
        "PID=$(printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"pid\"])' \"$TUNNEL_FILE\")\n"
        "if kill -0 \"$PID\" >/dev/null 2>&1; then\n"
        "  printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" sh -lc "
        + shell_quote("kill \"$PID\"")
        + "\n"
        "fi\n"
        "printf '%s\\n' \"$SUDO_PASS\" | sudo -S -u \"$APP_USER\" rm -f \"$TUNNEL_FILE\"\n"
        f"printf 'Stopped tunnel for {deployment.package_name} on %s\\n' {shell_quote(short_subdomain)}\n"
    )


def stop_tunnel(workspace_dir: Path, server_number: int, deployment_number: int, subdomain: str) -> int:
    code, device, deployment, username, password = _resolve_remote_deployment(workspace_dir, server_number, deployment_number)
    if code != 0 or device is None or deployment is None or username is None or password is None:
        return code
    print(f"Stopping tunnel for {deployment.package_name} on {device.host} ({device.ip})...", flush=True)
    fake_result = _run_fake_deploy("stop-tunnel", device, username, password, [deployment.package_name, subdomain])
    if fake_result != -1:
        return int(fake_result)
    completed = run_ssh_with_password(device, username, password, _stop_tunnel_command(deployment, subdomain), capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    return completed.returncode


def format_remote_deployments(server_label: str, deployments: list[RemoteDeployment]) -> str:
    if not deployments:
        return f"No deployed apps were found on {server_label}."
    lines = [f"Deployed apps on {server_label}:"]
    for index, deployment in enumerate(deployments, start=1):
        lines.append(
            f"{index}. {deployment.package_name} as {deployment.linux_user}: {deployment.package_path}"
        )
    return "\n".join(lines)


def format_running_apps(server_label: str, running_apps: list[RunningApp]) -> str:
    if not running_apps:
        return f"No running apps were found on {server_label}."
    lines = [f"Running apps on {server_label}:"]
    for index, app in enumerate(running_apps, start=1):
        lines.append(f"{index}. {app.package_name} as {app.linux_user} on port {app.port} (pid {app.pid})")
    return "\n".join(lines)


def format_remote_services(server_label: str, services: list[RemoteService]) -> str:
    if not services:
        return f"No known services were detected on {server_label}."
    lines = [f"Services on {server_label}:"]
    for index, service in enumerate(services, start=1):
        status = "installed" if service.installed else "missing"
        lines.append(f"{index}. {service.name}: {status}")
    return "\n".join(lines)
