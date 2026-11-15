"""Хранилище: SQLite, схема и импорт реплеев и JSON-выгрузок."""

from __future__ import annotations

import os
import re
import sqlite3
import time

from . import modcache, replay, spawns, tankdb

SCHEMA_VERSION = "6"

# Порядок колонок фиксирован: используется в INSERT.
COLUMNS = [
    "arena_id", "file", "file_name", "file_size", "file_mtime", "source",
    "played_at", "date", "ts",
    "duration", "battle_type", "gameplay", "battle_label",
    "map_id", "map_name", "arena_type_id", "spawn",
    "vehicle", "vehicle_id", "tank", "type_comp_descr", "tier", "tank_class", "partial",
    "nation", "nation_ru",
    "team", "winner_team", "win", "loss", "draw", "result",
    "damage", "spot", "assist", "assist_radio", "assist_track", "assist_stun",
    "assist_smoke", "assist_inspire",
    "blocked", "received", "potential",
    "kills", "shots", "hits", "pens", "crits", "def_points", "marks_on_gun", "damage_rating",
    "credits", "repair", "ammo", "consumables", "net_credits",
    "xp", "free_xp", "tmen_xp",
    "life_time", "max_hp", "health_left", "survived",
    "dmg_ratio", "rating", "mark_of_mastery", "achievements", "killer_id",
    "account_id", "player_name", "client_version", "server", "tanks_count",
]

DDL = """
CREATE TABLE IF NOT EXISTS battles (
    arena_id        INTEGER PRIMARY KEY,
    file            TEXT NOT NULL,
    file_name       TEXT,
    file_size       INTEGER,
    file_mtime      REAL,
    source          TEXT DEFAULT 'replay',
    played_at       TEXT,
    date            TEXT,
    ts              INTEGER,
    duration        INTEGER,
    battle_type     INTEGER,
    gameplay        TEXT,
    battle_label    TEXT,
    map_id          TEXT,
    map_name        TEXT,
    arena_type_id   INTEGER DEFAULT 0,
    spawn           TEXT,
    vehicle         TEXT,
    vehicle_id      TEXT,
    tank            TEXT,
    type_comp_descr INTEGER DEFAULT 0,
    tier            INTEGER,
    tank_class      TEXT,
    partial         INTEGER DEFAULT 0,
    nation          TEXT,
    nation_ru       TEXT,
    team            INTEGER,
    winner_team     INTEGER,
    win             INTEGER DEFAULT 0,
    loss            INTEGER DEFAULT 0,
    draw            INTEGER DEFAULT 0,
    result          TEXT,
    damage          INTEGER DEFAULT 0,
    spot            INTEGER DEFAULT 0,
    assist          INTEGER DEFAULT 0,
    assist_radio    INTEGER DEFAULT 0,
    assist_track    INTEGER DEFAULT 0,
    assist_stun     INTEGER DEFAULT 0,
    assist_smoke    INTEGER DEFAULT 0,
    assist_inspire  INTEGER DEFAULT 0,
    blocked         INTEGER DEFAULT 0,
    received        INTEGER DEFAULT 0,
    potential       INTEGER DEFAULT 0,
    kills           INTEGER DEFAULT 0,
    shots           INTEGER DEFAULT 0,
    hits            INTEGER DEFAULT 0,
    pens            INTEGER DEFAULT 0,
    crits           INTEGER DEFAULT 0,
    def_points      INTEGER DEFAULT 0,
    marks_on_gun    INTEGER DEFAULT 0,
    damage_rating   INTEGER DEFAULT 0,
    credits         INTEGER DEFAULT 0,
    repair          INTEGER DEFAULT 0,
    ammo            INTEGER DEFAULT 0,
    consumables     INTEGER DEFAULT 0,
    net_credits     INTEGER DEFAULT 0,
    xp              INTEGER DEFAULT 0,
    free_xp         INTEGER DEFAULT 0,
    tmen_xp         INTEGER DEFAULT 0,
    life_time       INTEGER DEFAULT 0,
    max_hp          INTEGER DEFAULT 0,
    health_left     INTEGER DEFAULT 0,
    survived        INTEGER DEFAULT 0,
    dmg_ratio       REAL DEFAULT 0,
    rating          INTEGER DEFAULT 0,
    mark_of_mastery INTEGER DEFAULT 0,
    achievements    TEXT,
    killer_id       INTEGER DEFAULT 0,
    account_id      INTEGER DEFAULT 0,
    player_name     TEXT,
    client_version  TEXT,
    server          TEXT,
    tanks_count     INTEGER DEFAULT 1,
    imported_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_battles_date ON battles(date);
CREATE INDEX IF NOT EXISTS idx_battles_ts ON battles(ts);
CREATE INDEX IF NOT EXISTS idx_battles_tank ON battles(tank);
CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(DDL)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Добавляет недостающие колонки, не удаляя уже собранные данные."""
    types = dict(re.findall(r"^\s{4}(\w+)\s+(INTEGER|TEXT|REAL)", DDL, re.M))
    existing = {row[1] for row in conn.execute("PRAGMA table_info(battles)")}
    missing = [name for name in COLUMNS if name not in existing]
    for name in missing:
        column_type = types.get(name, "TEXT")
        conn.execute(f"ALTER TABLE battles ADD COLUMN {name} {column_type}")
    conn.execute(
        "INSERT INTO app_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (SCHEMA_VERSION,),
    )
    conn.commit()


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _known_files(conn: sqlite3.Connection) -> dict[str, tuple[int, float]]:
    rows = conn.execute("SELECT file, file_size, file_mtime FROM battles").fetchall()
    return {r["file"]: (r["file_size"], r["file_mtime"]) for r in rows}


def dictionaries(conn: sqlite3.Connection) -> tuple[dict, dict]:
    """Справочники, собранные по уже импортированным реплеям."""
    tanks = {}
    for row in conn.execute(
        "SELECT type_comp_descr, vehicle FROM battles "
        "WHERE type_comp_descr > 0 AND vehicle != '' AND vehicle IS NOT NULL"
    ):
        tanks[row["type_comp_descr"]] = {"vehicle": row["vehicle"]}
    maps = {}
    for row in conn.execute(
        "SELECT arena_type_id, map_id, map_name FROM battles "
        "WHERE arena_type_id > 0 AND map_name != '' AND map_id != ''"
    ):
        maps[row["arena_type_id"] & 0xFFFF] = (row["map_id"], row["map_name"])
    return tanks, maps


def upsert(conn: sqlite3.Connection, row: dict) -> None:
    values = [row.get(col) for col in COLUMNS]
    placeholders = ", ".join("?" for _ in COLUMNS)
    columns = ", ".join(COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "arena_id")
    conn.execute(
        f"INSERT INTO battles ({columns}, imported_at) VALUES ({placeholders}, ?) "
        f"ON CONFLICT(arena_id) DO UPDATE SET {updates}, imported_at=excluded.imported_at",
        values + [time.strftime("%Y-%m-%d %H:%M:%S")],
    )


def _import_one(conn: sqlite3.Connection, path: str, stat, force: bool,
                known: dict, dict_tanks: dict, dict_maps: dict, result: dict) -> None:
    previous = known.get(path)
    if not force and previous and previous[0] == stat.st_size and abs(previous[1] - stat.st_mtime) < 1:
        result["skipped"] += 1
        return

    is_json = path.lower().endswith(".json")
    try:
        if is_json:
            battle = replay.parse_results_json(path, dict_tanks, dict_maps)
        else:
            battle = replay.parse(path)
    except replay.ReplayError as exc:
        result["failed"] += 1
        if "блоков" in str(exc):
            result["failed_no_results"] += 1
        result["errors"].append((os.path.basename(path), str(exc)))
        return
    except Exception as exc:  # noqa: BLE001 - не роняем импорт из-за одного файла
        result["failed"] += 1
        result["errors"].append((os.path.basename(path), f"{type(exc).__name__}: {exc}"))
        return

    row = battle.row
    row["file_size"] = stat.st_size
    row["file_mtime"] = stat.st_mtime
    row["spawn"] = spawns.side_for(row.get("map_id") or "", row.get("team") or 0)
    if not row.get("tier") or not row.get("tank_class"):
        tier, tank_class = tankdb.tier_class(row.get("vehicle_id") or "")
        row["tier"] = row.get("tier") or tier
        row["tank_class"] = row.get("tank_class") or tank_class
    if row.get("arena_id") in (0, None):
        row["arena_id"] = -abs(hash(os.path.basename(path))) % (2 ** 62)

    exists = conn.execute(
        "SELECT 1 FROM battles WHERE arena_id=?", (row["arena_id"],)
    ).fetchone()
    if exists:
        # реплей подробнее JSON-выгрузки: не затираем его «бедной» записью
        if is_json:
            result["skipped"] += 1
            return
        result["updated"] += 1
    else:
        result["imported"] += 1
    upsert(conn, row)
    if is_json:
        result["imported_json"] += 1


def import_files(conn: sqlite3.Connection, files: list[str], force: bool = False) -> dict:
    """Импортирует файлы: сначала реплеи, затем JSON-выгрузки модов."""
    known = _known_files(conn)
    result = {
        "scanned": 0, "imported": 0, "updated": 0, "skipped": 0,
        "failed": 0, "failed_no_results": 0, "imported_json": 0,
        "errors": [], "battles_in_db": 0,
    }
    replays = [f for f in files if not f.lower().endswith(".json")]
    jsons = [f for f in files if f.lower().endswith(".json")]

    for batch, is_json in ((replays, False), (jsons, True)):
        if not batch:
            continue
        dict_tanks, dict_maps = dictionaries(conn)
        for path in batch:
            result["scanned"] += 1
            try:
                stat = os.stat(path)
            except OSError as exc:
                result["failed"] += 1
                result["errors"].append((os.path.basename(path), f"нет доступа: {exc}"))
                continue
            _import_one(conn, path, stat, force, known, dict_tanks, dict_maps, result)
            if result["scanned"] % 200 == 0:
                conn.commit()
        conn.commit()

    result["battles_in_db"] = conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0]
    return result


def collect_files(replay_folders: list[str], json_folders: list[str]) -> list[str]:
    files: list[str] = []
    seen = set()
    for folder in replay_folders or []:
        if not folder or not os.path.isdir(folder):
            continue
        for path in replay.parse_folder(folder):
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key)
                files.append(path)
    for folder in json_folders or []:
        if not folder or not os.path.isdir(folder):
            continue
        for path in replay.parse_folder(folder, (".json",)):
            name = os.path.basename(path)
            if not name.split(".")[0].isdigit():
                continue  # settings.json, replay_index.json и прочие служебные
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key)
                files.append(path)
    return files


def import_mod_cache(conn: sqlite3.Connection, paths: list[str]) -> int:
    """Добивает бои из кэша мода — только те, которых нет в базе."""
    if not paths:
        return 0
    known = {row[0] for row in conn.execute("SELECT arena_id FROM battles")}
    added = 0
    for path in paths:
        for row in modcache.rows_from_cache(path, known):
            upsert(conn, row)
            known.add(row["arena_id"])
            added += 1
    conn.commit()
    return added


def fix_map_names(conn: sqlite3.Connection) -> int:
    """Заменяет ключи локализации вида «14_siegfried_line_att/name» на нормальные названия."""
    rows = conn.execute("SELECT arena_id, map_id, map_name FROM battles").fetchall()
    known: dict[str, str] = {}
    for row in rows:
        name = (row["map_name"] or "").strip()
        if not name or name.endswith("/name") or name == row["map_id"]:
            continue
        known.setdefault((row["map_id"] or "").lower(), name)

    updated = 0
    for row in rows:
        name = (row["map_name"] or "").strip()
        if name and not name.endswith("/name") and name != row["map_id"]:
            continue
        base = (row["map_id"] or "").lower()
        candidate = None
        parts = base.split("_")
        for size in range(len(parts), 1, -1):
            key = "_".join(parts[:size])
            if key in known:
                candidate = known[key]
                break
        if not candidate:
            candidate = base.replace("_", " ").strip().capitalize() or "Неизвестная карта"
        conn.execute("UPDATE battles SET map_name=? WHERE arena_id=?", (candidate, row["arena_id"]))
        updated += 1
    if updated:
        conn.commit()
    return updated


def fill_spawns(conn: sqlite3.Connection) -> int:
    """Проставляет респауны боям, у которых их ещё нет."""
    rows = conn.execute(
        "SELECT arena_id, map_id, team FROM battles WHERE spawn IS NULL"
    ).fetchall()
    updated = 0
    for row in rows:
        side = spawns.side_for(row["map_id"] or "", row["team"] or 0)
        if side:
            conn.execute("UPDATE battles SET spawn=? WHERE arena_id=?", (side, row["arena_id"]))
            updated += 1
    if updated:
        conn.commit()
    return updated


def enrich_tiers(conn: sqlite3.Connection) -> int:
    """Проставляет уровень и класс танкам, у которых их ещё нет."""
    rows = conn.execute(
        "SELECT arena_id, vehicle_id FROM battles WHERE tier IS NULL OR tank_class IS NULL"
    ).fetchall()
    updated = 0
    for row in rows:
        tier, tank_class = tankdb.tier_class(row["vehicle_id"] or "")
        if tier or tank_class:
            conn.execute(
                "UPDATE battles SET tier=COALESCE(tier, ?), tank_class=COALESCE(tank_class, ?) "
                "WHERE arena_id=?",
                (tier, tank_class, row["arena_id"]),
            )
            updated += 1
    if updated:
        conn.commit()
    return updated


def import_folders(conn: sqlite3.Connection, replay_folders: list[str],
                   json_folders: list[str] | None = None, force: bool = False,
                   include_cache: bool = True) -> dict:
    files = collect_files(replay_folders or [], json_folders or [])
    summary = import_files(conn, files, force=force)
    summary["folders"] = [f for f in (replay_folders or []) if f and os.path.isdir(f)]
    summary["json_folders"] = [f for f in (json_folders or []) if f and os.path.isdir(f)]
    summary["imported_cache"] = 0
    summary["mod_cache"] = []
    summary["tiers"] = enrich_tiers(conn)
    summary["map_names"] = fix_map_names(conn)
    if include_cache:
        caches = modcache.find_cache(replay_folders or [])
        summary["mod_cache"] = caches
        summary["imported_cache"] = import_mod_cache(conn, caches)
        summary["battles_in_db"] = conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0]
    set_meta(conn, "last_import", time.strftime("%Y-%m-%d %H:%M:%S"))
    set_meta(conn, "folders", "|".join(summary["folders"]))
    set_meta(conn, "json_folders", "|".join(summary["json_folders"]))
    set_meta(conn, "mod_cache", "|".join(summary["mod_cache"]))
    set_meta(conn, "last_unread", summary["failed"])
    set_meta(conn, "last_unread_no_results", summary.get("failed_no_results", 0))
    return summary


def prune_missing(conn: sqlite3.Connection) -> int:
    """Удаляет записи, чьи файлы больше не существуют."""
    rows = conn.execute("SELECT arena_id, file FROM battles").fetchall()
    gone = [r["arena_id"] for r in rows if not os.path.exists(r["file"])]
    for arena_id in gone:
        conn.execute("DELETE FROM battles WHERE arena_id=?", (arena_id,))
    conn.commit()
    return len(gone)


def select_range(conn: sqlite3.Connection, date_from: str | None, date_to: str | None) -> list[sqlite3.Row]:
    query = "SELECT * FROM battles"
    params: list = []
    where = []
    if date_from:
        where.append("date >= ?")
        params.append(date_from)
    if date_to:
        where.append("date <= ?")
        params.append(date_to)
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY ts ASC"
    return conn.execute(query, params).fetchall()


def bounds(conn: sqlite3.Connection) -> tuple[str | None, str | None, int]:
    row = conn.execute(
        "SELECT MIN(date) AS lo, MAX(date) AS hi, COUNT(*) AS n FROM battles"
    ).fetchone()
    return row["lo"], row["hi"], row["n"]
