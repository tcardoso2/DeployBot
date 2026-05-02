from __future__ import annotations

import argparse
import curses
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .commands import COMMAND_SPECS, COMMAND_SPEC_BY_NAME, coerce_command_inputs, execute_command, help_text


TITLE = "DeployBot TUI"
MIN_HEIGHT = 24
MIN_WIDTH = 90
MENU_WIDTH = 24
BUTTON_LABELS = ("Run", "Clear", "Help")
BUTTON1_MASK = (
    getattr(curses, "BUTTON1_CLICKED", 0)
    | getattr(curses, "BUTTON1_PRESSED", 0)
    | getattr(curses, "BUTTON1_RELEASED", 0)
)
BUTTON4_MASK = getattr(curses, "BUTTON4_PRESSED", 0)
BUTTON5_MASK = getattr(curses, "BUTTON5_PRESSED", 0)
ACTIVE_SCREEN = None


@dataclass
class ClickTarget:
    kind: str
    value: int | str
    top: int
    left: int
    bottom: int
    right: int

    def contains(self, y: int, x: int) -> bool:
        return self.top <= y <= self.bottom and self.left <= x <= self.right


@dataclass
class TuiState:
    selected_command: int = 0
    selected_field: int = 0
    message: str = "Arrows navigate, Enter edits or activates, Tab moves, PgUp/PgDn scroll results, q quits."
    output: str = help_text()
    output_scroll: int = 0
    focus: str = "menu"
    last_exit_code: int | None = None
    click_targets: list[ClickTarget] = field(default_factory=list)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deploybot-tui",
        description="Run DeployBot through a terminal UI.",
    )
    parser.add_argument("--plain", action="store_true", help="use a prompt-based terminal UI instead of curses")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace_dir = Path.cwd()
    if args.plain or not sys.stdin.isatty() or not sys.stdout.isatty():
        return run_plain_tui(workspace_dir=workspace_dir)
    return curses.wrapper(lambda stdscr: run_curses_tui(stdscr, workspace_dir))


def run_plain_tui(workspace_dir: Path) -> int:
    print(TITLE)
    print("Type a command name or number. Press Ctrl-D or enter q to exit.")

    while True:
        _print_command_menu()
        try:
            selection = input("Command: ").strip()
        except EOFError:
            print()
            return 0
        if not selection or selection.lower() in {"q", "quit", "exit"}:
            return 0

        command_name = _resolve_selection(selection)
        if command_name is None:
            print(f"Unknown command selection: {selection}")
            continue

        raw_values: dict[str, str] = {}
        spec = COMMAND_SPEC_BY_NAME[command_name]
        for field in spec.fields:
            raw_values[field.name] = input(f"{field.prompt}: ")

        try:
            values = coerce_command_inputs(command_name, raw_values)
        except ValueError as exc:
            print(str(exc))
            continue

        result = execute_command(command_name, values, workspace_dir)
        if result.output:
            print(result.output, end="" if result.output.endswith("\n") else "\n")
        print(f"[exit {result.exit_code}]")


def _print_command_menu() -> None:
    print("Commands:")
    for index, spec in enumerate(COMMAND_SPECS, start=1):
        print(f"  {index}. {spec.name} - {spec.help_text}")


def _resolve_selection(selection: str) -> str | None:
    normalized = selection.strip()
    if normalized in COMMAND_SPEC_BY_NAME:
        return normalized
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(COMMAND_SPECS):
            return COMMAND_SPECS[index].name
    return None


def run_curses_tui(stdscr, workspace_dir: Path) -> int:
    global ACTIVE_SCREEN
    ACTIVE_SCREEN = stdscr
    _initialize_curses(stdscr)
    state = TuiState()
    field_values = {spec.name: [field.default for field in spec.fields] for spec in COMMAND_SPECS}

    while True:
        _render_screen(stdscr, state, field_values)
        key = stdscr.get_wch()
        result = _handle_key(stdscr, key, state, field_values, workspace_dir)
        if result is not None:
            return result


def _initialize_curses(stdscr) -> None:
    _safe_curs_set(0)
    try:
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        curses.mouseinterval(0)
    except curses.error:
        pass
    stdscr.keypad(True)
    if curses.has_colors():
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
            curses.init_pair(3, curses.COLOR_GREEN, -1)
            curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(5, curses.COLOR_MAGENTA, -1)
            curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)
        except curses.error:
            pass


def _handle_key(stdscr, key, state: TuiState, field_values: dict[str, list[str]], workspace_dir: Path) -> int | None:
    spec = COMMAND_SPECS[state.selected_command]
    field_count = len(spec.fields)

    if key in {"q", "Q"}:
        return 0
    if key == curses.KEY_RESIZE:
        return None
    if key == curses.KEY_MOUSE:
        _handle_mouse(stdscr, state, field_values, workspace_dir)
        return None
    if key in ("\t", curses.KEY_BTAB):
        _cycle_focus(state, backward=(key == curses.KEY_BTAB))
        return None
    if key in (curses.KEY_UP, "k"):
        _move_up(state, field_count)
        return None
    if key in (curses.KEY_DOWN, "j"):
        _move_down(state, field_count)
        return None
    if key == curses.KEY_LEFT:
        _move_left(state)
        return None
    if key == curses.KEY_RIGHT:
        _move_right(state, field_count)
        return None
    if key == curses.KEY_PPAGE:
        _scroll_output(state, -5)
        return None
    if key == curses.KEY_NPAGE:
        _scroll_output(state, 5)
        return None
    if key == curses.KEY_F1:
        state.focus = "buttons"
        state.selected_field = 0
        _activate_button(state, field_values, workspace_dir)
        return None
    if key == curses.KEY_F2:
        state.focus = "buttons"
        state.selected_field = 1
        _activate_button(state, field_values, workspace_dir)
        return None
    if key == curses.KEY_F3:
        state.focus = "buttons"
        state.selected_field = 2
        _activate_button(state, field_values, workspace_dir)
        return None
    if key in ("\n", curses.KEY_ENTER, "\r"):
        _activate_focus(stdscr, state, field_values, workspace_dir)
        return None
    if key in (" ",) and state.focus == "buttons":
        _activate_focus(stdscr, state, field_values, workspace_dir)
        return None
    if key == curses.KEY_BACKSPACE:
        if state.focus == "fields" and state.selected_field < field_count:
            field_values[spec.name][state.selected_field] = field_values[spec.name][state.selected_field][:-1]
        return None
    if isinstance(key, str) and key.isprintable():
        if state.focus == "menu":
            _jump_to_command_by_letter(state, key)
        elif state.focus == "fields" and state.selected_field < field_count:
            field_values[spec.name][state.selected_field] += key
        elif state.focus == "output":
            if key == "g":
                state.output_scroll = 0
            elif key == "G":
                state.output_scroll = max(0, len(state.output.splitlines()) - 1)
        return None
    return None


def _cycle_focus(state: TuiState, backward: bool = False) -> None:
    order = ["menu", "fields", "buttons", "output"]
    index = order.index(state.focus)
    state.focus = order[(index - 1 if backward else index + 1) % len(order)]


def _move_up(state: TuiState, field_count: int) -> None:
    if state.focus == "menu":
        state.selected_command = (state.selected_command - 1) % len(COMMAND_SPECS)
        state.selected_field = 0
    elif state.focus == "fields":
        state.selected_field = max(0, state.selected_field - 1)
    elif state.focus == "buttons":
        state.focus = "fields"
        state.selected_field = max(0, field_count - 1)
    elif state.focus == "output":
        _scroll_output(state, -1)


def _move_down(state: TuiState, field_count: int) -> None:
    if state.focus == "menu":
        state.selected_command = (state.selected_command + 1) % len(COMMAND_SPECS)
        state.selected_field = 0
    elif state.focus == "fields":
        if field_count == 0:
            state.focus = "buttons"
            state.selected_field = 0
        elif state.selected_field < field_count - 1:
            state.selected_field += 1
        else:
            state.focus = "buttons"
            state.selected_field = 0
    elif state.focus == "buttons":
        state.focus = "output"
    elif state.focus == "output":
        _scroll_output(state, 1)


def _move_left(state: TuiState) -> None:
    if state.focus == "fields":
        state.focus = "menu"
    elif state.focus == "buttons":
        state.selected_field = max(0, state.selected_field - 1)
    elif state.focus == "output":
        state.focus = "buttons"


def _move_right(state: TuiState, field_count: int) -> None:
    if state.focus == "menu":
        state.focus = "fields" if field_count > 0 else "buttons"
        state.selected_field = 0
    elif state.focus == "fields":
        state.focus = "buttons"
        state.selected_field = 0
    elif state.focus == "buttons":
        state.selected_field = min(len(BUTTON_LABELS) - 1, state.selected_field + 1)


def _jump_to_command_by_letter(state: TuiState, key: str) -> None:
    lowered = key.lower()
    for index, spec in enumerate(COMMAND_SPECS):
        if spec.name.startswith(lowered):
            state.selected_command = index
            state.selected_field = 0
            return


def _activate_focus(stdscr, state: TuiState, field_values: dict[str, list[str]], workspace_dir: Path) -> None:
    spec = COMMAND_SPECS[state.selected_command]
    if state.focus == "menu":
        state.focus = "fields" if spec.fields else "buttons"
        state.selected_field = 0
        return
    if state.focus == "fields":
        _edit_current_field(stdscr, state, field_values)
        return
    if state.focus == "buttons":
        _activate_button(state, field_values, workspace_dir)
        return


def _activate_button(state: TuiState, field_values: dict[str, list[str]], workspace_dir: Path) -> None:
    action = BUTTON_LABELS[min(state.selected_field, len(BUTTON_LABELS) - 1)]
    if action == "Run":
        _run_selected_command(state, field_values, workspace_dir)
    elif action == "Clear":
        state.output = "Output cleared."
        state.output_scroll = 0
        state.message = "Cleared the lower output panel."
    elif action == "Help":
        state.output = help_text()
        state.output_scroll = 0
        state.message = "Loaded command help into the output panel."


def _handle_mouse(stdscr, state: TuiState, field_values: dict[str, list[str]], workspace_dir: Path) -> None:
    try:
        _device_id, x, y, _z, button_state = curses.getmouse()
    except curses.error:
        return

    if BUTTON4_MASK and button_state & BUTTON4_MASK:
        _scroll_output(state, -3)
        return
    if BUTTON5_MASK and button_state & BUTTON5_MASK:
        _scroll_output(state, 3)
        return
    if not (button_state & BUTTON1_MASK):
        return

    for target in state.click_targets:
        if not target.contains(y, x):
            continue
        if target.kind == "menu":
            state.focus = "menu"
            state.selected_command = int(target.value)
            state.selected_field = 0
            return
        if target.kind == "field":
            state.focus = "fields"
            state.selected_field = int(target.value)
            _edit_current_field(stdscr, state, field_values)
            return
        if target.kind == "button":
            state.focus = "buttons"
            state.selected_field = int(target.value)
            _activate_button(state, field_values, workspace_dir)
            return
        if target.kind == "output":
            state.focus = "output"
            return


def _render_screen(stdscr, state: TuiState, field_values: dict[str, list[str]]) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    state.click_targets = []

    if height < MIN_HEIGHT or width < MIN_WIDTH:
        message = f"Resize terminal to at least {MIN_WIDTH}x{MIN_HEIGHT}. Current size: {width}x{height}"
        _safe_addstr(stdscr, 0, 0, TITLE, _attr_header())
        _safe_addstr(stdscr, 2, 2, message)
        stdscr.refresh()
        return

    menu_width = MENU_WIDTH
    header_height = 3
    footer_height = 2
    output_height = max(10, height // 3)
    main_top = header_height
    content_bottom = height - footer_height
    output_top = content_bottom - output_height

    _draw_header(stdscr, width, state)
    _draw_footer(stdscr, height, width, state)

    menu_win = stdscr.derwin(output_top - main_top, menu_width, main_top, 0)
    main_win = stdscr.derwin(output_top - main_top, width - menu_width, main_top, menu_width)
    output_win = stdscr.derwin(output_height, width, output_top, 0)

    _draw_menu(menu_win, state)
    _draw_main(main_win, state, field_values)
    _draw_output(output_win, state)
    stdscr.refresh()


def _draw_header(stdscr, width: int, state: TuiState) -> None:
    spec = COMMAND_SPECS[state.selected_command]
    header = f" {TITLE} "
    status = f" active:{spec.name} "
    _safe_addstr(stdscr, 0, 1, header, _attr_header())
    _safe_hline(stdscr, 1, 0, width, curses.ACS_HLINE, _attr_border())
    _safe_addstr(stdscr, 0, max(1, width - len(status) - 2), status, _attr_accent())
    _safe_addstr(stdscr, 2, 1, state.message[: max(1, width - 3)], _attr_dim())


def _draw_footer(stdscr, height: int, width: int, state: TuiState) -> None:
    footer_row = height - 1
    _safe_hline(stdscr, footer_row - 1, 0, width, curses.ACS_HLINE, _attr_border())
    footer = " F1 Run  F2 Clear  F3 Help  Mouse select/edit  PgUp/PgDn scroll  q Quit "
    _safe_addstr(stdscr, footer_row, 1, footer[: max(1, width - 2)], _attr_footer())
    if state.last_exit_code is not None:
        exit_badge = f"[exit {state.last_exit_code}]"
        _safe_addstr(stdscr, footer_row, max(1, width - len(exit_badge) - 2), exit_badge, _attr_status(state.last_exit_code))


def _draw_menu(menu_win, state: TuiState) -> None:
    menu_win.erase()
    _draw_box(menu_win, " Menu ", active=(state.focus == "menu"))
    inner_height, inner_width = menu_win.getmaxyx()

    for index, spec in enumerate(COMMAND_SPECS):
        row = 2 + index
        if row >= inner_height - 2:
            break
        selected = index == state.selected_command
        attr = _attr_selected() if selected else _attr_normal()
        marker = ">" if selected else " "
        label = f"{marker} {spec.name}"
        _safe_addstr(menu_win, row, 2, label[: max(1, inner_width - 4)], attr)
        abs_y, abs_x = _abs_coords(menu_win, row, 1)
        state.click_targets.append(
            ClickTarget("menu", index, abs_y, abs_x, abs_y, abs_x + max(1, inner_width - 3))
        )


def _draw_main(main_win, state: TuiState, field_values: dict[str, list[str]]) -> None:
    main_win.erase()
    _draw_box(main_win, " Workspace ", active=(state.focus in {"fields", "buttons"}))
    height, width = main_win.getmaxyx()
    spec = COMMAND_SPECS[state.selected_command]

    summary_height = min(9, max(8, height // 3))
    summary_width = max(28, width // 2)
    fields_width = width - summary_width

    summary_win = main_win.derwin(summary_height, summary_width, 1, 1)
    form_win = main_win.derwin(summary_height, fields_width - 1, 1, summary_width)
    details_top = 1 + summary_height
    details_height = height - details_top - 1
    details_win = main_win.derwin(details_height, width - 2, details_top, 1)

    _draw_summary(summary_win, state)
    _draw_form(form_win, state, field_values)
    _draw_details(details_win, spec)


def _draw_summary(summary_win, state: TuiState) -> None:
    summary_win.erase()
    _draw_box(summary_win, " Command ", active=False)
    spec = COMMAND_SPECS[state.selected_command]
    lines = [
        f"Name: {spec.name}",
        f"Fields: {len(spec.fields)}",
        f"Focus: {state.focus}",
        f"Last exit: {'-' if state.last_exit_code is None else state.last_exit_code}",
    ]
    for index, line in enumerate(lines, start=2):
        _safe_addstr(summary_win, index, 2, line, _attr_accent() if index == 2 else _attr_normal())
    progress = _meter(len(spec.fields), 6)
    _safe_addstr(summary_win, 6, 2, f"Form: {progress}", _attr_success())


def _draw_form(form_win, state: TuiState, field_values: dict[str, list[str]]) -> None:
    form_win.erase()
    _draw_box(form_win, " Inputs ", active=(state.focus in {"fields", "buttons"}))
    height, width = form_win.getmaxyx()
    spec = COMMAND_SPECS[state.selected_command]

    for index, field in enumerate(spec.fields):
        row = 2 + index
        if row >= height - 4:
            break
        value = field_values[spec.name][index]
        if field.secret and value:
            value = "*" * len(value)
        prefix = ">" if state.focus == "fields" and state.selected_field == index else " "
        label = f"{prefix} {field.prompt}"
        _safe_addstr(form_win, row, 2, label[: max(1, width - 4)], _attr_selected() if prefix == ">" else _attr_normal())
        _safe_addstr(form_win, row + 1, 4, value[: max(1, width - 8)], _attr_dim())
        abs_y, abs_x = _abs_coords(form_win, row, 1)
        state.click_targets.append(
            ClickTarget("field", index, abs_y, abs_x, abs_y + 1, abs_x + max(1, width - 3))
        )

    button_row = max(2, height - 3)
    button_x = 2
    for index, label in enumerate(BUTTON_LABELS):
        highlighted = state.focus == "buttons" and state.selected_field == index
        button = f"[ {label} ]"
        attr = _attr_button(highlighted)
        _safe_addstr(form_win, button_row, button_x, button, attr)
        abs_y, abs_x = _abs_coords(form_win, button_row, button_x)
        state.click_targets.append(
            ClickTarget("button", index, abs_y, abs_x, abs_y, abs_x + len(button) - 1)
        )
        button_x += len(button) + 2


def _draw_details(details_win, spec) -> None:
    details_win.erase()
    _draw_box(details_win, " Notes ", active=False)
    lines = _wrap_lines(spec.help_text, max(20, details_win.getmaxyx()[1] - 4))
    _safe_addstr(details_win, 2, 2, "The TUI reuses the same command engine as the CLI.", _attr_normal())
    _safe_addstr(details_win, 3, 2, "Edit values in the upper-right panel, then press Run.", _attr_normal())
    for index, line in enumerate(lines, start=5):
        if index >= details_win.getmaxyx()[0] - 1:
            break
        _safe_addstr(details_win, index, 2, line, _attr_dim())


def _draw_output(output_win, state: TuiState) -> None:
    output_win.erase()
    _draw_box(output_win, " Results ", active=(state.focus == "output"))
    height, width = output_win.getmaxyx()
    lines = state.output.splitlines() or [""]
    body_height = max(1, height - 3)
    max_scroll = max(0, len(lines) - body_height)
    state.output_scroll = min(max_scroll, max(0, state.output_scroll))
    start = state.output_scroll
    visible_lines = lines[start : start + body_height]

    for index, line in enumerate(visible_lines, start=1):
        _safe_addstr(output_win, index, 2, line[: max(1, width - 4)], _attr_normal())

    _draw_scrollbar(output_win, start, body_height, len(lines))
    abs_y, abs_x = _abs_coords(output_win, 1, 1)
    state.click_targets.append(
        ClickTarget("output", "output", abs_y, abs_x, abs_y + height - 3, abs_x + width - 3)
    )


def _draw_scrollbar(win, start: int, body_height: int, total_lines: int) -> None:
    height, width = win.getmaxyx()
    if total_lines <= body_height:
        return
    rail_height = body_height
    thumb_size = max(1, rail_height * body_height // total_lines)
    max_scroll = max(1, total_lines - body_height)
    thumb_top = 1 + ((rail_height - thumb_size) * start // max_scroll)
    for offset in range(rail_height):
        attr = _attr_dim()
        char = curses.ACS_VLINE
        if thumb_top - 1 <= offset < thumb_top - 1 + thumb_size:
            attr = _attr_accent()
            char = curses.ACS_CKBOARD
        _safe_addch(win, 1 + offset, width - 2, char, attr)


def _run_selected_command(state: TuiState, field_values: dict[str, list[str]], workspace_dir: Path) -> None:
    spec = COMMAND_SPECS[state.selected_command]
    raw_values = {field.name: field_values[spec.name][index] for index, field in enumerate(spec.fields)}
    for index, field in enumerate(spec.fields):
        if field.name == "username" and not raw_values[field.name].strip():
            typed = _prompt_for_value(ACTIVE_SCREEN, "Username", "", secret=False)
            if typed is None:
                state.message = f"Cancelled {spec.name}."
                return
            raw_values[field.name] = typed
            field_values[spec.name][index] = typed
        if field.name == "password" and not raw_values[field.name]:
            typed = _prompt_for_value(ACTIVE_SCREEN, "Password", "", secret=True)
            if typed is None:
                state.message = f"Cancelled {spec.name}."
                return
            raw_values[field.name] = typed
            field_values[spec.name][index] = typed
    try:
        values = coerce_command_inputs(spec.name, raw_values)
    except ValueError as exc:
        state.message = f"Unable to run {spec.name}."
        state.output = str(exc)
        state.output_scroll = 0
        state.last_exit_code = 1
        return

    result = _run_command_with_waiting_modal(spec.name, values, workspace_dir)
    if result is None:
        state.message = f"{spec.name} did not complete."
        state.output = "The command was interrupted before a result was returned."
        state.output_scroll = 0
        state.last_exit_code = 1
        return
    state.message = f"Ran {spec.name} with exit code {result.exit_code}."
    state.output = result.output or f"[exit {result.exit_code}]"
    state.output_scroll = 0
    state.last_exit_code = result.exit_code


def _edit_current_field(stdscr, state: TuiState, field_values: dict[str, list[str]] | None) -> None:
    if stdscr is None or field_values is None:
        return
    spec = COMMAND_SPECS[state.selected_command]
    if state.selected_field >= len(spec.fields):
        return

    field = spec.fields[state.selected_field]
    current = field_values[spec.name][state.selected_field]
    typed = _prompt_for_value(stdscr, field.prompt, current, secret=field.secret)
    if typed is not None:
        field_values[spec.name][state.selected_field] = typed
        state.message = f"Updated {field.prompt.lower()}."


def _prompt_for_value(stdscr, prompt: str, initial: str, secret: bool = False) -> str | None:
    height, width = stdscr.getmaxyx()
    box_height = 7
    box_width = min(max(50, len(prompt) + 14), width - 6)
    top = max(2, (height - box_height) // 2)
    left = max(3, (width - box_width) // 2)

    win = stdscr.derwin(box_height, box_width, top, left)
    win.keypad(True)
    _draw_box(win, f" {prompt} ", active=True)
    _safe_addstr(win, 1, 2, "Enter to save, Esc to cancel", _attr_dim())

    edit_win = win.derwin(1, box_width - 6, 3, 3)
    edit_win.erase()
    if secret and initial:
        _safe_addstr(edit_win, 0, 0, "*" * min(len(initial), box_width - 7))
    else:
        _safe_addstr(edit_win, 0, 0, initial[: max(1, box_width - 7)])
    stdscr.refresh()
    win.refresh()
    edit_win.refresh()

    value = _read_popup_value(win, edit_win, initial, secret=secret)
    return value


def _show_waiting_modal(title: str, lines: tuple[str, ...]) -> None:
    stdscr = ACTIVE_SCREEN
    if stdscr is None:
        return

    height, width = stdscr.getmaxyx()
    box_height = max(7, len(lines) + 4)
    content_width = max((len(line) for line in lines), default=0)
    box_width = min(max(42, content_width + 6), max(20, width - 6))
    top = max(1, (height - box_height) // 2)
    left = max(2, (width - box_width) // 2)

    try:
        win = stdscr.derwin(box_height, box_width, top, left)
        win.erase()
        _draw_box(win, title, active=True)
        for index, line in enumerate(lines, start=2):
            _safe_addstr(win, index, 3, line[: max(1, box_width - 6)], _attr_normal())
        _safe_addstr(win, box_height - 2, 3, "UI is temporarily locked until the command completes.", _attr_dim())
        win.refresh()
        stdscr.refresh()
        curses.doupdate()
    except curses.error:
        return


def _run_command_with_waiting_modal(command_name: str, values: dict[str, object], workspace_dir: Path):
    result_box: dict[str, object] = {}

    def worker() -> None:
        try:
            result_box["result"] = execute_command(command_name, values, workspace_dir)
        except Exception as exc:  # pragma: no cover - defensive guard for TUI runtime
            result_box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    tick = 0
    while thread.is_alive():
        dots = "." * ((tick % 3) + 1)
        _show_waiting_modal(
            title=" Waiting ",
            lines=(
                f"Running {command_name}{dots}",
                "Please wait while DeployBot completes this action.",
            ),
        )
        tick += 1
        time.sleep(0.25)
    thread.join()

    if "error" in result_box:
        raise result_box["error"]  # surface unexpected failures instead of swallowing them
    return result_box.get("result")


def _read_popup_value(parent_win, edit_win, initial: str, secret: bool) -> str | None:
    _safe_curs_set(1)
    chars = list(initial)
    while True:
        edit_win.erase()
        display = "*" * len(chars) if secret else "".join(chars)
        _safe_addstr(edit_win, 0, 0, display[: max(1, edit_win.getmaxyx()[1] - 1)])
        edit_win.move(0, min(len(chars), edit_win.getmaxyx()[1] - 1))
        parent_win.refresh()
        edit_win.refresh()
        key = edit_win.get_wch()
        if key in ("\n", "\r", curses.KEY_ENTER):
            _safe_curs_set(0)
            return "".join(chars)
        if key == "\x1b":
            _safe_curs_set(0)
            return None
        if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
            if chars:
                chars.pop()
            continue
        if isinstance(key, str) and key.isprintable():
            chars.append(key)


def _scroll_output(state: TuiState, delta: int) -> None:
    state.output_scroll = max(0, state.output_scroll + delta)


def _wrap_lines(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        proposal = f"{current} {word}"
        if len(proposal) <= width:
            current = proposal
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _meter(value: int, width: int) -> str:
    filled = min(width, max(1, value))
    return "[" + ("#" * filled).ljust(width, ".") + "]"


def _draw_box(win, title: str, active: bool) -> None:
    attr = _attr_border(active)
    height, width = win.getmaxyx()
    if height < 2 or width < 2:
        return
    for x in range(max(0, width - 1)):
        _safe_addch(win, 0, x, curses.ACS_HLINE, attr)
        _safe_addch(win, height - 1, x, curses.ACS_HLINE, attr)
    for y in range(max(0, height - 1)):
        _safe_addch(win, y, 0, curses.ACS_VLINE, attr)
        _safe_addch(win, y, width - 1, curses.ACS_VLINE, attr)
    _safe_addch(win, 0, 0, curses.ACS_ULCORNER, attr)
    _safe_addch(win, 0, width - 1, curses.ACS_URCORNER, attr)
    _safe_addch(win, height - 1, 0, curses.ACS_LLCORNER, attr)
    _safe_addch(win, height - 1, width - 1, curses.ACS_LRCORNER, attr)
    _safe_addstr(win, 0, 2, title[: max(1, width - 4)], attr | curses.A_BOLD)


def _abs_coords(win, y: int, x: int) -> tuple[int, int]:
    origin_y, origin_x = win.getbegyx()
    return origin_y + y, origin_x + x


def _safe_addstr(win, row: int, col: int, text: str, attr: int = 0) -> None:
    height, width = win.getmaxyx()
    if row < 0 or col < 0 or row >= height or col >= width:
        return
    clipped = text[: max(0, width - col - 1)]
    if not clipped:
        return
    try:
        win.addstr(row, col, clipped, attr)
    except curses.error:
        return


def _safe_addch(win, row: int, col: int, ch, attr: int = 0) -> None:
    height, width = win.getmaxyx()
    if row < 0 or col < 0 or row >= height or col >= width:
        return
    try:
        win.addch(row, col, ch, attr)
    except curses.error:
        return


def _safe_hline(win, row: int, col: int, count: int, ch, attr: int = 0) -> None:
    height, width = win.getmaxyx()
    if row < 0 or row >= height or col >= width:
        return
    safe_count = max(0, min(count, width - col - 1))
    if safe_count <= 0:
        return
    try:
        win.hline(row, col, ch, safe_count, attr)
    except curses.error:
        return


def _safe_curs_set(visibility: int) -> None:
    try:
        curses.curs_set(visibility)
    except curses.error:
        return


def _attr_border(active: bool = False) -> int:
    if curses.has_colors():
        return curses.color_pair(1 if active else 5)
    return curses.A_BOLD if active else curses.A_NORMAL


def _attr_header() -> int:
    if curses.has_colors():
        return curses.color_pair(2) | curses.A_BOLD
    return curses.A_BOLD


def _attr_footer() -> int:
    if curses.has_colors():
        return curses.color_pair(4) | curses.A_BOLD
    return curses.A_REVERSE


def _attr_selected() -> int:
    if curses.has_colors():
        return curses.color_pair(6) | curses.A_BOLD
    return curses.A_REVERSE


def _attr_button(active: bool) -> int:
    if active:
        return _attr_selected()
    if curses.has_colors():
        return curses.color_pair(1) | curses.A_BOLD
    return curses.A_BOLD


def _attr_status(exit_code: int) -> int:
    if curses.has_colors():
        return curses.color_pair(3 if exit_code == 0 else 2) | curses.A_BOLD
    return curses.A_BOLD


def _attr_success() -> int:
    if curses.has_colors():
        return curses.color_pair(3)
    return curses.A_NORMAL


def _attr_accent() -> int:
    if curses.has_colors():
        return curses.color_pair(1) | curses.A_BOLD
    return curses.A_BOLD


def _attr_dim() -> int:
    return curses.A_DIM


def _attr_normal() -> int:
    return curses.A_NORMAL
