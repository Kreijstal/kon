from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
from pathlib import Path

KON_THEME_TO_GHOSTTY_THEME = {
    "ayu": "Ayu",
    "catppuccin-frappe": "Catppuccin Frappe",
    "catppuccin-latte": "Catppuccin Latte",
    "catppuccin-macchiato": "Catppuccin Macchiato",
    "catppuccin-mocha": "Catppuccin Mocha",
    "dracula": "Dracula",
    "everforest": "Everforest Dark Hard",
    "flexoki": "Flexoki Dark",
    "github-dark": "GitHub Dark",
    "github-light": "GitHub Light Default",
    "gruvbox-dark": "Gruvbox Dark",
    "gruvbox-light": "Gruvbox Light",
    "kanagawa": "Kanagawa Wave",
    "kanagawa-dragon": "Kanagawa Dragon",
    "monokai": "Monokai Classic",
    "nightowl": "Night Owl",
    "nord": "Nord",
    "one-dark": "Atom One Dark",
    "one-light": "Atom One Light",
    "osaka-jade": "Solarized Osaka Night",
    "palenight": "Pale Night Hc",
    "rosepine": "Rose Pine",
    "solarized-dark": "Solarized Dark Higher Contrast",
    "solarized-light": "iTerm2 Solarized Light",
    "tokyo-day": "TokyoNight Day",
    "tokyo-night": "TokyoNight Night",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select one theme and apply it to both Kon and Ghostty."
    )
    parser.add_argument("theme", nargs="?", help="Kon theme ID (prompts when omitted).")
    parser.add_argument(
        "--list", action="store_true", help="List matched themes without changing config."
    )
    parser.add_argument(
        "--ghostty-config", type=Path, default=Path.home() / ".config/ghostty/config"
    )
    parser.add_argument("--kon-config", type=Path, default=Path.home() / ".config/kon/config.toml")
    return parser.parse_args()


def list_ghostty_themes() -> set[str]:
    if shutil.which("ghostty") is None:
        raise RuntimeError("ghostty is not installed or is not on PATH")
    result = subprocess.run(
        ["ghostty", "+list-themes"], check=True, capture_output=True, text=True
    )
    suffix = "(resources)"
    return {
        line.strip()[: -len(suffix)].rstrip() if line.strip().endswith(suffix) else line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }


def replace_setting(config_text: str, key: str, value: str) -> str:
    lines = config_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        if stripped.partition("=")[0].strip() == key:
            lines[index] = f"{key} = {value}"
            return "\n".join(lines) + "\n"
    separator = "" if not config_text or config_text.endswith("\n") else "\n"
    return f"{config_text}{separator}{key} = {value}\n"


def replace_kon_theme(config_text: str, theme_name: str) -> str:
    lines = config_text.splitlines()
    in_ui = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_ui:
                lines.insert(index, f'theme = "{theme_name}"')
                return "\n".join(lines) + "\n"
            in_ui = stripped == "[ui]"
        elif in_ui and stripped.partition("=")[0].strip() == "theme":
            lines[index] = f'theme = "{theme_name}"'
            return "\n".join(lines) + "\n"
    if in_ui:
        lines.append(f'theme = "{theme_name}"')
        return "\n".join(lines) + "\n"
    separator = "" if not config_text or config_text.endswith("\n") else "\n"
    return f'{config_text}{separator}\n[ui]\ntheme = "{theme_name}"\n'


def get_kon_theme_ids() -> list[str]:
    themes_path = Path(__file__).resolve().parents[1] / "src/kon/themes.py"
    module = ast.parse(themes_path.read_text(encoding="utf-8"), filename=str(themes_path))
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "THEME_ORDER" for target in node.targets
        ):
            themes = ast.literal_eval(node.value)
            if isinstance(themes, list) and all(isinstance(theme, str) for theme in themes):
                return themes
    raise RuntimeError(f"Could not read THEME_ORDER from {themes_path}")


def matched_themes(available: set[str]) -> list[tuple[str, str]]:
    supported = get_kon_theme_ids()
    missing_mappings = set(supported) - KON_THEME_TO_GHOSTTY_THEME.keys()
    if missing_mappings:
        raise RuntimeError(
            f"Kon themes without Ghostty mappings: {', '.join(sorted(missing_mappings))}"
        )
    return [
        (theme, KON_THEME_TO_GHOSTTY_THEME[theme])
        for theme in supported
        if KON_THEME_TO_GHOSTTY_THEME[theme] in available
    ]


def print_themes(themes: list[tuple[str, str]]) -> None:
    width = max(len(kon) for kon, _ in themes)
    for index, (kon, ghostty) in enumerate(themes, 1):
        print(f"{index:2}. {kon:<{width}}  Ghostty: {ghostty}")


def choose_theme(themes: list[tuple[str, str]]) -> tuple[str, str]:
    print_themes(themes)
    while True:
        choice = input("Select a theme by number or Kon theme ID: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(themes):
            return themes[int(choice) - 1]
        for pair in themes:
            if choice == pair[0]:
                return pair
        print("Invalid selection.", file=sys.stderr)


def write_configs(kon_path: Path, ghostty_path: Path, kon: str, ghostty: str) -> None:
    kon_path.parent.mkdir(parents=True, exist_ok=True)
    ghostty_path.parent.mkdir(parents=True, exist_ok=True)
    kon_text = kon_path.read_text(encoding="utf-8") if kon_path.exists() else ""
    ghostty_text = ghostty_path.read_text(encoding="utf-8") if ghostty_path.exists() else ""
    kon_path.write_text(replace_kon_theme(kon_text, kon), encoding="utf-8")
    ghostty_path.write_text(replace_setting(ghostty_text, "theme", ghostty), encoding="utf-8")


def main() -> int:
    args = parse_args()
    themes = matched_themes(list_ghostty_themes())
    if not themes:
        raise RuntimeError("No shared Kon/Ghostty themes were found")
    if args.list:
        print_themes(themes)
        return 0

    if args.theme:
        selected = next((pair for pair in themes if pair[0] == args.theme), None)
        if selected is None:
            raise ValueError(f"Theme is not supported by both Kon and Ghostty: {args.theme}")
    else:
        selected = choose_theme(themes)

    kon, ghostty = selected
    write_configs(args.kon_config.expanduser(), args.ghostty_config.expanduser(), kon, ghostty)
    print(f"Applied Kon theme '{kon}' and Ghostty theme '{ghostty}'.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt as exc:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130) from exc
