"""Агрегация боев: сводка, ряды по периодам, разрезы."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from . import wn8 as _wn8

MONTHS_SHORT = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "май", 6: "июн",
    7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек",
}
PERIODS = ("today", "week", "month", "year", "all", "custom")


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _safe_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return _date(value)
    except (ValueError, TypeError):
        return None


def resolve_period(period: str, date_from: str | None = None,
                   date_to: str | None = None,
                   today: dt.date | None = None) -> tuple[dt.date | None, dt.date | None, str]:
    """Возвращает (from, to, подпись периода)."""
    today = today or dt.date.today()
    period = (period or "month").lower()
    if period == "today":
        return today, today, "Сегодня"
    if period == "week":
        start = today - dt.timedelta(days=today.weekday())
        return start, today, "Эта неделя"
    if period == "month":
        return today.replace(day=1), today, "Этот месяц"
    if period == "year":
        return today.replace(month=1, day=1), today, "Этот год"
    if period == "all":
        return None, None, "Всё время"
    if period == "custom":
        start = _safe_date(date_from)
        end = _safe_date(date_to) or start or today
        if start and start > end:
            start, end = end, start
        return start, end, "Свой период"
    return today.replace(day=1), today, "Этот месяц"


def auto_granularity(date_from: dt.date | None, date_to: dt.date | None) -> str:
    if not date_from or not date_to:
        return "month"
    days = (date_to - date_from).days
    if days <= 45:
        return "day"
    if days <= 220:
        return "week"
    if days <= 1100:
        return "month"
    return "year"


def _bucket(day: dt.date, granularity: str) -> tuple[str, str, str]:
    """(ключ сортировки, ключ группировки, подпись)."""
    if granularity == "day":
        return day.isoformat(), day.isoformat(), f"{day.day:02d}.{day.month:02d}"
    if granularity == "week":
        monday = day - dt.timedelta(days=day.weekday())
        return monday.isoformat(), monday.isoformat(), f"{monday.day:02d}.{monday.month:02d}"
    if granularity == "month":
        key = f"{day.year:04d}-{day.month:02d}"
        return key, key, f"{MONTHS_SHORT[day.month]} {day.year % 100:02d}"
    key = f"{day.year:04d}"
    return key, key, key


def _avg(total: float, count: int) -> float:
    return round(total / count, 1) if count else 0.0


def _known(rows: list, field: str) -> list:
    """Значения поля без «неизвестных» (NULL) — для неполных боёв из кэша мода."""
    return [row[field] for row in rows if row[field] is not None]


def _agg(rows: list) -> dict:
    n = len(rows)
    wins = sum(r["win"] for r in rows)
    losses = sum(r["loss"] for r in rows)
    draws = sum(r["draw"] for r in rows)
    damage = sum(r["damage"] for r in rows)
    spot_values = _known(rows, "spot")
    blocked_values = _known(rows, "blocked")
    received_values = _known(rows, "received")
    net_values = _known(rows, "net_credits")
    return {
        "battles": n,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "winrate": _avg(wins * 100, n),
        "damage_total": damage,
        "damage_avg": _avg(damage, n),
        "spot_avg": _avg(sum(spot_values), len(spot_values)),
        "spot_total": sum(spot_values) if spot_values else None,
        "assist_avg": _avg(sum(r["assist"] for r in rows), n),
        "assist_total": sum(r["assist"] for r in rows),
        "blocked_avg": _avg(sum(blocked_values), len(blocked_values)),
        "blocked_total": sum(blocked_values) if blocked_values else None,
        "received_avg": _avg(sum(received_values), len(received_values)),
        "credits_total": sum(r["credits"] for r in rows),
        "net_total": sum(net_values) if net_values else None,
        "net_avg": _avg(sum(net_values), len(net_values)),
        "xp_total": sum(r["xp"] for r in rows),
        "xp_avg": _avg(sum(r["xp"] for r in rows), n),
        "free_xp_total": sum(r["free_xp"] for r in rows),
        "kills_avg": _avg(sum(r["kills"] for r in rows), n),
        "kills_total": sum(r["kills"] for r in rows),
        "shots_total": sum(r["shots"] for r in rows),
        "hits_total": sum(r["hits"] for r in rows),
        "pens_total": sum(r["pens"] for r in rows),
        "damage_rating_avg": _avg(sum(_known(rows, "damage_rating")), len(_known(rows, "damage_rating"))),
        "def_avg": _avg(sum(r["def_points"] for r in rows), n),
        "def_total": sum(r["def_points"] for r in rows),
        "rating_avg": _avg(sum(r["rating"] for r in rows), n),
        "survival_rate": _avg(sum(r["survived"] for r in rows) * 100, n),
        "dmg_ratio_avg": _avg(sum(r["dmg_ratio"] for r in rows), n),
        "kd": _avg(sum(r["kills"] for r in rows), max(losses + draws, 1)),
    }


def _battle_row(row) -> dict:
    return {
        "played_at": row["played_at"],
        "date": row["date"],
        "map": row["map_name"],
        "tank": row["tank"],
        "nation": row["nation_ru"],
        "type": row["battle_label"],
        "result": row["result"],
        "damage": row["damage"],
        "spot": row["spot"],
        "assist": row["assist"],
        "blocked": row["blocked"],
        "credits": row["credits"],
        "net": row["net_credits"],
        "xp": row["xp"],
        "kills": row["kills"],
        "rating": row["rating"],
        "duration": row["duration"],
        "dmg_ratio": row["dmg_ratio"],
    }


def build(rows: list, granularity: str | None = None, battle_limit: int = 400,
          expected: dict | None = None) -> dict:
    rows = list(rows)
    summary = _agg(rows)
    summary["best_damage"] = max((r["damage"] for r in rows), default=0)
    summary["best_battle"] = None
    if rows:
        best = max(rows, key=lambda r: r["damage"])
        summary["best_battle"] = {
            "damage": best["damage"],
            "tank": best["tank"],
            "map": best["map_name"],
            "played_at": best["played_at"],
        }

    granularity = granularity or "month"
    groups: dict[str, list] = defaultdict(list)
    labels: dict[str, str] = {}
    for row in rows:
        try:
            day = _date(row["date"])
        except (ValueError, TypeError):
            continue
        sort_key, key, label = _bucket(day, granularity)
        groups[key].append(row)
        labels[key] = (sort_key, label)

    series = []
    for key in sorted(groups, key=lambda k: labels[k][0]):
        stats = _agg(groups[key])
        series.append({
            "key": key,
            "label": labels[key][1],
            "battles": stats["battles"],
            "winrate": stats["winrate"],
            "damage_avg": stats["damage_avg"],
            "damage_total": stats["damage_total"],
            "spot_avg": stats["spot_avg"],
            "assist_avg": stats["assist_avg"],
            "blocked_avg": stats["blocked_avg"],
            "net_total": stats["net_total"],
            "xp_avg": stats["xp_avg"],
            "rating_avg": stats["rating_avg"],
        })

    tanks: dict[str, list] = defaultdict(list)
    for row in rows:
        tanks[row["tank"] or "—"].append(row)
    by_tank = []
    for tank, items in tanks.items():
        stats = _agg(items)
        comp_count: dict[int, int] = defaultdict(int)
        vehicle_count: dict[str, int] = defaultdict(int)
        tier_count: dict[int, int] = defaultdict(int)
        class_count: dict[str, int] = defaultdict(int)
        mastery_count: dict[int, int] = defaultdict(int)
        for item in items:
            if item["type_comp_descr"]:
                comp_count[item["type_comp_descr"]] += 1
            if item["vehicle"]:
                vehicle_count[item["vehicle"]] += 1
            if item["tier"]:
                tier_count[item["tier"]] += 1
            if item["tank_class"]:
                class_count[item["tank_class"]] += 1
            if item["mark_of_mastery"]:
                mastery_count[item["mark_of_mastery"]] += 1
        type_comp = max(comp_count, key=comp_count.get) if comp_count else 0
        vehicle = max(vehicle_count, key=vehicle_count.get) if vehicle_count else ""
        rating_wn8 = None
        if expected and type_comp:
            rating_wn8 = _wn8.rating(
                stats["damage_avg"], stats["spot_avg"], stats["kills_avg"],
                stats["def_avg"], stats["winrate"], expected.get(type_comp),
            )
        by_tank.append({
            "tank": tank,
            "vehicle": vehicle,
            "type_comp": type_comp,
            "tier": max(tier_count, key=tier_count.get) if tier_count else None,
            "tank_class": max(class_count, key=class_count.get) if class_count else None,
            "nation": items[0]["nation_ru"],
            "nation_code": items[0]["nation"],
            "battles": stats["battles"],
            "winrate": stats["winrate"],
            "damage_avg": stats["damage_avg"],
            "damage_total": stats["damage_total"],
            "xp_avg": stats["xp_avg"],
            "rating": stats["rating_avg"],
            "wn8": rating_wn8,
            "net": stats["net_total"],
            "spot_avg": stats["spot_avg"],
            "assist_avg": stats["assist_avg"],
            "blocked_avg": stats["blocked_avg"],
            "kills_avg": stats["kills_avg"],
            "survival_rate": stats["survival_rate"],
            "accuracy": round(stats["hits_total"] * 100 / stats["shots_total"], 1) if stats["shots_total"] else None,
            "penetration": round(stats["pens_total"] * 100 / stats["hits_total"], 1) if stats["hits_total"] else None,
            "marks": stats["damage_rating_avg"] or None,
            "mastery": max(mastery_count, key=mastery_count.get) if mastery_count else None,
        })
    by_tank.sort(key=lambda t: (-t["battles"], t["tank"]))

    known = [t for t in by_tank if t["wn8"] is not None]
    if known:
        weight = sum(t["battles"] for t in known)
        summary["wn8"] = round(sum(t["wn8"] * t["battles"] for t in known) / weight, 0) if weight else None
    else:
        summary["wn8"] = None

    maps: dict[str, list] = defaultdict(list)
    for row in rows:
        maps[row["map_name"] or "—"].append(row)
    by_map = []
    for name, items in maps.items():
        stats = _agg(items)
        by_map.append({
            "map": name,
            "map_id": items[0]["map_id"],
            "battles": stats["battles"],
            "wins": stats["wins"],
            "winrate": stats["winrate"],
            "damage_avg": stats["damage_avg"],
            "damage_total": stats["damage_total"],
            "xp_avg": stats["xp_avg"],
            "kills_avg": stats["kills_avg"],
            "survival_rate": stats["survival_rate"],
            "spot_avg": stats["spot_avg"],
            "assist_avg": stats["assist_avg"],
            "blocked_avg": stats["blocked_avg"],
            "net": stats["net_total"],
            "rating": stats["rating_avg"],
            "tanks": len({item["tank"] for item in items}),
        })
    by_map.sort(key=lambda m: (-m["battles"], m["map"]))

    spawn_groups: dict[str, list] = defaultdict(list)
    for row in rows:
        if row["spawn"]:
            spawn_groups[row["spawn"]].append(row)
    by_spawn = []
    for side in ("top", "bottom", "left", "right"):
        items = spawn_groups.get(side)
        if not items:
            continue
        stats = _agg(items)
        by_spawn.append({
            "spawn": side,
            "battles": stats["battles"],
            "wins": stats["wins"],
            "winrate": stats["winrate"],
            "damage_avg": stats["damage_avg"],
            "xp_avg": stats["xp_avg"],
            "kills_avg": stats["kills_avg"],
            "survival_rate": stats["survival_rate"],
            "rating": stats["rating_avg"],
            "net": stats["net_total"],
        })

    types: dict[str, list] = defaultdict(list)
    for row in rows:
        types[row["battle_label"] or "—"].append(row)
    by_type = []
    for name, items in types.items():
        stats = _agg(items)
        by_type.append({
            "type": name,
            "battles": stats["battles"],
            "winrate": stats["winrate"],
            "damage_avg": stats["damage_avg"],
        })
    by_type.sort(key=lambda t: -t["battles"])

    # по-боевой ряд: каждая точка графика — отдельный бой
    chronological = sorted(rows, key=lambda r: r["ts"])
    battle_series = []
    cumulative_wins = 0
    for number, row in enumerate(chronological, 1):
        cumulative_wins += row["win"]
        battle_series.append({
            "i": number,
            "date": row["date"],
            "time": (row["played_at"] or "")[11:16],
            "label": f"{row['date'][8:10]}.{row['date'][5:7]}",
            "damage": row["damage"],
            "spot": row["spot"],
            "assist": row["assist"],
            "blocked": row["blocked"],
            "net": row["net_credits"],
            "xp": row["xp"],
            "rating": row["rating"],
            "kills": row["kills"],
            "cum_win": round(cumulative_wins * 100 / number, 1),
            "win": row["win"],
            "tank": row["tank"],
            "map": row["map_name"],
            "result": row["result"],
        })

    ordered = sorted(rows, key=lambda r: r["ts"], reverse=True)
    battles = [_battle_row(r) for r in ordered[:battle_limit]]

    return {
        "summary": summary,
        "series": series,
        "granularity": granularity,
        "by_tank": by_tank,
        "by_map": by_map,
        "by_type": by_type,
        "by_spawn": by_spawn,
        "battles": battles,
        "battle_series": battle_series,
        "battles_total": len(rows),
    }
