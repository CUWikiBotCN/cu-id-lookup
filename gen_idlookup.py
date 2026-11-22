#!/usr/bin/env python3
"""由原始语言文件 + 人工覆盖表生成 Data:Editor/IDLookup.json。

规则（与线上现行格式一致）：

1. 只取 ``main`` / ``buildings`` / ``moodles`` / ``other`` 四个命名空间；
2. 跳过以 ``dsc`` 结尾的键（那是对应条目的描述文案，不是条目本身）；
3. 条目 = ``{id: 键名, group: 命名空间, name: 中文名, aliases: []}``；
4. 名称取简体中文，缺失或为空时回退英文；
5. 中文名歧义（多个条目同名）、别名、语言文件缺键这三种情况写进覆盖表；
6. 输出按命名空间分组、组内按 id 升序，紧凑 JSON（无空格无换行），字段顺序 id/group/name/aliases。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GROUPS = ("main", "buildings", "moodles", "other")

# 覆盖表里允许出现哪些键。note 只给人看，其余三个会真正生效；
# 多写一个（比如把 aliases 拼成 alises）会让覆盖静默失效，所以这里直接报错。
ENTRY_FIELDS = frozenset({"id", "name", "aliases", "exclude", "note"})
ADDITION_FIELDS = frozenset({"id", "group", "name", "aliases", "note"})
TOP_FIELDS = frozenset({
    "schemaVersion", "note", "groups", "descriptionMarker", "descriptionModifiers", "entries", "additions",
})


def check_fields(where: str, value, allowed: frozenset[str]) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SystemExit(f"{where} 有无法识别的字段：{', '.join(unknown)}（允许：{', '.join(sorted(allowed))}）")


def check_text(where: str, value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{where} 必须是非空字符串")
    return value


def check_aliases(where: str, value) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(a, str) and a.strip() for a in value):
        raise SystemExit(f"{where} 必须是非空字符串数组")
    return value


def is_description(key: str, keys: set[str], marker: str, modifiers: tuple[str, ...]) -> bool:
    """判断一个键是不是条目的描述文案。

    规则与踩过的坑：
    - 以 marker 结尾 → 描述（bandagedsc）；
    - marker 后面跟数字（fandsc2）或修饰词（dscfixed / dscused / dscdead / dscdropped / dscalt）→ 描述，
      但要求前缀本身是个条目键，否则会误伤 endsc1..13、woodscraps、lcdscreen、endscreen* 这类名字；
    - 只是名字里恰好含 dsc 的（woodscraps、lcdscreen、endscreenstatus）保留。
    """
    if key.endswith(marker):
        return True

    match = re.search(rf"{re.escape(marker)}(\d+)$", key)
    if match or any(key.endswith(marker + word) for word in modifiers):
        base = key[: key.rfind(marker)]
        return base in keys
    return False


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean_name(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def build(locale_zh: dict, locale_en: dict, config: dict) -> tuple[dict, list[str]]:
    check_fields("覆盖表顶层", config, TOP_FIELDS)
    groups = tuple(config.get("groups") or GROUPS)
    marker = str(config.get("descriptionMarker") or "dsc")
    modifiers = tuple(config.get("descriptionModifiers") or ())
    overrides: dict = config.get("entries") or {}
    warnings: list[str] = []

    entries: list[dict] = []
    for group in groups:
        zh = locale_zh.get(group) or {}
        en = locale_en.get(group) or {}
        if not isinstance(zh, dict):
            raise SystemExit(f"语言文件里的 {group} 不是对象")
        known = set(zh)
        for key, raw in zh.items():
            if is_description(key, known, marker, modifiers):
                continue
            name = clean_name(raw) or clean_name(en.get(key))
            if name is None:
                warnings.append(f"{group}/{key}: 中英文都没有名称，已跳过")
                continue
            entries.append({"id": key, "group": group, "name": name, "aliases": []})

    for key, patch in overrides.items():
        group, _, entry_id = key.partition("/")
        if not group or not entry_id:
            raise SystemExit(f"覆盖表的键要写成「分组/id」：{key}")
        if not any(e["group"] == group and e["id"] == entry_id for e in entries):
            raise SystemExit(f"覆盖表引用了不存在的条目：{key}")
        check_fields(f"entries[{key}]", patch, ENTRY_FIELDS)
        if "id" in patch:
            check_text(f"entries[{key}].id", patch["id"])
        if "name" in patch:
            check_text(f"entries[{key}].name", patch["name"])
        if "aliases" in patch:
            check_aliases(f"entries[{key}].aliases", patch["aliases"])
        if "exclude" in patch and not isinstance(patch["exclude"], bool):
            raise SystemExit(f"entries[{key}].exclude 必须是 true / false")

    removed = set()
    for index, entry in enumerate(entries):
        patch = overrides.get(f"{entry['group']}/{entry['id']}")
        if not patch:
            continue
        if patch.get("exclude"):
            removed.add(index)
            continue
        if "id" in patch:
            entry["id"] = patch["id"]
        if "name" in patch:
            entry["name"] = patch["name"]
        if "aliases" in patch:
            entry["aliases"] = list(patch["aliases"])
    entries = [e for i, e in enumerate(entries) if i not in removed]

    for index, addition in enumerate(config.get("additions") or []):
        check_fields(f"additions[{index}]", addition, ADDITION_FIELDS)
        check_text(f"additions[{index}].id", addition.get("id"))
        check_text(f"additions[{index}].group", addition.get("group"))
        check_text(f"additions[{index}].name", addition.get("name"))
        check_aliases(f"additions[{index}].aliases", list(addition.get("aliases") or []))
        entries.append(
            {
                "id": addition["id"],
                "group": addition["group"],
                "name": addition["name"],
                "aliases": list(addition.get("aliases") or []),
            }
        )

    order = {group: index for index, group in enumerate(groups)}
    seen: dict[tuple[str, str], str] = {}
    for entry in entries:
        if entry["group"] not in order:
            raise SystemExit(f"条目 {entry['id']} 的分组 {entry['group']} 不在 groups 里")
        key = (entry["group"], entry["id"])
        if key in seen:
            raise SystemExit(f"重命名后出现重复 id：{entry['group']}/{entry['id']}")
        seen[key] = entry["id"]
    entries.sort(key=lambda e: (order[e["group"]], e["id"]))

    return {"schemaVersion": int(config.get("schemaVersion", 1)), "entries": entries}, warnings


def dumps(document: dict) -> str:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def compare(expected: dict, actual: dict) -> list[str]:
    """按 id+group 对齐，列出新增 / 缺失 / 改名 / 别名变化的条目。"""
    def index(doc):
        return {(e["group"], e["id"]): e for e in doc["entries"]}

    left, right = index(expected), index(actual)
    lines: list[str] = []

    # 先把「同一个名字换了 id」认出来，避免报告成一条缺失 + 一条新增
    renamed: set[tuple[str, str]] = set()
    for key in sorted(set(left) - set(right)):
        old = left[key]
        for new_key in sorted(set(right) - set(left)):
            new = right[new_key]
            if new["group"] == old["group"] and new["name"] == old["name"]:
                lines.append(f"~ 改 id {old['group']}/{old['id']} → {new['id']}")
                renamed.add(key)
                renamed.add(new_key)
                break

    for key in sorted(set(left) - set(right) - renamed):
        lines.append(f"- 缺失 {key[0]}/{key[1]}")
    for key in sorted(set(right) - set(left) - renamed):
        lines.append(f"+ 新增 {key[0]}/{key[1]}")
    for key in sorted(set(left) & set(right)):
        a, b = left[key], right[key]
        if a["name"] != b["name"]:
            lines.append(f"~ 改名 {key[0]}/{key[1]}: {a['name']} → {b['name']}")
        if a["aliases"] != b["aliases"]:
            lines.append(f"~ 别名 {key[0]}/{key[1]}: {a['aliases']} → {b['aliases']}")
    if [e["id"] for e in left.values()] and list(left) != list(right):
        lines.append("~ 条目顺序与原文件不同")
    return lines


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale-dir", type=Path, default=root / "data" / "locale")
    parser.add_argument("--overrides", type=Path, default=root / "data" / "overrides.json")
    parser.add_argument("--out", type=Path, default=root / "out" / "IDLookup.json")
    parser.add_argument("--check", type=Path, default=root / "data" / "snapshot" / "IDLookup.json",
                        help="与这份旧版本逐条对比（默认取仓库里的线上快照）")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    locale_zh = read_json(args.locale_dir / "zh-CN.json")
    locale_en = read_json(args.locale_dir / "EN.json")
    config = read_json(args.overrides)

    document, warnings = build(locale_zh, locale_en, config)
    text = dumps(document)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")

    counts = {}
    for entry in document["entries"]:
        counts[entry["group"]] = counts.get(entry["group"], 0) + 1
    if not args.quiet:
        print(f"生成 {args.out}：{len(document['entries'])} 条 / {len(text.encode('utf-8'))} 字节")
        print("  " + "  ".join(f"{g}:{counts.get(g, 0)}" for g in (config.get("groups") or GROUPS)))

    for warning in warnings:
        print(f"  ! {warning}", file=sys.stderr)

    if args.check and args.check.exists():
        previous = read_json(args.check)
        if dumps(previous) == text:
            if not args.quiet:
                print(f"与 {args.check.name} 完全一致。")
            return 0
        lines = compare(previous, document)
        print(f"与 {args.check} 不一致（{len(lines)} 处）：", file=sys.stderr)
        for line in lines[:40]:
            print("  " + line, file=sys.stderr)
        if len(lines) > 40:
            print(f"  ... 还有 {len(lines) - 40} 处", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
