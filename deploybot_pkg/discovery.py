from __future__ import annotations

import ipaddress
import os
import platform
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Device:
    host: str
    ip: str
    source: str


def _known_hosts_path() -> Path:
    override = os.environ.get("DEPLOYBOT_KNOWN_HOSTS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ssh" / "known_hosts"


def _extract_known_host_value(host: str) -> str | None:
    cleaned = host.strip()
    if not cleaned or cleaned.startswith("*") or cleaned.startswith("|"):
        return None

    if cleaned.startswith("[") and "]:" in cleaned:
        return cleaned[1:].split("]:", 1)[0]

    return cleaned


def _read_known_hosts() -> list[Device]:
    known_hosts_path = _known_hosts_path()
    if not known_hosts_path.exists():
        return []

    devices: list[Device] = []
    for line in known_hosts_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line or line.startswith("|") or line.startswith("#"):
            continue
        host_field = line.split(" ", 1)[0]
        for host in host_field.split(","):
            host_value = _extract_known_host_value(host)
            if host_value is None:
                continue
            if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host_value):
                devices.append(Device(host=host_value, ip=host_value, source="known_hosts"))
            elif ":" not in host_value:
                devices.append(Device(host=host_value, ip=_resolve_host(host_value), source="known_hosts"))
    return devices


def _resolve_host(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except OSError:
        return "unresolved"


def _read_arp_table() -> list[Device]:
    if os.environ.get("DEPLOYBOT_DISABLE_ARP") == "1":
        return []
    if not shutil.which("arp"):
        return []

    completed = subprocess.run(["arp", "-a"], capture_output=True, text=True, check=False)
    pattern = re.compile(r"(?P<host>[^\s]+) \((?P<ip>\d+\.\d+\.\d+\.\d+)\)")
    devices: list[Device] = []
    for match in pattern.finditer(completed.stdout):
        devices.append(Device(host=match.group("host"), ip=match.group("ip"), source="arp"))
    return devices


def _local_subnet_candidates(limit: int) -> list[str]:
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except OSError:
        return []

    try:
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return []

    candidates = []
    for host in network.hosts():
        host_ip = str(host)
        if host_ip == local_ip:
            continue
        candidates.append(host_ip)
        if len(candidates) >= limit:
            break
    return candidates


def _ping_host(ip: str) -> bool:
    if not shutil.which("ping"):
        return False

    system = platform.system().lower()
    cmd = ["ping", "-c", "1", "-W", "1000", ip]
    if "darwin" in system:
        cmd = ["ping", "-c", "1", "-t", "1", ip]

    completed = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return completed.returncode == 0


def _ping_sweep(limit: int) -> list[Device]:
    if os.environ.get("DEPLOYBOT_DISABLE_PING_SWEEP") == "1":
        return []
    devices: list[Device] = []
    for ip in _local_subnet_candidates(limit):
        if _ping_host(ip):
            devices.append(Device(host=ip, ip=ip, source="ping"))
    return devices


def _dedupe_devices(devices: list[Device]) -> list[Device]:
    seen: dict[tuple[str, str], Device] = {}
    for device in devices:
        key = (device.host, device.ip)
        seen.setdefault(key, device)
    return sorted(seen.values(), key=lambda device: (device.ip, device.host, device.source))


def discover_devices(workspace_dir: Path, ping_sweep: bool = False, limit: int = 32) -> list[Device]:
    del workspace_dir
    devices = []
    devices.extend(_read_known_hosts())
    devices.extend(_read_arp_table())
    if ping_sweep:
        devices.extend(_ping_sweep(limit=limit))
    return _dedupe_devices(devices)


def format_devices(devices: list[Device]) -> str:
    if not devices:
        return "No devices were detected. Try again with 'deploybot discover --ping-sweep'."

    lines = ["Discovered devices:"]
    for index, device in enumerate(devices, start=1):
        lines.append(f"{index}. {device.host} ({device.ip}) via {device.source}")
    return "\n".join(lines)
