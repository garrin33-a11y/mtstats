"""Точка входа для сборки .exe (PyInstaller) и обычного запуска из папки."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mtstats import paths  # noqa: E402
from mtstats.__main__ import main  # noqa: E402


def _fatal(exc: BaseException) -> None:
    import traceback

    text = "".join(traceback.format_exception(exc))
    paths.log("СТАРТ НЕ УДАЛСЯ:\n" + text)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Не удалось запустить MTstats.\n\nПодробности: " + paths.user_file("mtstats.log"),
            "MTstats",
            0x10,
        )
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001
        _fatal(error)
        sys.exit(1)
