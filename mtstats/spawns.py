"""Респауны: на каком краю карты какая команда появляется.

Данные собираются из клиента скриптом `tools/build_spawns.py` в
`data/map_spawns.json`: для каждой карты — какая команда сверху, снизу,
слева или справа, и координаты баз.
"""

from __future__ import annotations

import json
import os

from . import paths

DB_PATH = paths.resource(os.path.join("data", "map_spawns.json"))
USER_PATH = os.path.join(paths.user_dir(), "assets", "map_spawns.json")

LABELS = {
    "top": "Верхний",
    "bottom": "Нижний",
    "left": "Левый",
    "right": "Правый",
}
ORDER = ("top", "bottom", "left", "right")

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


def map_info(map_id: str) -> dict | None:
    if not map_id:
        return None
    return load().get(map_id)


def side_for(map_id: str, team: int) -> str | None:
    """'top'/'bottom'/'left'/'right' для команды 1 или 2."""
    info = map_info(map_id)
    if not info or team not in (1, 2):
        return None
    return info.get(f"team{team}")


def label(side: str | None) -> str:
    return LABELS.get(side or "", "")
