"""Запуск: импорт реплеев, локальный веб-интерфейс и окно управления."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

from . import config as cfg
from . import __version__, assets, db, paths, server


def _say(message: str) -> None:
    paths.log(message)
    try:
        print(message, flush=True)
    except (OSError, ValueError):
        pass


def _import(config: dict, force: bool = False) -> dict:
    conn = db.connect(config["db"])
    try:
        summary = db.import_folders(
            conn,
            config.get("replays", []),
            config.get("json_dirs", []),
            force=force,
        )
    finally:
        conn.close()
    return summary


def _report(summary: dict) -> None:
    _say(f"Папки с реплеями: {', '.join(summary.get('folders') or ['—'])}")
    json_folders = summary.get("json_folders") or []
    if json_folders:
        _say(f"JSON-выгрузки модов: {', '.join(json_folders)}")
    _say(f"Файлов просмотрено: {summary['scanned']}, новых: {summary['imported']}, "
         f"обновлено: {summary['updated']}, без изменений: {summary['skipped']}, "
         f"не прочитано: {summary['failed']}")
    _say(f"Боёв в базе: {summary['battles_in_db']}")
    for name, message in (summary.get("errors") or [])[:10]:
        _say(f"  - {name}: {message}")


def _status_text(config: dict) -> str:
    try:
        conn = db.connect(config["db"])
        try:
            lo, hi, total = db.bounds(conn)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return "Статистика готова"
    if not total:
        return "Пока нет боёв — укажите папку с реплеями"
    return f"Боёв в базе: {total} · {lo} … {hi}"


def _free_port(host: str, start: int) -> server.StatsServer:
    last_error: OSError | None = None
    for offset in range(25):
        try:
            return server.serve({**_CONFIG, "host": host, "port": start + offset})
        except OSError as exc:
            last_error = exc
    raise OSError(f"не удалось занять порт: {last_error}")


_CONFIG: dict = {}


def main(argv: list[str] | None = None) -> int:
    global _CONFIG

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(prog="MTstats", description="Статистика боёв «Мир танков» по реплеям.")
    parser.add_argument("command", nargs="?", default="serve",
                        choices=["serve", "import", "export"], help="что делать (по умолчанию serve)")
    parser.add_argument("--port", type=int, default=None, help="порт веб-интерфейса")
    parser.add_argument("--host", default=None, help="адрес прослушивания")
    parser.add_argument("--folder", action="append", default=None, help="папка с реплеями")
    parser.add_argument("--json-folder", action="append", default=None, help="папка с JSON мода")
    parser.add_argument("--force", action="store_true", help="перечитать все реплеи заново")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    parser.add_argument("--gui", action="store_true", help="показать окно управления")
    args = parser.parse_args(argv)

    config = cfg.load()
    if args.folder:
        config["replays"] = [os.path.abspath(p) for p in args.folder]
        config["json_dirs"] = cfg.detect_json_folders(config["replays"])
    if args.json_folder:
        config["json_dirs"] = [os.path.abspath(p) for p in args.json_folder]
    if args.port:
        config["port"] = args.port
    if args.host:
        config["host"] = args.host
    if not os.path.isfile(cfg.CONFIG_PATH):
        cfg.save(config)

    _CONFIG = config
    _say(f"MTstats {__version__} (тестовая версия) запускается")

    # справочник техники нужен уже при импорте — собираем из клиента заранее
    if assets.ensure_tank_db(config):
        _say("Справочник техники собран из клиента игры")

    started = time.time()
    summary = _import(config)
    _report(summary)
    _say(f"Импорт занял {time.time() - started:.1f} с")

    # респауны и иконки требуют списков из базы
    try:
        conn = db.connect(config["db"])
        try:
            map_ids = [row[0] for row in conn.execute(
                "SELECT DISTINCT map_id FROM battles WHERE map_id != ''"
            )]
            vehicles = [row[0] for row in conn.execute(
                "SELECT DISTINCT vehicle_id FROM battles WHERE vehicle_id != ''"
            )]
            if assets.ensure_map_spawns(config, map_ids):
                db.fill_spawns(conn)
                _say("Респауны собраны из клиента игры")
            db.enrich_tiers(conn)
        finally:
            conn.close()
        if assets.ensure_icons(config, vehicles):
            _say("Иконки техники подготовлены")
    except Exception as exc:  # noqa: BLE001 - без справочников программа работает
        _say(f"Справочники не собраны: {exc}")

    if args.command in ("import", "export"):
        return 0

    host = config.get("host", "127.0.0.1")
    httpd = _free_port(host, int(config.get("port", 8765)))
    port = httpd.server_address[1]
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "") else host
    url = f"http://{shown_host}:{port}/"
    _say(f"Статистика доступна: {url}")

    use_gui = args.gui or paths.is_frozen()
    if use_gui:
        try:
            return _run_gui(httpd, url, config, args.no_browser)
        except Exception as exc:  # noqa: BLE001 - окно не критично
            paths.log(f"окно управления не запустилось: {type(exc).__name__}: {exc}")
            if not args.no_browser:
                webbrowser.open(url)

    if config.get("open_browser", True) and not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    _say("Остановить: Ctrl+C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _say("Остановлено")
    finally:
        httpd.server_close()
    return 0


def _run_gui(httpd, url: str, config: dict, no_browser: bool) -> int:
    """Окно управления: сервер крутится в фоне, окно — в главном потоке."""
    from . import gui

    def open_stats() -> None:
        webbrowser.open(url)

    def open_folder() -> None:
        webbrowser.open(url.rstrip("/") + "/setup")

    def refresh() -> None:
        window.set_status("Обновляю реплеи…")
        threading.Thread(target=_refresh_worker, daemon=True).start()

    def quit_app() -> None:
        httpd.shutdown()
        httpd.server_close()
        window.close()

    def _refresh_worker() -> None:
        try:
            summary = _import(config)
            window.set_status(
                f"Обновлено. Боёв в базе: {summary['battles_in_db']}"
            )
        except Exception as exc:  # noqa: BLE001
            paths.log(f"ошибка импорта: {exc}")
            window.set_status("Не удалось обновить реплеи (подробности в mtstats.log)")

    try:
        window = gui.ControlWindow(
        "MTstats — статистика реплеев",
        "Статистика доступна в браузере.\n" + url,
            {"open": open_stats, "folder": open_folder, "refresh": refresh, "quit": quit_app},
        )
    except Exception as exc:  # noqa: BLE001 - без окна тоже работаем
        paths.log(f"окно управления недоступно: {exc}")
        if not no_browser:
            webbrowser.open(url)
        httpd.serve_forever()
        return 0
    window.set_status(_status_text(config) + f"\n{url}")

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if config.get("open_browser", True) and not no_browser:
        threading.Timer(0.7, open_stats).start()

    try:
        window.run()
    except KeyboardInterrupt:
        quit_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
