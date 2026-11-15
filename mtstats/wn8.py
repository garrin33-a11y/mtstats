"""WN8: расчёт по ожидаемым значениям из кэша XVM.

Файл `%APPDATA%\\Lesta\\MirTankov\\xvm\\cache\\wn8exp.json.gz.dat` — это pickle
со строкой gzip-JSON внутри (так кэширует сам XVM). Внутри — по танку:
expDamage, expFrag, expSpot, expDef, expWinRate.
"""

from __future__ import annotations

import codecs
import gzip
import json
import os


def _unpickle_string(raw: bytes) -> bytes:
    """Достаёт строку из pickle-протокола 0 (S'...')."""
    if raw[:2] != b"S'":
        raise ValueError("не pickle-строка")
    index = 2
    while index < len(raw):
        byte = raw[index]
        if byte == 0x5C:  # обратный слэш — пропускаем экранированный байт
            index += 2
            continue
        if byte == 0x27:  # закрывающая кавычка
            break
        index += 1
    return codecs.escape_decode(raw[2:index])[0]


def default_cache_path() -> str | None:
    candidates = [
        os.path.expandvars(r"%APPDATA%\Lesta\MirTankov\xvm\cache\wn8exp.json.gz.dat"),
        os.path.expandvars(r"%APPDATA%\Wargaming.net\WorldOfTanks\xvm\cache\wn8exp.json.gz.dat"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def load(path: str | None = None) -> dict:
    """Возвращает {tank_id: ожидаемые значения}. Пустой словарь, если файла нет."""
    path = path or default_cache_path()
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        payload = _unpickle_string(raw) if raw[:2] == b"S'" else raw
        data = json.loads(gzip.decompress(payload).decode("utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError, gzip.BadGzipFile, UnicodeDecodeError):
        return {}
    return {int(row["IDNum"]): row for row in data.get("data") or [] if "IDNum" in row}


def rating(avg_damage: float, avg_spot: float, avg_frags: float, avg_def: float,
           winrate: float, expected: dict) -> float | None:
    """WN8 танка по его средним показателям."""
    if not expected:
        return None
    try:
        exp_damage = float(expected["expDamage"]) or 1.0
        exp_spot = float(expected["expSpot"]) or 1.0
        exp_frag = float(expected["expFrag"]) or 1.0
        exp_def = float(expected["expDef"]) or 1.0
        exp_win = float(expected["expWinRate"]) or 50.0
    except (KeyError, TypeError, ValueError):
        return None

    r_damage = avg_damage / exp_damage
    r_spot = avg_spot / exp_spot
    r_frag = avg_frags / exp_frag
    r_def = avg_def / exp_def
    r_win = winrate / exp_win

    value = (
        980 * r_damage
        + 210 * r_damage * r_frag
        + 155 * r_frag * r_spot
        + 75 * r_def * r_frag
        + 145 * min(1.8, r_win)
    )
    return round(value, 0)
