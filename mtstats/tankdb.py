"""Справочник техники: уровень и класс из файлов клиента.

Файл `data/tank_db.json` собирается скриптом `tools/build_tank_db.py`
по `res/packages/scripts.pkg`. Если файла нет, справочник пуст — статистика
продолжает работать, просто без уровня и класса.
"""

from __future__ import annotations

import json
import os

from . import paths

DB_PATH = paths.resource(os.path.join("data", "tank_db.json"))
USER_PATH = os.path.join(paths.user_dir(), "assets", "tank_db.json")

CLASS_RU = {
    "heavyTank": "ТТ",
    "mediumTank": "СТ",
    "lightTank": "ЛТ",
    "AT-SPG": "ПТ-САУ",
    "SPG": "САУ",
}

_cache: dict | None = None


def load() -> dict:
    global _cache
    if _cache is None:
        _cache = {}
        path = USER_PATH if os.path.isfile(USER_PATH) else DB_PATH
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    _cache = json.load(fh)
            except (OSError, json.JSONDecodeError):
                _cache = {}
    return _cache


def lookup(vehicle_id: str) -> dict | None:
    """Уровень и класс по идентификатору танка (GB92_FV217).

    В реплеях встречаются «скиновые» варианты вида
    `F18_Bat_Chatillon25t_hound_TLXXL`, которых нет в списке клиента,
    поэтому пробуем отрезать хвосты по подчёркиваниям.
    """
    if not vehicle_id:
        return None
    data = load()
    key = vehicle_id.lower()
    if key in data:
        return data[key]
    parts = key.split("_")
    for size in range(len(parts) - 1, 1, -1):
        candidate = "_".join(parts[:size])
        if candidate in data:
            return data[candidate]
    return None


def tier_class(vehicle_id: str) -> tuple[int | None, str | None]:
    item = lookup(vehicle_id)
    if not item:
        return None, None
    return item.get("tier"), item.get("class")


def class_ru(code: str | None) -> str:
    if not code:
        return ""
    return CLASS_RU.get(code, code)
