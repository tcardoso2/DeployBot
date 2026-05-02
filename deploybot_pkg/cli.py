from __future__ import annotations

import argparse
from pathlib import Path

from .commands import execute_command, help_text


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

    services_parser = subparsers.add_parser(
        "services",
        help="list detectable remote services on a discovered server",
    )
    services_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")

    start_tunnel_parser = subparsers.add_parser(
        "start-tunnel",
        help="start an ngrok tunnel for a deployed app",
    )
    start_tunnel_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")
    start_tunnel_parser.add_argument("deployment_number", type=int, help="number from 'deploybot list-deployments'")
    start_tunnel_parser.add_argument("subdomain", help="subdomain or full ngrok host to bind to")

    stop_tunnel_parser = subparsers.add_parser(
        "stop-tunnel",
        help="stop an ngrok tunnel for a deployed app",
    )
    stop_tunnel_parser.add_argument("server_number", type=int, help="number from 'deploybot discover'")
    stop_tunnel_parser.add_argument("deployment_number", type=int, help="number from 'deploybot list-deployments'")
    stop_tunnel_parser.add_argument("subdomain", help="subdomain or full ngrok host to stop")

    remote_parser = subparsers.add_parser(
        "remote",
        help="run a command on a discovered host after prompting for credentials",
    )
    remote_parser.add_argument("host_number", type=int, help="number from 'deploybot discover'")
    remote_parser.add_argument("remote_command", nargs="+", help="remote command to execute")

    parser.epilog = help_text()
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace_dir = Path.cwd()

    if args.command is not None:
        values = {
            key: value
            for key, value in vars(args).items()
            if key != "command" and value is not None
        }
        if "remote_command" in values:
            values["remote_command"] = " ".join(values["remote_command"])
        result = execute_command(args.command, values, workspace_dir)
        if result.output:
            print(result.output, end="" if result.output.endswith("\n") else "\n")
        return result.exit_code

    parser.print_help()
    return 0
