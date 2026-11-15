"""Импорт сводок из кэша мода lesta_replays_upload (site_replays.json).

Мод сохраняет ответы сайта по загруженным реплеям. Там есть урон, помощь,
кредиты, опыт, убийства, результат, карта и танк (с уровнем и классом!), но нет
засвета, танкования и расходов — такие бои помечаются как неполные.
"""

from __future__ import annotations

import datetime as _dt
import json
import os

from .replay import NATIONS, split_vehicle

BATTLE_MODES = {
    "Стандартный бой": "Случайный бой",
}


def find_cache(replay_folders: list[str]) -> list[str]:
    """Ищет site_replays.json рядом с папкой клиента."""
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
            candidate = os.path.join(mods, name, "site_replays.json")
            if os.path.isfile(candidate):
                found.append(candidate)
    return found


def _parse_date(value: str) -> _dt.datetime | None:
    if not value:
        return None
    try:
        moment = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)  # сайт отдаёт UTC
    return moment


def rows_from_cache(path: str, known: set[int]) -> list[dict]:
    """Готовит записи для боёв, которых ещё нет в базе."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []

    rows: list[dict] = []
    accounts = payload.get("accounts") or {}
    for _account, block in accounts.items():
        for item in (block.get("items") or {}).values():
            arena_id = int(item.get("arena_unique_id") or 0)
            if not arena_id or arena_id in known:
                continue
            moment = _parse_date(item.get("battle_date") or "")
            if moment is None:
                continue
            tank = item.get("tank") or {}
            vehicle_id = tank.get("vehicle_id") or ""
            nation = tank.get("nation") or ""
            vehicle = f"{nation}:{vehicle_id}" if vehicle_id else ""
            _nation, _vid, tank_name = split_vehicle(vehicle)

            result = str(item.get("battle_result") or "").lower()
            win = 1 if result == "win" else 0
            loss = 1 if result == "loss" else 0
            draw = 1 if result == "draw" else 0
            if not (win or loss or draw):
                loss = 1

            damage = int(item.get("damage") or 0)
            kills = int(item.get("kills") or 0)
            assist = int(item.get("assist") or 0)
            max_hp = 1
            ratio = damage / max_hp
            score = (
                0.45 * min(ratio / 1.6, 1.0)
                + 0.20 * min(kills / 3.0, 1.0)
                + 0.15 * min(assist / 1500.0, 1.0)
                + 0.10 * win
            )

            rows.append({
                "arena_id": arena_id,
                "file": path,
                "file_name": f"{arena_id}.json",
                "file_size": 0,
                "file_mtime": 0.0,
                "source": "mod_cache",
                "partial": 1,
                "played_at": moment.strftime("%Y-%m-%d %H:%M:%S"),
                "date": moment.strftime("%Y-%m-%d"),
                "ts": int(moment.timestamp()),
                "duration": 0,
                "battle_type": 1,
                "gameplay": "",
                "battle_label": BATTLE_MODES.get(item.get("battle_mode") or "", item.get("battle_mode") or "Бой"),
                "map_id": (item.get("map") or {}).get("name") or "",
                "map_name": (item.get("map") or {}).get("display_name") or "Неизвестная карта",
                "arena_type_id": 0,
                "vehicle": vehicle,
                "vehicle_id": vehicle_id,
                "tank": tank_name,
                "type_comp_descr": 0,
                "tier": tank.get("level"),
                "tank_class": tank.get("type"),
                "nation": nation,
                "nation_ru": NATIONS.get(nation, nation.title() if nation else ""),
                "team": 0,
                "winner_team": 1 if win else 2,
                "win": win,
                "loss": loss,
                "draw": draw,
                "result": "Победа" if win else ("Ничья" if draw else "Поражение"),
                "damage": damage,
                "spot": None,
                "assist": assist,
                "assist_radio": 0,
                "assist_track": 0,
                "assist_stun": 0,
                "assist_smoke": 0,
                "assist_inspire": 0,
                "blocked": None,
                "received": None,
                "potential": None,
                "kills": kills,
                "shots": 0,
                "hits": 0,
                "pens": 0,
                "crits": 0,
                "def_points": 0,
                "credits": int(item.get("credits") or 0),
                "repair": 0,
                "ammo": 0,
                "consumables": 0,
                "net_credits": None,
                "xp": int(item.get("xp") or 0),
                "free_xp": 0,
                "tmen_xp": 0,
                "life_time": 0,
                "max_hp": max_hp,
                "health_left": 0,
                "survived": 0,
                "dmg_ratio": 0.0,
                "rating": round(score * 100),
                "mark_of_mastery": 0,
                "achievements": "[]",
                "killer_id": 0,
                "account_id": int(block.get("account_id") or 0) or 0,
                "player_name": "",
                "client_version": "",
                "server": "",
                "tanks_count": 1,
            })
    return rows
