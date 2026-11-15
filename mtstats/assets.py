"""Сборка справочников из файлов игры — на компьютере пользователя.

В публичной версии программа не содержит картинок и таблиц из клиента.
Всё это строится при первом запуске из установленного клиента «Мир танков»:

* `tank_db.json`    — уровни и классы техники (`scripts/item_defs/vehicles/*/list.xml`);
* `map_spawns.json` — респауны сторон (`scripts/arena_defs/*.xml`);
* `tank_icons/*.png`— обрезанные иконки техники (`gui/maps/icons/vehicle/...`).

Если клиент не найден, справочники остаются пустыми, а интерфейс просто
показывает прочерки вместо уровней, классов и картинок.
"""

from __future__ import annotations

import io
import json
import os
import zipfile

from . import bigworld, paths

CLASSES = ("heavyTank", "mediumTank", "lightTank", "AT-SPG", "SPG")
SPAWN_TEAMS = ("ctf", "assault", "assault2", "domination", "comp7")

TANK_DB = "tank_db.json"
MAP_SPAWNS = "map_spawns.json"
ICONS = "tank_icons"

PACKAGE_SCRIPTS = os.path.join("res", "packages", "scripts.pkg")
PACKAGE_GUI = ("gui-part1.pkg", "gui-part2.pkg")


# --------------------------------------------------------------------------
# где лежит игра
# --------------------------------------------------------------------------

def detect_game_root(config: dict | None = None) -> str | None:
    """Ищет корень клиента рядом с папками реплеев и по типовым путям."""
    candidates: list[str] = []
    for folder in (config or {}).get("replays") or []:
        if folder:
            candidates.append(os.path.dirname(os.path.abspath(folder)))
    candidates += [
        r"C:\Games\Tanki",
        r"C:\Games\World_of_Tanks_RU",
        r"D:\Games\Tanki",
    ]
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, PACKAGE_SCRIPTS)):
            return path
    return None


def _assets_dir() -> str:
    path = os.path.join(paths.user_dir(), "assets")
    os.makedirs(path, exist_ok=True)
    return path


def asset(name: str) -> str:
    return os.path.join(_assets_dir(), name)


# --------------------------------------------------------------------------
# справочник техники
# --------------------------------------------------------------------------

def _class_from_tags(tags: str) -> str | None:
    words = set((tags or "").split())
    for name in CLASSES:
        if name in words:
            return name
    return None


def build_tank_db(game_root: str) -> dict:
    tanks: dict[str, dict] = {}
    package = os.path.join(game_root, PACKAGE_SCRIPTS)
    if not os.path.isfile(package):
        return tanks
    with zipfile.ZipFile(package) as archive:
        for name in archive.namelist():
            parts = name.split("/")
            if len(parts) != 5 or not name.startswith("scripts/item_defs/vehicles/"):
                continue
            if parts[-1] != "list.xml":
                continue
            nation = parts[3]
            try:
                tree = bigworld.parse(archive.read(name))
            except bigworld.PackedSectionError:
                continue
            for node_name, typ, value in tree:
                if typ != bigworld.SECTION:
                    continue
                fields = {n: v for n, t, v in value}
                level = fields.get("level")
                tags = fields.get("tags") or ""
                if not isinstance(level, int) or not level:
                    continue
                tanks[node_name.lower()] = {
                    "name": node_name,
                    "tier": int(level),
                    "class": _class_from_tags(tags if isinstance(tags, str) else ""),
                    "nation": nation,
                }
    if tanks:
        with open(asset(TANK_DB), "w", encoding="utf-8") as fh:
            json.dump(tanks, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return tanks


# --------------------------------------------------------------------------
# респауны
# --------------------------------------------------------------------------

def _find_node(nodes, path):
    for name, typ, value in nodes:
        if name != path[0]:
            continue
        if len(path) == 1:
            return typ, value
        if typ == bigworld.SECTION:
            found = _find_node(value, path[1:])
            if found:
                return found
    return None


def _first_position(nodes):
    for name, typ, value in nodes:
        if typ != bigworld.SECTION and isinstance(value, tuple) and len(value) >= 2:
            return float(value[0]), float(value[1])
        if typ == bigworld.SECTION:
            found = _first_position(value)
            if found:
                return found
    return None


def _bases(tree):
    for gameplay in SPAWN_TEAMS:
        node = _find_node(tree, ["gameplayTypes", gameplay, "teamBasePositions"])
        if not node:
            continue
        section = node[1]
        first = _find_node(section, ["team1"])
        second = _find_node(section, ["team2"])
        if not first or not second:
            continue
        pos1 = _first_position(first[1])
        pos2 = _first_position(second[1])
        if pos1 and pos2:
            return gameplay, pos1, pos2
    return None


def build_map_spawns(game_root: str, map_ids: list[str]) -> dict:
    result: dict[str, dict] = {}
    package = os.path.join(game_root, PACKAGE_SCRIPTS)
    if not os.path.isfile(package) or not map_ids:
        return result
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        for map_id in map_ids:
            candidates = [map_id]
            parts = map_id.split("_")
            for size in range(len(parts) - 1, 1, -1):
                candidates.append("_".join(parts[:size]))
            tree = None
            used = None
            for candidate in candidates:
                path = f"scripts/arena_defs/{candidate}.xml"
                if path not in names:
                    continue
                try:
                    tree = bigworld.parse(archive.read(path))
                    used = candidate
                    break
                except bigworld.PackedSectionError:
                    continue
            if not tree:
                continue
            data = _bases(tree)
            if not data:
                continue
            gameplay, (x1, z1), (x2, z2) = data
            dx, dz = x2 - x1, z2 - z1
            if abs(dz) >= abs(dx):
                axis = "vertical"
                team1 = "top" if z1 > z2 else "bottom"
            else:
                axis = "horizontal"
                team1 = "right" if x1 > x2 else "left"
            team2 = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}[team1]
            result[map_id] = {
                "arena": used,
                "gameplay": gameplay,
                "axis": axis,
                "team1": team1,
                "team2": team2,
                "team1_pos": [round(x1, 1), round(z1, 1)],
                "team2_pos": [round(x2, 1), round(z2, 1)],
            }
    if result:
        with open(asset(MAP_SPAWNS), "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, sort_keys=True, indent=1)
    return result


# --------------------------------------------------------------------------
# иконки техники
# --------------------------------------------------------------------------

def build_icons(game_root: str, vehicle_ids: list[str]) -> int:
    """Обрезает иконки по содержимому: в клиентских PNG много пустых полей."""
    try:
        from PIL import Image
    except ImportError:
        return 0

    target_dir = asset(ICONS)
    os.makedirs(target_dir, exist_ok=True)

    archives = []
    for name in PACKAGE_GUI:
        path = os.path.join(game_root, "res", "packages", name)
        if os.path.isfile(path):
            archives.append(zipfile.ZipFile(path))
    if not archives:
        return 0

    made = 0
    for vehicle in vehicle_ids:
        key = (vehicle or "").lower()
        if not key:
            continue
        out = os.path.join(target_dir, f"{key}.png")
        if os.path.isfile(out):
            continue
        raw = None
        for archive in archives:
            names = set(archive.namelist())
            for candidate in (
                f"gui/maps/icons/vehicle/420x307/{key}.png",
                f"gui/maps/icons/vehicle/contour/{key}.png",
            ):
                if candidate in names:
                    raw = archive.read(candidate)
                    break
            if raw:
                break
        if not raw:
            continue
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:  # noqa: BLE001
            continue
        bbox = image.getbbox()
        if bbox:
            left, top, right, bottom = bbox
            pad_x = int((right - left) * 0.06)
            pad_y = int((bottom - top) * 0.06)
            image = image.crop((
                max(0, left - pad_x), max(0, top - pad_y),
                min(image.width, right + pad_x), min(image.height, bottom + pad_y),
            ))
        image.thumbnail((240, 176), Image.LANCZOS)
        image.save(out, optimize=True)
        made += 1
    return made


# --------------------------------------------------------------------------
# всё вместе
# --------------------------------------------------------------------------

def ensure_tank_db(config: dict) -> int:
    game_root = detect_game_root(config)
    if not game_root or os.path.isfile(asset(TANK_DB)):
        return 0
    return len(build_tank_db(game_root))


def ensure_map_spawns(config: dict, map_ids: list[str]) -> int:
    game_root = detect_game_root(config)
    if not game_root or os.path.isfile(asset(MAP_SPAWNS)):
        return 0
    return len(build_map_spawns(game_root, map_ids))


def ensure_icons(config: dict, vehicle_ids: list[str]) -> int:
    game_root = detect_game_root(config)
    if not game_root:
        return 0
    return build_icons(game_root, vehicle_ids)


def ensure(config: dict, map_ids: list[str] | None = None,
           vehicle_ids: list[str] | None = None) -> dict:
    """Строит недостающие справочники. Возвращает отчёт для лога."""
    report = {"game_root": None, "tank_db": 0, "spawns": 0, "icons": 0}
    game_root = detect_game_root(config)
    report["game_root"] = game_root
    if not game_root:
        return report

    if not os.path.isfile(asset(TANK_DB)):
        report["tank_db"] = len(build_tank_db(game_root))
    if map_ids and not os.path.isfile(asset(MAP_SPAWNS)):
        report["spawns"] = len(build_map_spawns(game_root, map_ids))
    if vehicle_ids:
        report["icons"] = build_icons(game_root, vehicle_ids)
    return report
