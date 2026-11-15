"""Конфигурация: пути к реплеям, база, порт."""

from __future__ import annotations

import json
import os
import winreg

from . import paths

PROJECT_DIR = paths.PROJECT_DIR
CONFIG_PATH = paths.user_file("config.json")
DB_PATH = paths.user_file("mtstats.db")

DEFAULTS = {
    "replays": [],
    "json_dirs": [],
    "db": "data/mtstats.db",
    "host": "127.0.0.1",
    "port": 8765,
    "open_browser": True,
}


def _registry_install_locations() -> list[str]:
    """Пути установки клиента из реестра (Lesta / Мir Tankov)."""
    found: list[str] = []
    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, path in roots:
        try:
            with winreg.OpenKey(hive, path) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, sub) as entry:
                            name = str(winreg.QueryValueEx(entry, "DisplayName")[0]).lower()
                            if "танк" not in name and "tank" not in name:
                                continue
                            location = str(winreg.QueryValueEx(entry, "InstallLocation")[0])
                            if location:
                                found.append(location)
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def detect_replay_folders() -> list[str]:
    candidates: list[str] = []
    candidates.append(os.path.join(PROJECT_DIR, "replays"))
    candidates.append(os.path.join(os.path.dirname(PROJECT_DIR), "MT repley"))
    for base in _registry_install_locations():
        candidates.append(os.path.join(base, "replays"))
    for base in (r"C:\Games\Tanki", r"C:\Games\World_of_Tanks_RU", r"D:\Games\Tanki"):
        candidates.append(os.path.join(base, "replays"))
    unique: list[str] = []
    seen = set()
    for path in candidates:
        if not os.path.isdir(path):
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        unique.append(os.path.abspath(path))
    return unique


def detect_json_folders(replay_folders: list[str]) -> list[str]:
    """Папки battle_results модов рядом с клиентом (lesta_replays_upload и др.).

    Мод сохраняет JSON с результатами каждого боя даже тогда, когда сам реплей
    не записался, поэтому такие папки заметно улучшают полноту статистики.
    """
    found: list[str] = []
    for folder in replay_folders or []:
        root = os.path.dirname(os.path.abspath(folder))
        mods = os.path.join(root, "mods", "configs")
        if not os.path.isdir(mods):
            continue
        try:
            names = sorted(os.listdir(mods))
        except OSError:
            continue
        for name in names:
            candidate = os.path.join(mods, name, "battle_results")
            if os.path.isdir(candidate):
                found.append(os.path.abspath(candidate))
    return found


def load() -> dict:
    paths.migrate_legacy()
    config = dict(DEFAULTS)
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                config.update(json.load(fh))
        except (OSError, json.JSONDecodeError):
            pass
    if not config.get("replays"):
        config["replays"] = detect_replay_folders()
    if not config.get("json_dirs"):
        config["json_dirs"] = detect_json_folders(config["replays"])
    # база всегда в профиле пользователя — так программа работает и из Program Files
    config["db"] = paths.user_file("mtstats.db")
    return config


def save(config: dict) -> None:
    data = {
        "replays": config.get("replays", []),
        "json_dirs": config.get("json_dirs", []),
        "db": os.path.relpath(config["db"], PROJECT_DIR).replace("\\", "/"),
        "host": config.get("host", "127.0.0.1"),
        "port": int(config.get("port", 8765)),
        "open_browser": bool(config.get("open_browser", True)),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
