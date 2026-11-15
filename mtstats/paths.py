"""Пути: что лежит рядом с программой, а что — в пользовательских данных.

В обычном запуске (из исходников) всё лежит в папке проекта. В собранном
.exe ресурсы (интерфейс, справочники) распаковываются во временную папку
PyInstaller, а настройки и база должны лежать в профиле пользователя —
иначе программа не сможет писать в Program Files.
"""

from __future__ import annotations

import os
import sys

APP_NAME = "MTstats"
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PACKAGE_DIR)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource(relative: str) -> str:
    """Файл только для чтения: интерфейс, справочники, иконки."""
    base = getattr(sys, "_MEIPASS", None) or PROJECT_DIR
    return os.path.join(base, relative)


def user_dir() -> str:
    """Папка для настроек и базы: %APPDATA%\\MTstats."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def user_file(name: str) -> str:
    return os.path.join(user_dir(), name)


def migrate_legacy() -> None:
    """Первый запуск новой версии: переносим базу и настройки из папки проекта."""
    if is_frozen():
        return
    pairs = [
        (os.path.join(PROJECT_DIR, "data", "mtstats.db"), user_file("mtstats.db")),
        (os.path.join(PROJECT_DIR, "config.json"), user_file("config.json")),
    ]
    for source, target in pairs:
        try:
            if os.path.isfile(source) and not os.path.exists(target):
                import shutil

                shutil.copy2(source, target)
        except OSError:
            pass


def log(message: str) -> None:
    """Пишет строку в mtstats.log рядом с настройками (для .exe без консоли)."""
    try:
        import time

        path = user_file("mtstats.log")
        if os.path.isfile(path) and os.path.getsize(path) > 1_000_000:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except OSError:
        pass
