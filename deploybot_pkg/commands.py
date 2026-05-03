from __future__ import annotations

import io
import os
import shlex
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from .apps import find_local_apps, format_apps
from .deployments import (
    deploy_package,
    format_remote_deployments,
    format_remote_services,
    format_startup_points,
    format_running_apps,
    list_remote_deployments,
    list_remote_services,
    list_startup_points,
    list_running_apps,
    start_remote_app,
    start_remote_app_custom,
    start_tunnel,
    stop_remote_app,
    stop_tunnel,
)
from .discovery import discover_devices, format_devices
from .packages import format_packages, list_packages, package_app
from .remote import run_remote_command


FEATURE_SUMMARY = [
    "discover: detect devices on the local network using known hosts, ARP data, and optional ping sweeps",
    "list-apps: find deployable apps in sibling folders next to this DeployBot workspace",
    "package: build and package a discovered app into DeployBot/dist using versioned output folders",
    "list-packages: list the versioned packages available in DeployBot/dist",
    "deploy: deploy a packaged app to a discovered server and prepare a dedicated linux runtime user",
    "list-deployments: list packaged apps already deployed on a discovered server",
    "start-app: start a deployed app on a discovered server and report its runtime port",
    "start-app-custom: run a custom start command inside a deployed app directory as that app's linux user",
    "startup-points: inspect the commands start-app will run, including companion servers inside the same deployment",
    "stop-app: stop a deployed app on a discovered server",
    "running: list currently running apps on a discovered server",
    "services: list detectable remote services on a discovered server",
    "start-tunnel: start an ngrok tunnel for a deployed app and print its public URL",
    "stop-tunnel: stop an ngrok tunnel for a deployed app and subdomain",
    "remote: select a discovered host number and run a remote command after prompting for credentials",
]


@dataclass(frozen=True)
class CommandField:
    name: str
    prompt: str
    kind: str = "text"
    default: str = ""
    secret: bool = False


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help_text: str
    fields: tuple[CommandField, ...] = ()


COMMAND_SPECS = (
    CommandSpec(
        name="discover",
        help_text="scan the local network for reachable devices",
        fields=(
            CommandField(name="ping_sweep", prompt="Ping sweep? [y/N]", kind="bool", default="n"),
            CommandField(name="limit", prompt="Ping sweep host limit", kind="int", default="32"),
        ),
    ),
    CommandSpec(name="list-apps", help_text="list sibling folders that look like deployable apps"),
    CommandSpec(
        name="package",
        help_text="build and package a listed app into the local dist folder",
        fields=(CommandField(name="app_number", prompt="App number", kind="int"),),
    ),
    CommandSpec(name="list-packages", help_text="list built packages in the local dist folder"),
    CommandSpec(
        name="deploy",
        help_text="deploy a packaged app to a discovered server",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="package_number", prompt="Package number", kind="int"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="list-deployments",
        help_text="list deployed packaged apps on a discovered server",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="start-app",
        help_text="start a deployed app on a discovered server",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="deployment_number", prompt="Deployment number", kind="int"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="start-app-custom",
        help_text="run a custom command in a deployed app directory as that app's linux user",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="deployment_number", prompt="Deployment number", kind="int"),
            CommandField(name="custom_command", prompt="Custom command"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="startup-points",
        help_text="show the commands start-app will run for a deployed app",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="deployment_number", prompt="Deployment number", kind="int"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="stop-app",
        help_text="stop a deployed app on a discovered server",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="deployment_number", prompt="Deployment number", kind="int"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="running",
        help_text="list currently running apps on a discovered server",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="services",
        help_text="list detectable remote services on a discovered server",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="start-tunnel",
        help_text="start an ngrok tunnel for a deployed app",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="deployment_number", prompt="Deployment number", kind="int"),
            CommandField(name="subdomain", prompt="Subdomain"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="stop-tunnel",
        help_text="stop an ngrok tunnel for a deployed app",
        fields=(
            CommandField(name="server_number", prompt="Server number", kind="int"),
            CommandField(name="deployment_number", prompt="Deployment number", kind="int"),
            CommandField(name="subdomain", prompt="Subdomain"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
    CommandSpec(
        name="remote",
        help_text="run a command on a discovered host after prompting for credentials",
        fields=(
            CommandField(name="host_number", prompt="Host number", kind="int"),
            CommandField(name="remote_command", prompt="Remote command"),
            CommandField(name="username", prompt="Username"),
            CommandField(name="password", prompt="Password", secret=True),
        ),
    ),
)

COMMAND_SPEC_BY_NAME = {spec.name: spec for spec in COMMAND_SPECS}


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str


def help_text() -> str:
    return "Features:\n" + "\n".join(f"- {line}" for line in FEATURE_SUMMARY)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "t", "y", "yes", "on"}


def _coerce_field(field: CommandField, raw_value: str) -> object:
    value = raw_value.strip()
    if field.kind == "int":
        return int(value)
    if field.kind == "bool":
        return _parse_bool(value or field.default)
    return value


def coerce_command_inputs(command_name: str, raw_inputs: dict[str, str]) -> dict[str, object]:
    spec = COMMAND_SPEC_BY_NAME[command_name]
    coerced: dict[str, object] = {}
    for field in spec.fields:
        raw_value = raw_inputs.get(field.name, field.default)
        coerced[field.name] = _coerce_field(field, raw_value)
    return coerced


def _temporary_env(overrides: dict[str, str]):
    class _EnvContext:
        def __enter__(self_inner) -> None:
            self_inner.previous = {key: os.environ.get(key) for key in overrides}
            for key, value in overrides.items():
                os.environ[key] = value

        def __exit__(self_inner, exc_type, exc, tb) -> None:
            for key, previous in self_inner.previous.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous

    return _EnvContext()


def execute_command(command_name: str, values: dict[str, object], workspace_dir: Path) -> CommandResult:
    buffer = io.StringIO()
    env_overrides: dict[str, str] = {}
    username = str(values.get("username", "")).strip()
    password = str(values.get("password", "")).strip()
    if username:
        env_overrides["DEPLOYBOT_USERNAME"] = username
    if password:
        env_overrides["DEPLOYBOT_PASSWORD"] = password

    with _temporary_env(env_overrides), redirect_stdout(buffer), redirect_stderr(buffer):
        try:
            exit_code = _execute_command_internal(command_name=command_name, values=values, workspace_dir=workspace_dir)
        except ValueError as exc:
            print(str(exc))
            exit_code = 1
    return CommandResult(exit_code=exit_code, output=buffer.getvalue())


def _execute_command_internal(command_name: str, values: dict[str, object], workspace_dir: Path) -> int:
    if command_name == "discover":
        devices = discover_devices(
            workspace_dir=workspace_dir,
            ping_sweep=bool(values.get("ping_sweep", False)),
            limit=int(values.get("limit", 32)),
        )
        print(format_devices(devices))
        return 0

    if command_name == "list-apps":
        print(format_apps(find_local_apps(workspace_dir=workspace_dir)))
        return 0

    if command_name == "package":
        return package_app(workspace_dir=workspace_dir, app_number=int(values["app_number"]))

    if command_name == "list-packages":
        print(format_packages(list_packages(workspace_dir=workspace_dir)))
        return 0

    if command_name == "deploy":
        return deploy_package(
            workspace_dir=workspace_dir,
            server_number=int(values["server_number"]),
            package_number=int(values["package_number"]),
        )

    if command_name == "list-deployments":
        code, deployments = list_remote_deployments(workspace_dir=workspace_dir, server_number=int(values["server_number"]))
        if code != 0 or deployments is None:
            return code
        devices = discover_devices(workspace_dir=workspace_dir)
        device = devices[int(values["server_number"]) - 1]
        print(format_remote_deployments(f"{device.host} ({device.ip})", deployments))
        return 0

    if command_name == "start-app":
        return start_remote_app(
            workspace_dir=workspace_dir,
            server_number=int(values["server_number"]),
            deployment_number=int(values["deployment_number"]),
        )

    if command_name == "start-app-custom":
        custom_command = str(values["custom_command"]).strip()
        if not custom_command:
            raise ValueError("Custom command cannot be empty.")
        return start_remote_app_custom(
            workspace_dir=workspace_dir,
            server_number=int(values["server_number"]),
            deployment_number=int(values["deployment_number"]),
            custom_command=custom_command,
        )

    if command_name == "startup-points":
        code, device, deployment, startup_points = list_startup_points(
            workspace_dir=workspace_dir,
            server_number=int(values["server_number"]),
            deployment_number=int(values["deployment_number"]),
        )
        if code != 0 or device is None or deployment is None or startup_points is None:
            return code
        print(format_startup_points(f"{device.host} ({device.ip})", deployment, startup_points))
        return 0

    if command_name == "stop-app":
        return stop_remote_app(
            workspace_dir=workspace_dir,
            server_number=int(values["server_number"]),
            deployment_number=int(values["deployment_number"]),
        )

    if command_name == "running":
        code, device, running_apps = list_running_apps(workspace_dir=workspace_dir, server_number=int(values["server_number"]))
        if code != 0 or device is None or running_apps is None:
            return code
        print(format_running_apps(f"{device.host} ({device.ip})", running_apps))
        return 0

    if command_name == "services":
        code, device, services = list_remote_services(workspace_dir=workspace_dir, server_number=int(values["server_number"]))
        if code != 0 or device is None or services is None:
            return code
        print(format_remote_services(f"{device.host} ({device.ip})", services))
        return 0

    if command_name == "start-tunnel":
        return start_tunnel(
            workspace_dir=workspace_dir,
            server_number=int(values["server_number"]),
            deployment_number=int(values["deployment_number"]),
            subdomain=str(values["subdomain"]),
        )

    if command_name == "stop-tunnel":
        return stop_tunnel(
            workspace_dir=workspace_dir,
            server_number=int(values["server_number"]),
            deployment_number=int(values["deployment_number"]),
            subdomain=str(values["subdomain"]),
        )

    if command_name == "remote":
        remote_command = str(values["remote_command"]).strip()
        if not remote_command:
            raise ValueError("Remote command cannot be empty.")
        return run_remote_command(
            workspace_dir=workspace_dir,
            host_number=int(values["host_number"]),
            command_parts=shlex.split(remote_command),
        )

    raise ValueError(f"Unsupported command: {command_name}")
