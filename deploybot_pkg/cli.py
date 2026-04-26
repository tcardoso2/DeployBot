from __future__ import annotations

import argparse
from pathlib import Path

from .apps import find_local_apps, format_apps
from .deployments import (
    deploy_package,
    format_remote_deployments,
    format_running_apps,
    list_remote_deployments,
    list_running_apps,
    start_remote_app,
    stop_remote_app,
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
    "stop-app: stop a deployed app on a discovered server",
    "running: list currently running apps on a discovered server",
    "remote: select a discovered host number and run a remote command after prompting for credentials",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploybot",
        description="Discover devices on your local network and deploy sibling apps to them.",
        add_help=False,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-h", "--help", "-help", action="help", help="show this help message and exit")

    subparsers = parser.add_subparsers(dest="command")

    discover_parser = subparsers.add_parser(
        "discover",
        help="scan the local network for reachable devices",
    )
    discover_parser.add_argument(
        "--ping-sweep",
        action="store_true",
        help="probe the local subnet for additional devices",
    )
    discover_parser.add_argument(
        "--limit",
        type=int,
        default=32,
        help="maximum number of ping sweep hosts to probe",
    )

    subparsers.add_parser(
        "list-apps",
        help="list sibling folders that look like deployable apps",
    )

    package_parser = subparsers.add_parser(
        "package",
        help="build and package a listed app into the local dist folder",
    )
    package_parser.add_argument("app_number", type=int, help="number from 'deploybot list-apps'")

    subparsers.add_parser(
        "list-packages",
        help="list built packages in the local dist folder",
    )

    deploy_parser = subparsers.add_parser(
        "deploy",
        help="deploy a packaged app to a discovered server",
    )
    deploy_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")
    deploy_parser.add_argument("package_number", type=int, help="number from 'deploybot list-packages'")

    list_deployments_parser = subparsers.add_parser(
        "list-deployments",
        help="list deployed packaged apps on a discovered server",
    )
    list_deployments_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")

    start_app_parser = subparsers.add_parser(
        "start-app",
        help="start a deployed app on a discovered server",
    )
    start_app_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")
    start_app_parser.add_argument("deployment_number", type=int, help="number from 'deploybot list-deployments'")

    stop_app_parser = subparsers.add_parser(
        "stop-app",
        help="stop a deployed app on a discovered server",
    )
    stop_app_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")
    stop_app_parser.add_argument("deployment_number", type=int, help="number from 'deploybot list-deployments'")

    running_parser = subparsers.add_parser(
        "running",
        help="list currently running apps on a discovered server",
    )
    running_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")

    remote_parser = subparsers.add_parser(
        "remote",
        help="run a command on a discovered host after prompting for credentials",
    )
    remote_parser.add_argument("host_number", type=int, help="number from 'deploybot discover'")
    remote_parser.add_argument("remote_command", nargs="+", help="remote command to execute")

    parser.epilog = "Features:\n" + "\n".join(f"- {line}" for line in FEATURE_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace_dir = Path.cwd()

    if args.command == "discover":
        devices = discover_devices(workspace_dir=workspace_dir, ping_sweep=args.ping_sweep, limit=args.limit)
        print(format_devices(devices))
        return 0

    if args.command == "list-apps":
        apps = find_local_apps(workspace_dir=workspace_dir)
        print(format_apps(apps))
        return 0

    if args.command == "package":
        return package_app(workspace_dir=workspace_dir, app_number=args.app_number)

    if args.command == "list-packages":
        packages = list_packages(workspace_dir=workspace_dir)
        print(format_packages(packages))
        return 0

    if args.command == "deploy":
        return deploy_package(workspace_dir=workspace_dir, server_number=args.server_number, package_number=args.package_number)

    if args.command == "list-deployments":
        code, deployments = list_remote_deployments(workspace_dir=workspace_dir, server_number=args.server_number)
        if code != 0 or deployments is None:
            return code
        devices = discover_devices(workspace_dir=workspace_dir)
        device = devices[args.server_number - 1]
        print(format_remote_deployments(f"{device.host} ({device.ip})", deployments))
        return 0

    if args.command == "start-app":
        return start_remote_app(
            workspace_dir=workspace_dir,
            server_number=args.server_number,
            deployment_number=args.deployment_number,
        )

    if args.command == "stop-app":
        return stop_remote_app(
            workspace_dir=workspace_dir,
            server_number=args.server_number,
            deployment_number=args.deployment_number,
        )

    if args.command == "running":
        code, device, running_apps = list_running_apps(workspace_dir=workspace_dir, server_number=args.server_number)
        if code != 0 or device is None or running_apps is None:
            return code
        print(format_running_apps(f"{device.host} ({device.ip})", running_apps))
        return 0

    if args.command == "remote":
        return run_remote_command(
            workspace_dir=workspace_dir,
            host_number=args.host_number,
            command_parts=args.remote_command,
        )

    parser.print_help()
    return 0
