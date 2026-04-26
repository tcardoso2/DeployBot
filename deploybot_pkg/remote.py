from __future__ import annotations

import getpass
import os
import shlex
import stat
import subprocess
import tempfile
from pathlib import Path

from .discovery import Device, discover_devices


def prompt_username() -> str:
    return input("Username: ").strip()


def prompt_password() -> str:
    if os.environ.get("DEPLOYBOT_PLAIN_PASSWORD_PROMPT") == "1" or not os.isatty(0):
        return input("Password: ")
    return getpass.getpass("Password: ")


def resolve_device(workspace_dir: Path, host_number: int) -> Device | None:
    devices = discover_devices(workspace_dir=workspace_dir)
    if host_number < 1 or host_number > len(devices):
        return None
    return devices[host_number - 1]


def _run_fake_executor(device: Device, username: str, password: str, command: str) -> int:
    executor = os.environ.get("DEPLOYBOT_REMOTE_EXECUTOR")
    if not executor:
        return -1

    completed = subprocess.run(
        [executor, device.host, device.ip, username, password, command],
        check=False,
    )
    return completed.returncode


def _ssh_command(device: Device, username: str, command: str) -> list[str]:
    target = f"{username}@{device.ip if device.ip != 'unresolved' else device.host}"
    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "NumberOfPasswordPrompts=1",
        target,
        command,
    ]


def _with_askpass(password: str) -> tuple[Path, dict[str, str]]:
    askpass_contents = f"#!/bin/sh\nprintf '%s\\n' {password!r}\n"
    with tempfile.NamedTemporaryFile("w", delete=False) as askpass_file:
        askpass_file.write(askpass_contents)
        askpass_path = Path(askpass_file.name)

    askpass_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    env = {
        **os.environ,
        "SSH_ASKPASS": str(askpass_path),
        "SSH_ASKPASS_REQUIRE": "force",
        "DISPLAY": os.environ.get("DISPLAY", "deploybot"),
    }
    return askpass_path, env


def run_ssh_with_password(device: Device, username: str, password: str, command: str, capture_output: bool = False) -> subprocess.CompletedProcess:
    askpass_path, env = _with_askpass(password)

    try:
        with open(os.devnull, "r", encoding="utf-8") as devnull:
            completed = subprocess.run(
                _ssh_command(device, username, command),
                stdin=devnull,
                env=env,
                text=True,
                capture_output=capture_output,
                check=False,
            )
        return completed
    finally:
        askpass_path.unlink(missing_ok=True)


def run_scp_with_password(device: Device, username: str, password: str, source: Path, destination: str) -> subprocess.CompletedProcess:
    askpass_path, env = _with_askpass(password)

    target = f"{username}@{device.ip if device.ip != 'unresolved' else device.host}:{destination}"
    cmd = [
        "scp",
        "-r",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "PreferredAuthentications=password",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "NumberOfPasswordPrompts=1",
        str(source),
        target,
    ]

    try:
        with open(os.devnull, "r", encoding="utf-8") as devnull:
            return subprocess.run(
                cmd,
                stdin=devnull,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
    finally:
        askpass_path.unlink(missing_ok=True)


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def run_remote_command(workspace_dir: Path, host_number: int, command_parts: list[str]) -> int:
    device = resolve_device(workspace_dir=workspace_dir, host_number=host_number)
    if device is None:
        print(f"Host number {host_number} was not found.")
        return 1

    username = prompt_username()
    password = prompt_password()
    command = " ".join(command_parts)

    print(f"Connecting to {device.host} ({device.ip})...", flush=True)

    fake_result = _run_fake_executor(device=device, username=username, password=password, command=command)
    if fake_result != -1:
        return fake_result

    return run_ssh_with_password(device=device, username=username, password=password, command=command).returncode
