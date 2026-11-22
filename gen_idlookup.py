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
import sys
from pathlib import Path

GROUPS = ("main", "buildings", "moodles", "other")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean_name(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def build(locale_zh: dict, locale_en: dict, config: dict) -> tuple[dict, list[str]]:
    groups = tuple(config.get("groups") or GROUPS)
    suffixes = tuple(config.get("excludeSuffixes") or ("dsc",))
    overrides: dict = config.get("entries") or {}
    warnings: list[str] = []

    entries: list[dict] = []
    for group in groups:
        zh = locale_zh.get(group) or {}
        en = locale_en.get(group) or {}
        if not isinstance(zh, dict):
            raise SystemExit(f"语言文件里的 {group} 不是对象")
        for key, raw in zh.items():
            if key.endswith(suffixes):
                continue
            name = clean_name(raw) or clean_name(en.get(key))
            if name is None:
                warnings.append(f"{group}/{key}: 中英文都没有名称，已跳过")
                continue
            entries.append({"id": key, "group": group, "name": name, "aliases": []})

    for key in overrides:
        group, _, entry_id = key.partition("/")
        if not any(e["group"] == group and e["id"] == entry_id for e in entries):
            raise SystemExit(f"覆盖表引用了不存在的条目：{key}")

    removed = set()
    for index, entry in enumerate(entries):
        patch = overrides.get(f"{entry['group']}/{entry['id']}")
        if not patch:
            continue
        if patch.get("exclude"):
            removed.add(index)
            continue
        if "name" in patch:
            entry["name"] = patch["name"]
        if "aliases" in patch:
            entry["aliases"] = list(patch["aliases"])
    entries = [e for i, e in enumerate(entries) if i not in removed]

    for addition in config.get("additions") or []:
        if not addition.get("id") or not addition.get("name"):
            raise SystemExit("additions 里每一项都要有 id 和 name")
        entries.append(
            {
                "id": addition["id"],
                "group": addition["group"],
                "name": addition["name"],
                "aliases": list(addition.get("aliases") or []),
            }
        )

    order = {group: index for index, group in enumerate(groups)}
    for entry in entries:
        if entry["group"] not in order:
            raise SystemExit(f"条目 {entry['id']} 的分组 {entry['group']} 不在 groups 里")
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
    for key in sorted(set(left) - set(right)):
        lines.append(f"- 缺失 {key[0]}/{key[1]}")
    for key in sorted(set(right) - set(left)):
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
