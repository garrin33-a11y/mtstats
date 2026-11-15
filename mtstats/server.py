"""HTTP-сервер и JSON API (только стандартная библиотека)."""

from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import threading
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, config as cfg, db, paths, replay, stats

try:
    from . import gui
except Exception:  # noqa: BLE001 - без tkinter работаем в браузере
    gui = None
from . import wn8 as wn8_module

WEB_DIR = paths.resource(os.path.join("mtstats", "web"))

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

_ICON_CACHE: dict[str, bytes] = {}
_MAP_CACHE: dict[str, bytes] = {}
_EXPECTED: dict | None = None


def needs_setup(config: dict) -> bool:
    """True, пока не выбрана ни одна существующая папка с реплеями."""
    folders = [folder for folder in (config.get("replays") or []) if folder and os.path.isdir(folder)]
    return not folders


def replay_files_count(folder: str) -> int:
    try:
        return len(replay.parse_folder(folder))
    except OSError:
        return 0


def expected_values() -> dict:
    """WN8-ожидания XVM (читаются один раз)."""
    global _EXPECTED
    if _EXPECTED is None:
        _EXPECTED = wn8_module.load()
    return _EXPECTED


def _icon_packages(config: dict) -> list[str]:
    """Пути к .pkg с иконками техники."""
    packages: list[str] = []
    game_root = config.get("game_root")
    roots = [game_root] if game_root else []
    for folder in config.get("replays", []):
        roots.append(os.path.dirname(os.path.abspath(folder)))
    for root in roots:
        if not root:
            continue
        for name in ("gui-part1.pkg", "gui-part2.pkg"):
            path = os.path.join(root, "res", "packages", name)
            if os.path.isfile(path) and path not in packages:
                packages.append(path)
    return packages


def map_image(config: dict, map_id: str, kind: str = "minimap") -> bytes | None:
    """Картинка карты из клиента: мини-карта 300x300 или широкий превью 230x81."""
    if not map_id:
        return None
    key = f"{kind}:{map_id}".lower()
    if key in _MAP_CACHE:
        return _MAP_CACHE[key] or None

    # варианты имени: сама карта, затем базовые (новогодние/зимние/штурмовые версии)
    variants = []
    parts = map_id.lower().split("_")
    for size in range(len(parts), 1, -1):
        variants.append("_".join(parts[:size]))
    plural = []
    for variant in variants:
        plural.append(f"gui/maps/icons/map/{variant}.png")
    plural_thumbs = []
    for variant in variants:
        plural_thumbs.append(f"gui/maps/icons/map/battleLoading/{variant}.png")

    candidates = (plural + plural_thumbs) if kind == "minimap" else (plural_thumbs + plural)

    result = None
    for package in _icon_packages(config):
        try:
            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
                for candidate in candidates:
                    if candidate in names:
                        result = archive.read(candidate)
                        break
        except (OSError, zipfile.BadZipFile, KeyError):
            continue
        if result:
            break
    _MAP_CACHE[key] = result or b""
    return result


def map_placeholder(label: str, kind: str = "minimap") -> bytes:
    """Красивая заглушка для карт, которых нет в клиенте."""
    width, height = (300, 300) if kind != "thumb" else (230, 81)
    text = (label or "").strip() or "Карта"
    if len(text) > 22:
        text = text[:21] + "…"
    safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    if kind == "thumb":
        cx, cy, radius = 40, height / 2, 20
        text_x, text_y, text_size = 78, height / 2 + 5, 15
        anchor = "start"
    else:
        cx, cy, radius = width / 2, height / 2 - 16, 52
        text_x, text_y, text_size = width / 2, height - 34, 19
        anchor = "middle"

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#f7f7f9"/><stop offset="1" stop-color="#ececf0"/>
</linearGradient>
<pattern id="grid" width="22" height="22" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
<line x1="0" y1="0" x2="0" y2="22" stroke="#e3e3e8" stroke-width="1"/>
</pattern>
</defs>
<rect width="{width}" height="{height}" fill="url(#bg)"/>
<rect width="{width}" height="{height}" fill="url(#grid)" opacity="0.55"/>
<g fill="none" stroke="#b9b9c0" stroke-opacity="0.9" stroke-width="1.4">
<circle cx="{cx}" cy="{cy}" r="{radius}"/>
<circle cx="{cx}" cy="{cy}" r="{radius * 0.42}" stroke-opacity="0.3"/>
<path d="M{cx - radius - 8} {cy} H{cx - radius * 0.55} M{cx + radius * 0.55} {cy} H{cx + radius + 8}"/>
<path d="M{cx} {cy - radius - 8} V{cy - radius * 0.55} M{cx} {cy + radius * 0.55} V{cy + radius + 8}"/>
</g>
<text x="{text_x}" y="{text_y}" text-anchor="{anchor}" fill="#86868b"
 font-family="Inter, Segoe UI, Arial, sans-serif" font-size="{text_size}" font-weight="600">{safe}</text>
</svg>"""
    return svg.encode("utf-8")


def tank_icon(config: dict, vehicle: str) -> bytes | None:
    """PNG-иконка танка из клиента (contour -> small -> большая картинка)."""
    if not vehicle:
        return None
    key = vehicle.lower()
    if key in _ICON_CACHE:
        return _ICON_CACHE[key] or None
    norm = vehicle.replace(":", "-")
    short = norm.split("-", 1)[1] if "-" in norm else norm

    # готовые обрезанные иконки (см. tools/build_tank_icons.py)
    local_dir = os.path.join(paths.user_dir(), "assets", "tank_icons")
    if not os.path.isdir(local_dir):
        local_dir = paths.resource(os.path.join("data", "tank_icons"))
    local = os.path.join(local_dir, f"{short.lower()}.png")
    if os.path.isfile(local):
        with open(local, "rb") as fh:
            data = fh.read()
        _ICON_CACHE[key] = data
        return data
    candidates = [
        # цветной рендер из клиента лучше всего смотрится на тёмном фоне,
        # затем цветная «маленькая» иконка, и только потом контур
        f"gui/maps/icons/vehicle/420x307/{short.lower()}.png",
        f"gui/maps/icons/vehicle/small/{norm}.png",
        f"gui/maps/icons/vehicle/contour/{norm}.png",
        f"gui/maps/icons/vehicle/contour/{norm}_T.png",
    ]
    result = None
    for package in _icon_packages(config):
        try:
            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
                for candidate in candidates:
                    if candidate in names:
                        result = archive.read(candidate)
                        break
        except (OSError, zipfile.BadZipFile, KeyError):
            continue
        if result:
            break
    _ICON_CACHE[key] = result or b""
    return result


class StatsServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, conn, config):
        super().__init__(address, handler)
        self.conn = conn
        self.config = config
        self.lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "MTStats/1.0"
    protocol_version = "HTTP/1.1"

    # --- служебное ---------------------------------------------------
    def log_message(self, fmt, *args):  # noqa: A003 - сигнатура stdlib
        pass

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 500) -> None:
        self._json({"error": message}, status)

    # --- маршрутизация ----------------------------------------------
    def do_GET(self):  # noqa: N802 - stdlib
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path in ("/setup", "/setup/"):
                return self._static("setup.html")
            if path in ("/about", "/about/"):
                return self._static("about.html")
            if path in ("/", "/index.html"):
                if needs_setup(self.server.config):
                    return self._redirect("/setup")
                return self._static("index.html")
            if path in ("/tanks", "/tanks/"):
                return self._static("tanks.html")
            if path in ("/tank", "/tank/"):
                return self._static("tank.html")
            if path in ("/maps", "/maps/"):
                return self._static("maps.html")
            if path in ("/map", "/map/"):
                return self._static("map.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path.startswith("/api/icon/"):
                return self._api_icon(path[len("/api/icon/"):])
            if path.startswith("/api/mapicon/"):
                return self._api_mapicon(path[len("/api/mapicon/"):], query)
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if path == "/api/data":
                return self._api_data(query)
            if path == "/api/tanks":
                return self._api_tanks(query)
            if path == "/api/tank":
                return self._api_tank(query)
            if path == "/api/maps":
                return self._api_maps(query)
            if path == "/api/map":
                return self._api_map(query)
            if path == "/api/status":
                return self._api_status()
            if path == "/api/setup/status":
                return self._api_setup_status()
            if path == "/api/export.csv":
                return self._api_csv(query)
            if path == "/api/browse":
                return self._api_browse()
            self._error("не найдено", 404)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - показываем ошибку в интерфейсе
            self._error(f"{type(exc).__name__}: {exc}", 500)

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/setup":
            return self._api_setup()
        if parsed.path == "/api/refresh":
            try:
                server = self.server
                with server.lock:
                    summary = db.import_folders(
                        server.conn,
                        server.config.get("replays", []),
                        server.config.get("json_dirs", []),
                    )
                summary["errors"] = (summary.get("errors") or [])[:15]
                return self._json({"ok": True, "import": summary})
            except Exception as exc:  # noqa: BLE001
                return self._error(f"{type(exc).__name__}: {exc}", 500)
        self._error("не найдено", 404)

    # --- обработчики ------------------------------------------------
    def _static(self, relative: str) -> None:
        relative = urllib.parse.unquote(relative)
        target = os.path.normpath(os.path.join(WEB_DIR, relative))
        if not target.startswith(os.path.normpath(WEB_DIR)) or not os.path.isfile(target):
            return self._error("файл не найден", 404)
        with open(target, "rb") as fh:
            body = fh.read()
        ext = os.path.splitext(target)[1].lower()
        self._send(200, body, MIME.get(ext) or mimetypes.guess_type(target)[0] or "application/octet-stream")

    def _api_tanks(self, query: dict) -> None:
        server = self.server
        period = (query.get("period") or ["all"])[0]
        start, end, label = stats.resolve_period(
            period, (query.get("from") or [None])[0], (query.get("to") or [None])[0]
        )
        with server.lock:
            rows = db.select_range(
                server.conn,
                start.isoformat() if start else None,
                end.isoformat() if end else None,
            )
        granularity = stats.auto_granularity(start, end)
        payload = stats.build(rows, granularity, battle_limit=1, expected=expected_values())
        self._json({
            "tanks": payload["by_tank"],
            "summary": payload["summary"],
            "wn8_available": bool(expected_values()),
            "request": {
                "period": period, "label": label,
                "from": start.isoformat() if start else None,
                "to": end.isoformat() if end else None,
            },
        })

    def _api_tank(self, query: dict) -> None:
        server = self.server
        name = (query.get("tank") or [""])[0]
        if not name:
            return self._error("не указан танк", 400)
        period = (query.get("period") or ["all"])[0]
        start, end, label = stats.resolve_period(
            period, (query.get("from") or [None])[0], (query.get("to") or [None])[0]
        )
        with server.lock:
            rows = db.select_range(
                server.conn,
                start.isoformat() if start else None,
                end.isoformat() if end else None,
            )
        mine = [row for row in rows if (row["tank"] or "—") == name]
        granularity = stats.auto_granularity(start, end)
        if timeline := query.get("granularity"):
            if timeline[0] in ("day", "week", "month", "year"):
                granularity = timeline[0]
        payload = stats.build(mine, granularity, battle_limit=500, expected=expected_values())
        vehicle = next((row["vehicle"] for row in mine if row["vehicle"]), "")
        tiers = [row["tier"] for row in mine if row["tier"]]
        classes = [row["tank_class"] for row in mine if row["tank_class"]]
        payload["tank"] = {
            "name": name,
            "vehicle": vehicle,
            "nation": mine[0]["nation_ru"] if mine else "",
            "type_comp": mine[0]["type_comp_descr"] if mine else 0,
            "tier": max(set(tiers), key=tiers.count) if tiers else None,
            "tank_class": max(set(classes), key=classes.count) if classes else None,
        }
        payload["request"] = {
            "period": period, "label": label,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
            "granularity": granularity,
        }
        self._json(payload)

    def _api_setup_status(self) -> None:
        config = self.server.config
        detected = [folder for folder in cfg.detect_replay_folders() if os.path.isdir(folder)]
        current = [folder for folder in (config.get("replays") or []) if os.path.isdir(folder)]
        self._json({
            "needs_setup": needs_setup(config),
            "current": current,
            "detected": detected,
            "browse_available": bool(gui and gui.available()),
        })

    def _api_browse(self) -> None:
        folder = gui.ask_folder("") if gui else None
        self._json({"path": folder})

    def _api_setup(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._error("некорректный запрос", 400)

        folder = str(payload.get("folder") or "").strip().strip('"')
        if not folder:
            return self._error("не указана папка", 400)
        folder = os.path.abspath(os.path.expandvars(os.path.expanduser(folder)))
        if not os.path.isdir(folder):
            return self._error(f"папка не найдена: {folder}", 400)

        server = self.server
        found = replay_files_count(folder)
        config = dict(server.config)
        config["replays"] = [folder]
        config["json_dirs"] = cfg.detect_json_folders([folder])
        cfg.save(config)
        server.config.clear()
        server.config.update(config)

        with server.lock:
            summary = db.import_folders(
                server.conn, config.get("replays", []), config.get("json_dirs", [])
            )
        self._json({
            "ok": True,
            "folder": folder,
            "found": found,
            "import": {
                "battles": summary.get("battles_in_db", 0),
                "imported": summary.get("imported", 0),
                "failed": summary.get("failed", 0),
            },
        })

    def _api_maps(self, query: dict) -> None:
        server = self.server
        period = (query.get("period") or ["all"])[0]
        start, end, label = stats.resolve_period(
            period, (query.get("from") or [None])[0], (query.get("to") or [None])[0]
        )
        with server.lock:
            rows = db.select_range(
                server.conn,
                start.isoformat() if start else None,
                end.isoformat() if end else None,
            )
        granularity = stats.auto_granularity(start, end)
        payload = stats.build(rows, granularity, battle_limit=1, expected=expected_values())
        self._json({
            "maps": payload["by_map"],
            "summary": payload["summary"],
            "request": {
                "period": period, "label": label,
                "from": start.isoformat() if start else None,
                "to": end.isoformat() if end else None,
            },
        })

    def _api_icon(self, raw_name: str) -> None:
        name = urllib.parse.unquote(raw_name or "")
        if name.lower().endswith(".png"):
            name = name[:-4]
        data = tank_icon(self.server.config, name)
        if not data:
            return self._error("иконка не найдена", 404)
        self._send(200, data, "image/png", {"Cache-Control": "public, max-age=604800"})

    def _api_mapicon(self, raw_name: str, query: dict) -> None:
        name = urllib.parse.unquote(raw_name or "")
        if name.lower().endswith(".png"):
            name = name[:-4]
        kind = (query.get("kind") or ["minimap"])[0]
        normalised = "thumb" if kind == "thumb" else "minimap"
        data = map_image(self.server.config, name, normalised)
        if data:
            return self._send(200, data, "image/png", {"Cache-Control": "public, max-age=604800"})
        label = urllib.parse.unquote((query.get("name") or [name])[0])
        self._send(200, map_placeholder(label, normalised), "image/svg+xml",
                   {"Cache-Control": "public, max-age=86400"})

    def _api_map(self, query: dict) -> None:
        server = self.server
        name = (query.get("map") or [""])[0]
        if not name:
            return self._error("не указана карта", 400)
        period = (query.get("period") or ["all"])[0]
        start, end, label = stats.resolve_period(
            period, (query.get("from") or [None])[0], (query.get("to") or [None])[0]
        )
        with server.lock:
            rows = db.select_range(
                server.conn,
                start.isoformat() if start else None,
                end.isoformat() if end else None,
            )
        mine = [row for row in rows if (row["map_name"] or "") == name]
        granularity = stats.auto_granularity(start, end)
        payload = stats.build(mine, granularity, battle_limit=500, expected=expected_values())
        payload["map"] = {
            "name": name,
            "map_id": mine[0]["map_id"] if mine else "",
        }
        payload["request"] = {
            "period": period, "label": label,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
            "granularity": granularity,
        }
        self._json(payload)

    def _api_status(self) -> None:
        server = self.server
        with server.lock:
            conn = server.conn
            lo, hi, total = db.bounds(conn)
            row = conn.execute(
                "SELECT player_name, COUNT(*) AS n FROM battles "
                "WHERE player_name != '' GROUP BY player_name ORDER BY n DESC LIMIT 1"
            ).fetchone()
            last_import = db.get_meta(conn, "last_import", "")
            unread = db.get_meta(conn, "last_unread", "0")
            unread_no_results = db.get_meta(conn, "last_unread_no_results", "0")
            from_mod = conn.execute(
                "SELECT COUNT(*) FROM battles WHERE source='mod_json'"
            ).fetchone()[0]
            partial = conn.execute(
                "SELECT COUNT(*) FROM battles WHERE partial=1"
            ).fetchone()[0]
            no_farm = conn.execute(
                "SELECT COUNT(*) FROM battles WHERE net_credits IS NULL"
            ).fetchone()[0]
        folders = server.config.get("replays", [])
        json_folders = server.config.get("json_dirs", [])
        self._json({
            "player": row["player_name"] if row else "",
            "battles": total,
            "from_mod": from_mod,
            "partial": partial,
            "no_farm": no_farm,
            "date_min": lo,
            "date_max": hi,
            "last_import": last_import,
            "unread": unread,
            "unread_no_results": unread_no_results,
            "version": __version__,
            "folders": folders,
            "json_folders": json_folders,
            "db": server.config.get("db", ""),
        })

    def _api_data(self, query: dict) -> None:
        server = self.server
        period = (query.get("period") or ["month"])[0]
        date_from = (query.get("from") or [None])[0]
        date_to = (query.get("to") or [None])[0]
        granularity = (query.get("granularity") or [""])[0] or None
        try:
            limit = max(1, min(int((query.get("limit") or ["400"])[0]), 5000))
        except ValueError:
            limit = 400

        start, end, label = stats.resolve_period(period, date_from, date_to)
        if granularity not in ("day", "week", "month", "year"):
            granularity = stats.auto_granularity(start, end)
        with server.lock:
            conn = server.conn
            rows = db.select_range(
                conn,
                start.isoformat() if start else None,
                end.isoformat() if end else None,
            )
            lo, hi, total = db.bounds(conn)
            last_import = db.get_meta(conn, "last_import", "")
        payload = stats.build(rows, granularity, battle_limit=limit, expected=expected_values())
        payload["request"] = {
            "period": period,
            "label": label,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
            "granularity": granularity,
        }
        payload["db"] = {
            "battles": total,
            "date_min": lo,
            "date_max": hi,
            "last_import": last_import,
        }
        self._json(payload)

    def _api_csv(self, query: dict) -> None:
        server = self.server
        period = (query.get("period") or ["all"])[0]
        start, end, _label = stats.resolve_period(
            period, (query.get("from") or [None])[0], (query.get("to") or [None])[0]
        )
        with server.lock:
            conn = server.conn
            rows = db.select_range(
                conn,
                start.isoformat() if start else None,
                end.isoformat() if end else None,
            )
        rows = sorted(rows, key=lambda r: r["ts"], reverse=True)
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow([
            "Дата", "Время", "Карта", "Танк", "Нация", "Режим", "Результат",
            "Урон", "Засвет", "Помощь", "Танкование", "Получено", "Убийства",
            "Выстрелы", "Попадания", "Пробития", "Кредиты", "Ремонт", "Снаряды",
            "Снаряжение", "Чистый фарм", "Опыт", "Свободный опыт", "Жив", "Рейтинг",
            "Длительность", "Файл",
        ])
        for row in rows:
            writer.writerow([
                row["date"], row["played_at"][11:16], row["map_name"], row["tank"],
                row["nation_ru"], row["battle_label"], row["result"],
                row["damage"], row["spot"], row["assist"], row["blocked"],
                row["received"], row["kills"], row["shots"], row["hits"],
                row["pens"], row["credits"], row["repair"], row["ammo"],
                row["consumables"], row["net_credits"], row["xp"], row["free_xp"],
                "да" if row["survived"] else "нет", row["rating"], row["duration"],
                os.path.basename(row["file"]),
            ])
        body = ("\ufeff" + buffer.getvalue()).encode("utf-8")
        name = f"mtstats_{start or 'all'}_{end or 'all'}.csv"
        self._send(200, body, "text/csv; charset=utf-8", {
            "Content-Disposition": f'attachment; filename="{name}"',
        })


def serve(config: dict) -> StatsServer:
    conn = db.connect(config["db"])
    server = StatsServer((config.get("host", "127.0.0.1"), int(config.get("port", 8765))), Handler, conn, config)
    return server
