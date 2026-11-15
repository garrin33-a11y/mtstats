"""Парсер реплеев «Мир танков» (Lesta, .mtreplay).

Формат файла (проверено на клиенте 1.46.0.0):

    0x00  uint32  сигнатура 0x11343212
    0x04  uint32  число JSON-блоков (обычно 2)
    далее для каждого блока:
          uint32  длина
          bytes   JSON (UTF-8)
    после блоков:
          uint32  размер распакованного потока боя
          uint32  размер сжатого потока боя
          bytes   поток боя (позиции/выстрелы; для статистики не нужен)
          bytes   хвост/CRC

Блок 0 — «шапка»: игрок, танк, карта, версия клиента, список участников.
Блок 1 — результат боя: personal (полная экономика и боевые показатели),
          players, vehicles, common (победитель, длительность, время).

Кроме реплеев поддерживаются JSON-выгрузки модов (например,
mods/configs/lesta_replays_upload/battle_results/<arena_id>.json): в них есть
только блок результатов, без «шапки», поэтому танк и карта подставляются из
справочников, собранных по реплеям.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import struct
from dataclasses import dataclass, field

MAGIC = 0x11343212

# Человекочитаемые названия режимов по gameplayID.
GAMEPLAY = {
    "ctf": "Случайный бой",
    "assault": "Штурм",
    "encounter": "Встречный бой",
    "epic": "Эпический бой",
    "domination": "Превосходство",
    "ctf30x30": "30 на 30",
    "armsrace": "Гонка вооружений",
    "bootcamp": "Учебный бой",
    "comp7": "Ранговый бой",
    "ctf_epic": "Эпический бой",
}

# Названия по числовому типу боя (когда нет gameplayID, например в JSON мода).
BATTLE_TYPES = {
    1: "Случайный бой",
    2: "Тренировка",
    3: "Турнир",
    4: "Ротный бой",
    5: "Взводный бой",
    6: "Турнир",
    7: "Специальный бой",
    8: "Специальный бой",
    9: "Специальный бой",
    10: "Специальный бой",
    27: "Эпический бой",
    31: "Ранговый бой",
    32: "Ранговый бой",
}

NATIONS = {
    "ussr": "СССР",
    "germany": "Германия",
    "usa": "США",
    "china": "Китай",
    "france": "Франция",
    "uk": "Великобритания",
    "japan": "Япония",
    "czech": "Чехия",
    "sweden": "Швеция",
    "poland": "Польша",
    "italy": "Италия",
    "intunion": "Интернациональный",
}


class ReplayError(Exception):
    """Реплей не удалось разобрать."""


@dataclass
class Battle:
    """Один бой, приведённый к плоской записи."""

    row: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def __getitem__(self, key):
        return self.row[key]

    def get(self, key, default=None):
        return self.row.get(key, default)


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def read_blocks(path: str) -> tuple[list[bytes], int]:
    """Читает блоки JSON из файла реплея."""
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 16:
        raise ReplayError("файл слишком мал")
    if _u32(data, 0) != MAGIC:
        raise ReplayError(f"неизвестная сигнатура {_u32(data, 0):#010x}")
    count = _u32(data, 4)
    if not 2 <= count <= 4:
        raise ReplayError(f"неожиданное число блоков: {count}")
    blocks: list[bytes] = []
    off = 8
    for index in range(count):
        if off + 4 > len(data):
            raise ReplayError("файл обрывается на заголовке блока")
        size = _u32(data, off)
        off += 4
        if size <= 0 or off + size > len(data):
            raise ReplayError(f"блок {index} выходит за границы файла")
        blocks.append(data[off:off + size])
        off += size
    return blocks, off


def _load_json(block: bytes):
    text = block.decode("utf-8-sig", errors="strict")
    return json.loads(text)


def _num(value, default=0) -> int:
    if value is None:
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _cost(value) -> int:
    """Стоимость из полей вида [40000, 0, 0] / 24970 / None."""
    if isinstance(value, (list, tuple)):
        return sum(_num(x) for x in value)
    return _num(value)


_DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def _parse_datetime(value, fallback_epoch=None, filename=None) -> _dt.datetime | None:
    if isinstance(value, (int, float)) and value > 1_000_000_000:
        return _dt.datetime.fromtimestamp(value)
    if isinstance(value, str) and value.strip():
        text = value.strip()
        for fmt in _DATE_FORMATS:
            try:
                return _dt.datetime.strptime(text, fmt)
            except ValueError:
                continue
    if fallback_epoch:
        try:
            return _dt.datetime.fromtimestamp(int(fallback_epoch))
        except (OverflowError, OSError, ValueError):
            pass
    if filename:
        match = re.match(r"(\d{8})_(\d{4})", os.path.basename(filename))
        if match:
            try:
                return _dt.datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M")
            except ValueError:
                pass
    return None


_PREFIX_RE = re.compile(r"^[A-Za-z]{1,3}\d{1,3}_")


def split_vehicle(vehicle: str) -> tuple[str, str, str]:
    """'uk-GB92_FV217' -> ('uk', 'GB92_FV217', 'FV217')."""
    if not vehicle:
        return "", "", "Неизвестный танк"
    norm = vehicle.replace(":", "-")
    nation, _, name = norm.partition("-")
    if not name:
        nation, name = "", norm
    short = _PREFIX_RE.sub("", name)
    return nation, name, short.replace("_", " ")


def _result_label(winner_team: int, my_team: int) -> str:
    if not winner_team:
        return "Ничья"
    return "Победа" if winner_team == my_team else "Поражение"


def _extract(meta: dict | None, results: list, path: str, source: str,
             dict_tanks: dict | None = None, dict_maps: dict | None = None) -> Battle:
    """Собирает плоскую запись боя из блоков реплея или JSON мода."""
    meta = meta or {}
    first = results[0]
    personal = first.get("personal") or {}
    common = first.get("common") or {}
    players = first.get("players") or {}

    tank_keys = [key for key in personal if key != "avatar"]
    if not tank_keys:
        raise ReplayError("в результатах нет данных по своему танку")

    entries = [personal[key] for key in tank_keys]
    me = entries[0]
    avatar = personal.get("avatar") or {}

    my_team = _num(me.get("team"))
    winner_team = _num(common.get("winnerTeam"))

    damage = sum(_num(e.get("damageDealt")) for e in entries)
    spot = sum(_num(e.get("spotted")) for e in entries)
    assist_radio = sum(_num(e.get("damageAssistedRadio")) for e in entries)
    assist_track = sum(_num(e.get("damageAssistedTrack")) for e in entries)
    assist_stun = sum(_num(e.get("damageAssistedStun")) for e in entries)
    assist_smoke = sum(_num(e.get("damageAssistedSmoke")) for e in entries)
    assist_inspire = sum(_num(e.get("damageAssistedInspire")) for e in entries)
    assist = assist_radio + assist_track + assist_stun

    blocked = sum(_num(e.get("damageBlockedByArmor")) for e in entries)
    received = sum(_num(e.get("damageReceived")) for e in entries)
    potential = sum(_num(e.get("potentialDamageReceived")) for e in entries)
    kills = sum(_num(e.get("kills")) for e in entries)
    shots = sum(_num(e.get("shots")) for e in entries)
    hits = sum(_num(e.get("directHits")) for e in entries)
    pens = sum(_num(e.get("piercings")) for e in entries)
    crits = sum(_num(e.get("tdestroyedModules")) for e in entries)
    def_points = sum(_num(e.get("droppedCapturePoints")) for e in entries)
    marks_on_gun = sum(_num(e.get("marksOnGun")) for e in entries)
    damage_rating = sum(_num(e.get("damageRating")) for e in entries)
    credits = sum(_num(e.get("credits")) for e in entries)
    xp = sum(_num(e.get("xp")) for e in entries)
    free_xp = sum(_num(e.get("freeXP")) for e in entries)
    tmen_xp = sum(_num(e.get("tmenXP")) for e in entries)
    life_time = sum(_num(e.get("lifeTime")) for e in entries)
    max_hp = sum(_num(e.get("maxHealth")) for e in entries) or _num(me.get("maxHealth"))
    health = _num(me.get("health"))

    repair = sum(_cost(e.get("repair", e.get("autoRepairCost"))) for e in entries)
    ammo = sum(_cost(e.get("autoLoadCost")) for e in entries)
    consumables = sum(_cost(e.get("autoEquipCost")) for e in entries)
    net = credits - repair - ammo - consumables

    achievements = []
    for entry in entries:
        for item in entry.get("achievements") or []:
            if isinstance(item, (list, tuple)) and item:
                achievements.append(item[0])
            elif isinstance(item, int):
                achievements.append(item)

    account_id = _num(me.get("accountDBID")) or _num(avatar.get("accountDBID"))
    type_comp = _num(me.get("typeCompDescr"))
    arena_type = _num(common.get("arenaTypeID"))
    base_arena = arena_type & 0xFFFF if arena_type else 0

    # --- танк ---
    vehicle = str(meta.get("playerVehicle") or "")
    if not vehicle and dict_tanks and type_comp in dict_tanks:
        vehicle = dict_tanks[type_comp].get("vehicle", "")
    nation, vehicle_id, tank_name = split_vehicle(vehicle)
    if not vehicle and type_comp:
        tank_name = f"Танк #{type_comp}"
        vehicle_id = str(type_comp)

    # --- карта ---
    map_id = str(meta.get("mapName") or "")
    map_name = str(meta.get("mapDisplayName") or "")
    if not map_id and dict_maps and base_arena in dict_maps:
        map_id, map_name = dict_maps[base_arena]
    if not map_name:
        map_name = map_id or "Неизвестная карта"

    # --- игрок ---
    player_name = str(meta.get("playerName") or "")
    if not player_name and account_id:
        player_name = str((players.get(str(account_id)) or {}).get("name") or "")

    played_at = _parse_datetime(meta.get("dateTime"), common.get("arenaCreateTime"), path)
    if played_at is None:
        raise ReplayError("не удалось определить дату боя")

    duration = _num(common.get("duration"))
    win = 1 if winner_team and winner_team == my_team else 0
    draw = 1 if winner_team == 0 else 0
    loss = 1 if not win and not draw else 0

    ratio = damage / max_hp if max_hp else 0.0
    score = (
        0.45 * min(ratio / 1.6, 1.0)
        + 0.20 * min(kills / 3.0, 1.0)
        + 0.15 * min((spot * 150 + assist) / 1500.0, 1.0)
        + 0.10 * min(blocked / 1500.0, 1.0)
        + 0.10 * win
    )
    rating = round(score * 100)

    gameplay = str(meta.get("gameplayID") or "")
    battle_type = _num(meta.get("battleType")) or _num(common.get("bonusType"))
    label = GAMEPLAY.get(gameplay) or BATTLE_TYPES.get(battle_type) or (
        f"Тип боя {battle_type}" if battle_type else "Бой"
    )

    row = {
        "arena_id": _num(meta.get("arenaUniqueID")) or _num(first.get("arenaUniqueID")),
        "file": path,
        "file_name": os.path.basename(path),
        "file_size": os.path.getsize(path),
        "source": source,
        "played_at": played_at.strftime("%Y-%m-%d %H:%M:%S"),
        "date": played_at.strftime("%Y-%m-%d"),
        "ts": int(played_at.timestamp()),
        "duration": duration,
        "battle_type": battle_type,
        "gameplay": gameplay,
        "battle_label": label,
        "map_id": map_id,
        "map_name": map_name,
        "arena_type_id": arena_type,
        "vehicle": vehicle,
        "vehicle_id": vehicle_id,
        "tank": tank_name,
        "type_comp_descr": type_comp,
        "nation": nation,
        "nation_ru": NATIONS.get(nation, nation.title() if nation else ""),
        "team": my_team,
        "winner_team": winner_team,
        "win": win,
        "loss": loss,
        "draw": draw,
        "result": _result_label(winner_team, my_team),
        "damage": damage,
        "spot": spot,
        "assist": assist,
        "assist_radio": assist_radio,
        "assist_track": assist_track,
        "assist_stun": assist_stun,
        "assist_smoke": assist_smoke,
        "assist_inspire": assist_inspire,
        "blocked": blocked,
        "received": received,
        "potential": potential,
        "kills": kills,
        "shots": shots,
        "hits": hits,
        "pens": pens,
        "crits": crits,
        "def_points": def_points,
        "marks_on_gun": marks_on_gun,
        "damage_rating": damage_rating,
        "credits": credits,
        "repair": repair,
        "ammo": ammo,
        "consumables": consumables,
        "net_credits": net,
        "xp": xp,
        "free_xp": free_xp,
        "tmen_xp": tmen_xp,
        "life_time": life_time,
        "max_hp": max_hp,
        "health_left": health,
        "survived": 1 if health > 0 else 0,
        "dmg_ratio": round(ratio, 3),
        "rating": rating,
        "mark_of_mastery": _num(me.get("markOfMastery")),
        "achievements": json.dumps(sorted(set(achievements))),
        "killer_id": _num(me.get("killerID")),
        "account_id": account_id,
        "player_name": player_name,
        "client_version": str(meta.get("clientVersionFromExe") or ""),
        "server": str(meta.get("serverName") or ""),
        "tanks_count": len(entries),
    }
    return Battle(row=row)


def parse(path: str) -> Battle:
    """Разбирает файл реплея .mtreplay/.wotreplay."""
    blocks, _tail = read_blocks(path)
    meta = _load_json(blocks[0])
    try:
        results = _load_json(blocks[1])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReplayError(f"не читается блок результатов: {exc}") from exc
    if not isinstance(results, list) or not results:
        raise ReplayError("блок результатов пуст")
    return _extract(meta, results, path, source="replay")


def parse_results_json(path: str, dict_tanks: dict | None = None,
                       dict_maps: dict | None = None) -> Battle:
    """Разбирает JSON с результатами боя (выгрузка мода lesta_replays_upload)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"не читается JSON: {exc}") from exc
    if isinstance(data, dict) and "personal" in data:
        results = [data]
    elif isinstance(data, list) and data and isinstance(data[0], dict) and "personal" in data[0]:
        results = data
    else:
        raise ReplayError("это не файл результатов боя")
    return _extract(None, results, path, source="mod_json",
                    dict_tanks=dict_tanks, dict_maps=dict_maps)


def parse_folder(folder: str, extensions: tuple[str, ...] = (".mtreplay", ".wotreplay")) -> list[str]:
    """Возвращает список файлов реплеев в папке (рекурсивно)."""
    found: list[str] = []
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if name.lower().endswith(extensions):
                found.append(os.path.join(root, name))
    found.sort()
    return found
