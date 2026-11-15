"""Сборка MTstats.exe (PyInstaller).

Запуск: python build_exe.py
Результат: dist\\MTstats.exe — один файл, который можно положить куда угодно.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Нужен PyInstaller: python -m pip install pyinstaller")
        return 1

    add_data = [
        (os.path.join("mtstats", "web"), os.path.join("mtstats", "web")),
        (os.path.join("data", "tank_db.json"), "data"),
        (os.path.join("data", "map_spawns.json"), "data"),
        (os.path.join("data", "tank_icons"), os.path.join("data", "tank_icons")),
    ]

    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "MTstats",
        "--icon", os.path.join(PROJECT_DIR, "app.ico"),
        # распаковываем не в TEMP (его часто блокируют антивирусы и политики),
        # а в профиль пользователя
        "--runtime-tmpdir", r"%LOCALAPPDATA%\MTstats\runtime",
        "--hidden-import", "PIL.Image",
        "--paths", PROJECT_DIR,
    ]
    for source, target in add_data:
        if not os.path.exists(os.path.join(PROJECT_DIR, source)):
            continue  # справочники собираются на компьютере пользователя
        command += ["--add-data", f"{source};{target}"]

    command.append(os.path.join(PROJECT_DIR, "run.py"))

    for folder in ("build", "dist"):
        path = os.path.join(PROJECT_DIR, folder)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)

    print("собираю…")
    result = subprocess.run(command, cwd=PROJECT_DIR)
    if result.returncode != 0:
        print("сборка не удалась")
        return result.returncode

    # портативная сборка (папка, без распаковки во временные файлы)
    portable = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onedir", "--windowed",
        "--name", "MTstats-portable",
        "--icon", os.path.join(PROJECT_DIR, "app.ico"),
        "--paths", PROJECT_DIR,
    ]
    for source, target in add_data:
        if os.path.exists(os.path.join(PROJECT_DIR, source)):
            portable += ["--add-data", f"{source};{target}"]
    portable.append(os.path.join(PROJECT_DIR, "run.py"))
    subprocess.run(portable, cwd=PROJECT_DIR)

    portable_dir = os.path.join(PROJECT_DIR, "dist", "MTstats-portable")
    if os.path.isdir(portable_dir):
        archive = os.path.join(PROJECT_DIR, "dist", "MTstats-portable")
        shutil.make_archive(archive, "zip", os.path.join(PROJECT_DIR, "dist"), "MTstats-portable")
        print("портативная версия: dist\\MTstats-portable\\ и dist\\MTstats-portable.zip")

    exe = os.path.join(PROJECT_DIR, "dist", "MTstats.exe")
    if os.path.isfile(exe):
        size = os.path.getsize(exe) / (1024 * 1024)
        print(f"готово: {exe} ({size:.1f} МБ)")
        return 0
    print("exe не найден")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
