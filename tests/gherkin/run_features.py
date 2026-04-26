from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURES_DIR = PROJECT_ROOT / "tests" / "gherkin" / "features"


@dataclass
class ScenarioContext:
    command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    output: str = ""
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    stdin_text: str = ""


def set_environment_variable(context: ScenarioContext, key: str, value: str) -> None:
    context.env[key] = value.replace("{project_root}", str(PROJECT_ROOT))


def set_interactive_input(context: ScenarioContext, value: str) -> None:
    context.stdin_text = value.replace("\\n", "\n")


def _expand_placeholders(value: str) -> str:
    return value.replace("{project_root}", str(PROJECT_ROOT))


def remove_path(context: ScenarioContext, value: str) -> None:
    path = Path(_expand_placeholders(value))
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def expect_path_exists(context: ScenarioContext, value: str) -> None:
    path = Path(_expand_placeholders(value))
    if not path.exists():
        raise AssertionError(f"Expected path to exist: {path}")


def expect_file_contains(context: ScenarioContext, path_value: str, expected_text: str) -> None:
    path = Path(_expand_placeholders(path_value))
    if not path.exists():
        raise AssertionError(f"Expected file to exist: {path}")
    contents = path.read_text(encoding="utf-8")
    expected_text = _expand_placeholders(expected_text)
    if expected_text not in contents:
        raise AssertionError(f"Expected to find '{expected_text}' in file {path}.\nContents were:\n{contents}")


def run_command(context: ScenarioContext, command_text: str) -> None:
    context.command = shlex.split(command_text)
    completed = subprocess.run(
        context.command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        input=context.stdin_text,
        env={**context.env, "PATH": f"{PROJECT_ROOT}:{context.env.get('PATH', '')}"},
        check=False,
    )
    context.exit_code = completed.returncode
    context.output = (completed.stdout or "") + (completed.stderr or "")


def expect_exit_code(context: ScenarioContext, expected: str) -> None:
    if context.exit_code != int(expected):
        raise AssertionError(
            f"Expected exit code {expected}, got {context.exit_code}.\nOutput was:\n{context.output}"
        )


def expect_output_contains(context: ScenarioContext, expected: str) -> None:
    expected = _expand_placeholders(expected)
    if expected not in context.output:
        raise AssertionError(f"Expected to find '{expected}' in output.\nOutput was:\n{context.output}")


STEP_PATTERNS = [
    (re.compile(r'^Given the environment variable "(?P<key>.+)" is "(?P<value>.+)"$'), set_environment_variable),
    (re.compile(r'^Given the interactive input is "(?P<value>.*)"$'), set_interactive_input),
    (re.compile(r'^Given the path "(?P<value>.+)" is removed$'), remove_path),
    (re.compile(r'^When I run "(?P<command>.+)"$'), run_command),
    (re.compile(r"^Then the command exits with code (?P<code>\d+)$"), expect_exit_code),
    (re.compile(r'^And the output contains "(?P<text>.+)"$'), expect_output_contains),
    (re.compile(r'^Then the output contains "(?P<text>.+)"$'), expect_output_contains),
    (re.compile(r'^And the path "(?P<value>.+)" exists$'), expect_path_exists),
    (
        re.compile(r'^And the file "(?P<path_value>.+)" contains "(?P<expected_text>.+)"$'),
        expect_file_contains,
    ),
]


def execute_step(context: ScenarioContext, step: str) -> None:
    for pattern, handler in STEP_PATTERNS:
        match = pattern.match(step)
        if not match:
            continue
        groups = match.groupdict()
        if "command" in groups:
            handler(context, groups["command"])
            return
        if "path_value" in groups and "expected_text" in groups:
            handler(context, groups["path_value"], groups["expected_text"])
            return
        if "value" in groups and "key" not in groups:
            handler(context, groups["value"])
            return
        if "key" in groups and "value" in groups:
            handler(context, groups["key"], groups["value"])
            return
        if "code" in groups:
            handler(context, groups["code"])
            return
        if "text" in groups:
            handler(context, groups["text"])
            return
    raise AssertionError(f"Unsupported step: {step}")


def run_feature(feature_path: Path) -> tuple[int, int]:
    scenarios = 0
    failures = 0
    current_steps: list[str] = []

    for raw_line in feature_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("Feature:"):
            continue
        if line.startswith("Scenario:"):
            if current_steps:
                scenarios += 1
                failures += _run_scenario(feature_path, current_steps)
                current_steps = []
            continue
        if line.startswith(("Given ", "When ", "Then ", "And ")):
            current_steps.append(line)

    if current_steps:
        scenarios += 1
        failures += _run_scenario(feature_path, current_steps)

    return scenarios, failures


def _run_scenario(feature_path: Path, steps: list[str]) -> int:
    context = ScenarioContext()
    try:
        for step in steps:
            execute_step(context, step)
        print(f"PASS {feature_path.name}")
        return 0
    except AssertionError as exc:
        print(f"FAIL {feature_path.name}\n{exc}")
        return 1


def main() -> int:
    feature_files = sorted(FEATURES_DIR.glob("*.feature"))
    if not feature_files:
        print("No feature files were found.")
        return 1

    total_scenarios = 0
    total_failures = 0
    for feature_path in feature_files:
        scenarios, failures = run_feature(feature_path)
        total_scenarios += scenarios
        total_failures += failures

    print(f"Executed {total_scenarios} scenario(s); failures: {total_failures}")
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
