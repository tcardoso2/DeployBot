from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable


APP_MARKERS = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "Cargo.toml",
    "go.mod",
    "Podfile",
    ".xcodeproj",
    ".xcworkspace",
)


@dataclass(frozen=True)
class LocalApp:
    name: str
    path: Path


def _search_root(workspace_dir: Path) -> Path:
    override = os.environ.get("DEPLOYBOT_APP_SEARCH_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return workspace_dir.resolve().parent


def _looks_like_app(path: Path) -> bool:
    if not path.is_dir():
        return False

    children = {child.name for child in path.iterdir()}
    if children.intersection(APP_MARKERS):
        return True

    return any(name.endswith((".xcodeproj", ".xcworkspace")) for name in children)


def _candidate_directories(root_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for child in sorted(root_dir.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        candidates.append(child)
        for grandchild in sorted(child.iterdir()):
            if grandchild.name.startswith(".") or not grandchild.is_dir():
                continue
            candidates.append(grandchild)
    return candidates


def find_local_apps(workspace_dir: Path) -> list[LocalApp]:
    root_dir = _search_root(workspace_dir)
    apps: list[LocalApp] = []
    seen_paths: set[Path] = set()

    for candidate in _candidate_directories(root_dir):
        resolved_candidate = candidate.resolve()
        if resolved_candidate in seen_paths:
            continue
        if _looks_like_app(resolved_candidate):
            apps.append(LocalApp(name=resolved_candidate.name, path=resolved_candidate))
            seen_paths.add(resolved_candidate)

    return apps


def format_apps(apps: Iterable[LocalApp]) -> str:
    app_list = list(apps)
    if not app_list:
        return "No deployable apps were detected one level above this workspace or in the direct subfolders of those sibling folders."

    lines = ["Detected deployable apps:"]
    for index, app in enumerate(app_list, start=1):
        lines.append(f"{index}. {app.name}: {app.path}")
    return "\n".join(lines)
