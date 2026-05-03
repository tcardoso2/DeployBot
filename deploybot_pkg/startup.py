from __future__ import annotations

import re
from pathlib import Path


_PRIMARY_PYTHON_FILES = ("main.py", "app.py", "server.py", "run.py")
_SERVER_EXTENSIONS = {".js", ".cjs", ".mjs", ".py", ".sh"}
_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "node_modules",
    ".deploybot-python-build",
}


def deterministic_port(package_name: str) -> int:
    return 41000 + sum(ord(char) for char in package_name) % 1000


def detect_startup_points(app_dir: Path, app_type: str, runtime: str) -> list[dict]:
    startup_points: list[dict] = []

    if runtime == "static-files":
        startup_points.append(
            {
                "name": "web",
                "role": "primary",
                "command_template": "python3 -m http.server {port} --bind 0.0.0.0",
                "source": "packaged static files",
            }
        )
    elif runtime == "python-files":
        primary_file = _find_primary_python_file(app_dir)
        if primary_file is not None:
            startup_points.append(
                {
                    "name": primary_file.stem,
                    "role": "primary",
                    "command_template": f"python3 {primary_file.as_posix()}",
                    "path": primary_file.as_posix(),
                    "source": "python entrypoint",
                }
            )

    seen_paths = {str(point.get("path", "")) for point in startup_points if point.get("path")}
    for relative_path in _find_companion_server_files(app_dir, app_type=app_type):
        rel_text = relative_path.as_posix()
        if rel_text in seen_paths:
            continue
        startup_points.append(
            {
                "name": _companion_name(relative_path),
                "role": "companion",
                "command_template": _command_for_path(relative_path),
                "path": rel_text,
                "source": "detected companion server",
            }
        )
        seen_paths.add(rel_text)

    return startup_points


def materialize_startup_points(manifest: dict, package_name: str) -> list[dict]:
    startup_points = list(manifest.get("startup_points") or [])
    if not startup_points:
        return []

    port = deterministic_port(package_name)
    resolved: list[dict] = []
    for point in startup_points:
        command_template = str(point.get("command_template", "")).strip()
        resolved.append(
            {
                "name": str(point.get("name", "startup")).strip() or "startup",
                "role": str(point.get("role", "companion")).strip() or "companion",
                "path": str(point.get("path", "")).strip(),
                "source": str(point.get("source", "")).strip(),
                "command": command_template.replace("{port}", str(port)),
                "port": port if "{port}" in command_template else None,
            }
        )
    return resolved


def supplemental_package_files(app_dir: Path, startup_points: list[dict]) -> list[Path]:
    extras: list[Path] = []
    seen: set[Path] = set()

    for point in startup_points:
        path_text = str(point.get("path", "")).strip()
        if not path_text:
            continue
        relative_path = Path(path_text)
        if relative_path in seen:
            continue
        candidate = app_dir / relative_path
        if candidate.exists() and candidate.is_file():
            extras.append(relative_path)
            seen.add(relative_path)

    if any(_is_node_path(Path(str(point.get("path", "")))) for point in startup_points):
        for filename in ("package.json", "package-lock.json", "npm-shrinkwrap.json"):
            candidate = app_dir / filename
            relative = Path(filename)
            if candidate.exists() and relative not in seen:
                extras.append(relative)
                seen.add(relative)

    return extras


def _find_primary_python_file(app_dir: Path) -> Path | None:
    for filename in _PRIMARY_PYTHON_FILES:
        candidate = app_dir / filename
        if candidate.exists() and candidate.is_file():
            return Path(filename)
    return None


def _find_companion_server_files(app_dir: Path, app_type: str) -> list[Path]:
    results: list[Path] = []
    for candidate in sorted(app_dir.rglob("*")):
        if not candidate.is_file():
            continue
        if any(part in _EXCLUDED_PARTS for part in candidate.parts):
            continue
        if candidate.suffix.lower() not in _SERVER_EXTENSIONS:
            continue
        relative = candidate.relative_to(app_dir)
        stem = candidate.stem.lower()
        if stem in {"build", "vite.config", "webpack.config"}:
            continue
        if _looks_like_companion_server(relative, stem=stem, app_type=app_type):
            results.append(relative)
    return results


def _looks_like_companion_server(relative_path: Path, stem: str, app_type: str) -> bool:
    parts = [part.lower() for part in relative_path.parts]
    name = relative_path.name.lower()
    if any(token in stem for token in ("ws", "websocket", "socket")):
        return True
    if stem in {"server", "api", "backend"} or stem.endswith(("-server", "_server")):
        return True
    if app_type == "python" and name == "server.py":
        return True
    return any(part in {"ws", "websocket", "socket", "server", "api", "backend"} for part in parts[:-1])


def _command_for_path(relative_path: Path) -> str:
    if _is_node_path(relative_path):
        return f"node {relative_path.as_posix()}"
    if relative_path.suffix.lower() == ".py":
        return f"python3 {relative_path.as_posix()}"
    return f"sh {relative_path.as_posix()}"


def _companion_name(relative_path: Path) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", relative_path.stem).strip("-")
    return name or "companion-server"


def _is_node_path(path: Path) -> bool:
    return path.suffix.lower() in {".js", ".cjs", ".mjs"}
