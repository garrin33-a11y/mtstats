"""Декодер BigWorld PackedSection.

Так в клиенте «Мир танков» запакованы XML-описания техники
(`res/packages/scripts.pkg → scripts/item_defs/vehicles/*/*.xml`). Из них берутся
уровень и класс танка.

Алгоритм повторяет открытый декодер
https://github.com/marty-doc/BigWorldPackedSectionDecompiler (MIT-подобная
открытая реализация сообщества WoT), переписанный под Python 3 и только для
чтения нужных полей.
"""

from __future__ import annotations

import struct

MAGIC = 0x62A14E45

SECTION = 0
STRING = 1
INT = 2
FLOAT = 3
BOOL = 4
BLOB = 5
ENCRYPTED_BLOB = 6


class PackedSectionError(Exception):
    pass


def _load_strings(data: bytes, pos: int) -> tuple[list[str], int]:
    strings: list[str] = []
    while True:
        end = data.find(b"\x00", pos)
        if end < 0:
            raise PackedSectionError("незакрытая таблица строк")
        raw = data[pos:end]
        pos = end + 1
        if not raw:
            return strings, pos
        strings.append(raw.decode("utf-8", "strict"))


def _read_header(data: bytes, off: int, strings: list[str]):
    if off + 2 > len(data):
        raise PackedSectionError("обрезанный заголовок секции")
    count = struct.unpack_from("<H", data, off)[0]
    records_off = off + 2
    data_base = off + 2 + count * 6 + 4
    if data_base > len(data):
        raise PackedSectionError("заголовок секции выходит за файл")

    records = []
    for index in range(count + 1):
        point = records_off + index * 6
        size = 6 if index < count else 4
        if point + size > len(data):
            raise PackedSectionError("обрезанные записи секции")
        packed = struct.unpack_from("<I", data, point)[0]
        position = packed & 0x0FFFFFFF
        typ = (packed >> 28) & 0x0F
        key = None
        if index < count:
            key = struct.unpack_from("<H", data, point + 4)[0]
            if key >= len(strings):
                raise PackedSectionError(f"плохой индекс строки {key}")
        records.append((position, typ, key))
    return count, records, data_base


def _decode(raw: bytes, typ: int):
    if typ == STRING:
        return raw.decode("utf-8", "replace")
    if typ == INT:
        if len(raw) == 1:
            return struct.unpack("<b", raw)[0]
        if len(raw) == 2:
            return struct.unpack("<h", raw)[0]
        if len(raw) == 4:
            return struct.unpack("<i", raw)[0]
        return 0
    if typ == FLOAT:
        if len(raw) and len(raw) % 4 == 0:
            values = struct.unpack("<" + "f" * (len(raw) // 4), raw)
            return values[0] if len(values) == 1 else values
        return 0.0
    if typ == BOOL:
        return bool(raw)
    return raw


def _parse(data: bytes, off: int, strings: list[str], depth: int = 0):
    if depth > 200:
        raise PackedSectionError("слишком глубокая вложенность")
    count, records, base = _read_header(data, off, strings)
    nodes = []
    for index in range(count):
        start = records[index][0]
        end = records[index + 1][0]
        typ = records[index + 1][1]
        name = strings[records[index][2]]
        if start > end:
            raise PackedSectionError(f"плохой диапазон у <{name}>")
        chunk = data[base + start:base + end]
        if typ == SECTION:
            value = _parse(data, base + start, strings, depth + 1)
        else:
            value = _decode(chunk, typ)
        nodes.append((name, typ, value))
    return nodes


def parse(data: bytes) -> list:
    """Разбирает PackedSection в дерево [(имя, тип, значение), ...]."""
    if len(data) < 5:
        raise PackedSectionError("файл слишком мал")
    if struct.unpack_from("<I", data, 0)[0] != MAGIC:
        raise PackedSectionError("не PackedSection")
    strings, root = _load_strings(data, 5)
    return _parse(data, root, strings)


def find(node_list: list, name: str):
    """Первый узел с указанным именем (рекурсивно)."""
    for item_name, typ, value in node_list:
        if item_name == name:
            return typ, value
        if typ == SECTION:
            found = find(value, name)
            if found is not None:
                return found
    return None
