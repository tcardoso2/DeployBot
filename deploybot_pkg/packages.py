from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .apps import LocalApp, find_local_apps


@dataclass(frozen=True)
class BuiltPackage:
    name: str
    path: Path


def _dist_root(workspace_dir: Path) -> Path:
    override = os.environ.get("DEPLOYBOT_DIST_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return workspace_dir.resolve() / "dist"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _infer_package_name_parts(package_name: str) -> tuple[str, str]:
    match = re.match(r"^(?P<app_name>.+)-(?P<version>\d+\.\d+\.\d+)$", package_name)
    if not match:
        raise RuntimeError(
            f"Package {package_name} is missing deploybot-manifest.json and its folder name does not match '<app-name>-<x.y.z>'."
        )
    return match.group("app_name"), match.group("version")


def _detect_app_type(app: LocalApp) -> str | None:
    if (app.path / "package.json").exists():
        return "npm"
    if (app.path / "pyproject.toml").exists() or (app.path / "requirements.txt").exists():
        return "python"
    return None


def _base_version_for_app(app: LocalApp, app_type: str) -> str:
    if app_type == "npm":
        package_json = _read_json(app.path / "package.json")
        return str(package_json.get("version", "0.1.0"))
    return "0.1.0"


def _version_pattern(app_name: str) -> re.Pattern[str]:
    escaped_name = re.escape(app_name)
    return re.compile(rf"^{escaped_name}-(\d+)\.(\d+)\.(\d+)$")


def _parse_version(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Unsupported version format: {version}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _next_package_version(dist_root: Path, app_name: str, base_version: str) -> str:
    base_major, base_minor, base_patch = _parse_version(base_version)
    existing_versions: list[tuple[int, int, int]] = []
    pattern = _version_pattern(app_name)

    if dist_root.exists():
        for child in dist_root.iterdir():
            match = pattern.match(child.name)
            if match:
                existing_versions.append(tuple(int(part) for part in match.groups()))

    if not existing_versions:
        return base_version

    same_series = [version for version in existing_versions if version[0] == base_major and version[1] == base_minor]
    if not same_series:
        return base_version

    next_patch = max(version[2] for version in same_series) + 1
    return f"{base_major}.{base_minor}.{next_patch}"


def _run_command(cmd: list[str], cwd: Path) -> None:
    completed = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="")
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(cmd)}")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)


def _build_npm_app(app: LocalApp) -> Path:
    if shutil.which("npm") is None:
        raise RuntimeError("npm is not available on this machine.")

    _run_command(["npm", "run", "build"], cwd=app.path)
    dist_dir = app.path / "dist"
    if not dist_dir.exists():
        raise RuntimeError(f"Expected npm build output at {dist_dir}.")
    return dist_dir


def _build_python_app(app: LocalApp) -> Path:
    staging_dir = app.path / ".deploybot-python-build"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    for child in sorted(app.path.iterdir()):
        if child.name.startswith(".") or child.name == "__pycache__":
            continue
        if child.name in {"dist", ".deploybot-python-build"}:
            continue
        destination = staging_dir / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)

    return staging_dir


def _build_app(app: LocalApp, app_type: str) -> Path:
    if app_type == "npm":
        return _build_npm_app(app)
    if app_type == "python":
        return _build_python_app(app)
    raise RuntimeError(f"Unsupported app type: {app_type}")


def _runtime_profile(app: LocalApp, app_type: str) -> dict:
    if app_type == "npm":
        package_json = _read_json(app.path / "package.json")
        scripts = package_json.get("scripts", {})
        build_script = str(scripts.get("build", ""))
        source_kind = "vite-build-output" if "vite" in build_script else "node-build-output"
        return {
            "app_type": "npm",
            "runtime": "static-files",
            "install_dependencies": [],
            "source_kind": source_kind,
        }
    return {
        "app_type": "python",
        "runtime": "python-files",
        "install_dependencies": ["python3"],
        "source_kind": "python-source",
    }


def _runtime_profile_for_packaged_contents(package: BuiltPackage, app_type: str) -> dict:
    if app_type == "npm":
        return {
            "app_type": "npm",
            "runtime": "static-files",
            "install_dependencies": [],
            "source_kind": "vite-build-output" if (package.path / "index.html").exists() else "node-build-output",
        }
    return {
        "app_type": "python",
        "runtime": "python-files",
        "install_dependencies": ["python3"],
        "source_kind": "python-source",
    }


def _detect_packaged_app_type(package: BuiltPackage) -> str:
    if (package.path / "index.html").exists() or (package.path / "assets").exists():
        return "npm"
    if (package.path / "pyproject.toml").exists() or (package.path / "requirements.txt").exists():
        return "python"
    raise RuntimeError(
        f"Package {package.name} is missing deploybot-manifest.json and DeployBot could not infer its app type from the packaged files."
    )


def _infer_package_manifest(package: BuiltPackage) -> dict:
    app_name, package_version = _infer_package_name_parts(package.name)
    app_type = _detect_packaged_app_type(package)
    manifest = {
        "app_name": app_name,
        "app_type": app_type,
        "package_name": package.name,
        "package_version": package_version,
        **_runtime_profile_for_packaged_contents(package, app_type),
    }
    _write_json(package.path / "deploybot-manifest.json", manifest)
    return manifest


def _write_manifest(package_dir: Path, app: LocalApp, app_type: str, package_version: str) -> None:
    manifest = {
        "app_name": app.name,
        "app_type": app_type,
        "package_name": package_dir.name,
        "package_version": package_version,
        **_runtime_profile(app, app_type),
    }
    _write_json(package_dir / "deploybot-manifest.json", manifest)


def package_app(workspace_dir: Path, app_number: int) -> int:
    apps = find_local_apps(workspace_dir)
    if app_number < 1 or app_number > len(apps):
        print(f"App number {app_number} was not found.")
        return 1

    app = apps[app_number - 1]
    app_type = _detect_app_type(app)
    if app_type is None:
        print(f"Could not detect a supported app type for {app.name}.")
        return 1

    dist_root = _dist_root(workspace_dir)
    dist_root.mkdir(parents=True, exist_ok=True)

    try:
        source_dir = _build_app(app, app_type)
        base_version = _base_version_for_app(app, app_type)
        package_version = _next_package_version(dist_root, app.name, base_version)
        package_dir = dist_root / f"{app.name}-{package_version}"
        if package_dir.exists():
            shutil.rmtree(package_dir)
        _copy_tree(source_dir, package_dir)
        _write_manifest(package_dir, app, app_type, package_version)
    except (RuntimeError, ValueError) as exc:
        print(str(exc))
        return 1
    finally:
        python_staging = app.path / ".deploybot-python-build"
        if python_staging.exists():
            shutil.rmtree(python_staging)

    print(f"Packaged {app.name} as {package_dir.name}")
    print(f"Output: {package_dir}")
    return 0


def list_packages(workspace_dir: Path) -> list[BuiltPackage]:
    dist_root = _dist_root(workspace_dir)
    if not dist_root.exists():
        return []

    packages = [BuiltPackage(name=child.name, path=child) for child in sorted(dist_root.iterdir()) if child.is_dir()]
    return packages


def resolve_package(workspace_dir: Path, package_number: int) -> BuiltPackage | None:
    packages = list_packages(workspace_dir)
    if package_number < 1 or package_number > len(packages):
        return None
    return packages[package_number - 1]


def read_package_manifest(package: BuiltPackage) -> dict:
    manifest_path = package.path / "deploybot-manifest.json"
    if not manifest_path.exists():
        return _infer_package_manifest(package)
    return _read_json(manifest_path)


def format_packages(packages: Iterable[BuiltPackage]) -> str:
    package_list = list(packages)
    if not package_list:
        return "No packaged apps were found in dist."

    lines = ["Packaged apps:"]
    for index, package in enumerate(package_list, start=1):
        lines.append(f"{index}. {package.name}: {package.path}")
    return "\n".join(lines)
