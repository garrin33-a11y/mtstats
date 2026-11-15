"""Дозаполнение засвета и танкования по публичным страницам lesta-replays.ru.

У боёв, восстановленных из кэша мода, нет засвета и танкования. На странице
каждого реплея сайт показывает полную сводку:

    Урон: 879 · Фраги: 0 · Засвет: 0 · Урон по засвету и гусеницам: 331 ·
    Заблокировано бронёй: 390 · Опыт: 660 · Серебро: 31 855

Скрипт аккуратно (по одной странице, с паузой) забирает эти три числа и
обновляет базу.

Запуск: python tools/enrich_from_site.py [--delay 0.4] [--limit N]
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_DIR, "data", "mtstats.db")
CACHE_PATH = r"C:\Games\Tanki\mods\configs\lesta_replays_upload\site_replays.json"

PATTERNS = {
    "spot": re.compile(r"Засвет:\s*([\d\s]+)"),
    "assist": re.compile(r"Урон по засвету и гусеницам:\s*([\d\s]+)"),
    "blocked": re.compile(r"Заблокировано бронёй:\s*([\d\s]+)"),
    "damage": re.compile(r"Урон:\s*([\d\s]+)"),
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) mtstats/1.0",
    "Accept-Language": "ru-RU,ru;q=0.9",
}


def _number(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def fetch(url: str) -> str | None:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        print(f"    ошибка: {exc}")
        return None


def parse(html: str) -> dict | None:
    values = {}
    for field, pattern in PATTERNS.items():
        match = pattern.search(html)
        if not match:
            return None
        values[field] = _number(match.group(1))
    return values


def load_urls(account_id: int | None) -> dict[int, str]:
    if not os.path.isfile(CACHE_PATH):
        return {}
    with open(CACHE_PATH, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    urls: dict[int, str] = {}
    for key, block in (payload.get("accounts") or {}).items():
        if account_id and str(key) != str(account_id):
            continue
        for item in (block.get("items") or {}).values():
            arena = int(item.get("arena_unique_id") or 0)
            url = item.get("url")
            if arena and url:
                urls[arena] = url
    return urls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.4)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    urls = load_urls(None)
    print(f"ссылок в кэше мода: {len(urls)}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT arena_id, damage FROM battles WHERE spot IS NULL ORDER BY ts"
    ).fetchall()
    todo = [row for row in rows if row["arena_id"] in urls]
    if args.limit:
        todo = todo[: args.limit]
    print(f"боёв без засвета: {len(rows)}, из них есть ссылка: {len(todo)}")

    updated = failed = mismatch = 0
    for index, row in enumerate(todo, 1):
        arena = row["arena_id"]
        html = fetch(urls[arena])
        if not html:
            failed += 1
        else:
            values = parse(html)
            if not values:
                failed += 1
            else:
                if values["damage"] and abs(values["damage"] - row["damage"]) > max(50, row["damage"] * 0.05):
                    mismatch += 1
                conn.execute(
                    "UPDATE battles SET spot=?, assist=?, blocked=?, partial=0 "
                    "WHERE arena_id=?",
                    (values["spot"], values["assist"], values["blocked"], arena),
                )
                updated += 1
        if index % 25 == 0:
            conn.commit()
            print(f"  {index}/{len(todo)}: обновлено {updated}, ошибок {failed}")
        time.sleep(args.delay)

    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM battles WHERE spot IS NULL").fetchone()[0]
    print(f"обновлено: {updated}, ошибок: {failed}, расхождений по урону: {mismatch}")
    print(f"осталось без засвета: {left}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
