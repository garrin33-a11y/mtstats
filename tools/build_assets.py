"""Сборка справочников из установленного клиента игры.

Обычно это происходит само при первом запуске программы. Скрипт нужен, если
хочется пересобрать справочники вручную (например, после патча игры).

Запуск: python tools/build_assets.py [путь к корню клиента]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtstats import assets, config as cfg, db  # noqa: E402


def main() -> int:
    config = cfg.load()
    if len(sys.argv) > 1:
        root = os.path.abspath(sys.argv[1])
        config["replays"] = [os.path.join(root, "replays")]
    game_root = assets.detect_game_root(config)
    if not game_root:
        print("Клиент игры не найден. Укажите путь: python tools/build_assets.py C:\\Games\\Tanki")
        return 1

    print(f"клиент: {game_root}")
    print("справочник техники:", assets.ensure_tank_db(config) or "уже есть")

    conn = db.connect(config["db"])
    try:
        map_ids = [row[0] for row in conn.execute(
            "SELECT DISTINCT map_id FROM battles WHERE map_id != ''"
        )]
        vehicles = [row[0] for row in conn.execute(
            "SELECT DISTINCT vehicle_id FROM battles WHERE vehicle_id != ''"
        )]
    finally:
        conn.close()

    print("респауны:", assets.ensure_map_spawns(config, map_ids) or "уже есть")
    print("иконки:", assets.ensure_icons(config, vehicles))
    print("готово. Папка:", os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "MTstats", "assets"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
