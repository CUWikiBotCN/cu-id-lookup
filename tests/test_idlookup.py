"""生成器自测：规则覆盖 + 与线上快照逐字节一致。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gen_idlookup  # noqa: E402


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class RuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zh = {
            "main": {"bandage": "绷带", "bandagedsc": "描述", "empty": "", "big": "大件"},
            "buildings": {"fan": "老旧机械", "crystalbig": "水晶"},
            "moodles": {"pain": "疼痛"},
            "other": {"Head": "头"},
        }
        self.en = {"main": {"empty": "Empty"}, "buildings": {}, "moodles": {}, "other": {}}

    def test_skips_description_keys_and_falls_back_to_english(self):
        document, warnings = gen_idlookup.build(self.zh, self.en, {"schemaVersion": 1})
        ids = [entry["id"] for entry in document["entries"]]
        self.assertNotIn("bandagedsc", ids)
        self.assertEqual(ids[:2], ["bandage", "big"])  # main 组内按 id 升序
        empty = next(e for e in document["entries"] if e["id"] == "empty")
        self.assertEqual(empty["name"], "Empty")
        self.assertEqual(warnings, [])

    def test_group_order_and_sorting(self):
        document, _ = gen_idlookup.build(self.zh, self.en, {"schemaVersion": 1})
        self.assertEqual([e["group"] for e in document["entries"]],
                         ["main", "main", "main", "buildings", "buildings", "moodles", "other"])

    def test_overrides_and_additions(self):
        config = {
            "schemaVersion": 1,
            "entries": {"buildings/fan": {"name": "风扇", "aliases": ["老旧机械"]}},
            "additions": [{"id": "bloodsuckerden", "group": "buildings", "name": "吸血巢",
                           "aliases": ["bloodsuckerden"]}],
        }
        document, _ = gen_idlookup.build(self.zh, self.en, config)
        by_key = {(e["group"], e["id"]): e for e in document["entries"]}
        self.assertEqual(by_key[("buildings", "fan")]["name"], "风扇")
        self.assertEqual(by_key[("buildings", "fan")]["aliases"], ["老旧机械"])
        self.assertEqual(by_key[("buildings", "bloodsuckerden")]["name"], "吸血巢")
        order = [e["id"] for e in document["entries"] if e["group"] == "buildings"]
        self.assertEqual(order, ["bloodsuckerden", "crystalbig", "fan"])

    def test_unknown_override_is_rejected(self):
        with self.assertRaises(SystemExit):
            gen_idlookup.build(self.zh, self.en, {"entries": {"main/nope": {"name": "x"}}})


class SnapshotTests(unittest.TestCase):
    def test_matches_live_snapshot_byte_for_byte(self):
        locale = ROOT / "data" / "locale"
        document, warnings = gen_idlookup.build(
            load(locale / "zh-CN.json"),
            load(locale / "EN.json"),
            load(ROOT / "data" / "overrides.json"),
        )
        expected = load(ROOT / "data" / "snapshot" / "IDLookup.json")
        self.assertEqual(gen_idlookup.dumps(document), gen_idlookup.dumps(expected))
        self.assertEqual(warnings, [])

    def test_group_counts(self):
        document, _ = gen_idlookup.build(
            load(ROOT / "data" / "locale" / "zh-CN.json"),
            load(ROOT / "data" / "locale" / "EN.json"),
            load(ROOT / "data" / "overrides.json"),
        )
        counts = {}
        for entry in document["entries"]:
            counts[entry["group"]] = counts.get(entry["group"], 0) + 1
        self.assertEqual(counts, {"main": 302, "buildings": 146, "moodles": 173, "other": 962})


if __name__ == "__main__":
    unittest.main()
