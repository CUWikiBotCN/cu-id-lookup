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

    def test_unknown_field_is_rejected(self):
        """把 aliases 拼成 alises 之类的错误必须报错，而不是静默失效。"""
        with self.assertRaises(SystemExit):
            gen_idlookup.build(self.zh, self.en, {"entries": {"buildings/fan": {"alises": ["x"]}}})
        with self.assertRaises(SystemExit):
            gen_idlookup.build(self.zh, self.en, {"entrys": {}})
        with self.assertRaises(SystemExit):
            gen_idlookup.build(self.zh, self.en, {"additions": [{"id": "x", "group": "main",
                                                                 "name": "X", "alias": ["x"]}]})

    def test_bad_types_are_rejected(self):
        for patch in ({"name": ""}, {"aliases": "老旧机械"}, {"aliases": [1]}, {"exclude": "yes"}):
            with self.subTest(patch=patch), self.assertRaises(SystemExit):
                gen_idlookup.build(self.zh, self.en, {"entries": {"buildings/fan": patch}})

    def test_note_is_documentation_only(self):
        """note 不参与生成：改 note 不影响输出，也不会进入条目。"""
        base = {"schemaVersion": 1, "entries": {"buildings/fan": {"name": "风扇", "note": "甲"}}}
        other = {"schemaVersion": 1, "entries": {"buildings/fan": {"name": "风扇", "note": "乙"}}}
        left, _ = gen_idlookup.build(self.zh, self.en, base)
        right, _ = gen_idlookup.build(self.zh, self.en, other)
        self.assertEqual(gen_idlookup.dumps(left), gen_idlookup.dumps(right))
        self.assertNotIn("note", gen_idlookup.dumps(left))


class DescriptionTests(unittest.TestCase):
    KEYS = {"fan", "trader", "lcdscreen", "woodscraps", "endscreenstatus", "endsc1"}

    def check(self, key):
        return gen_idlookup.is_description(key, self.KEYS, "dsc", ("alt", "used", "fixed", "dead", "dropped"))

    def test_marker_suffix_is_description(self):
        self.assertTrue(self.check("bandagedsc"))
        self.assertTrue(self.check("lcdscreendsc"))

    def test_numbered_variant_needs_existing_base(self):
        self.assertTrue(self.check("fandsc2"))
        self.assertFalse(self.check("endsc1"))  # "en" 不是条目，是 end screen 的台词

    def test_modifier_variant(self):
        self.assertTrue(self.check("traderdscdead"))

    def test_names_containing_dsc_are_kept(self):
        for key in ("woodscraps", "lcdscreen", "endscreenstatus"):
            self.assertFalse(self.check(key), key)


class SnapshotTests(unittest.TestCase):
    def test_matches_live_snapshot_byte_for_byte(self):
        locale = ROOT / "data" / "locale"
        document, warnings = gen_idlookup.build(
            load(locale / "zh-CN.json"),
            load(locale / "EN.json"),
            load(ROOT / "data" / "overrides.json"),
        )
        expected = load(ROOT / "data" / "expected" / "IDLookup.json")
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
        self.assertEqual(counts, {"main": 302, "buildings": 138, "moodles": 172, "other": 961})

    def test_layer_titles_use_real_ids(self):
        document, _ = gen_idlookup.build(
            load(ROOT / "data" / "locale" / "zh-CN.json"),
            load(ROOT / "data" / "locale" / "EN.json"),
            load(ROOT / "data" / "overrides.json"),
        )
        by_id = {e["id"]: e for e in document["entries"]}
        expected = {
            "gravel_lands": "砾石荒原", "deeper_gravel_lands": "深层砾石带",
            "dried_desert": "干旱沙漠", "wasteland": "辐射废土",
            "overgrown_depths": "深林丛渊", "frozen_chasm": "覆冰断崖",
            "fungal_pools": "真菌洼地", "crystalline_hollow": "晶蚀空穴",
            "geothermal_vents": "地热喷口", "where_we_must_reach": "必须抵达之地",
            "crimson_ascent": "猩红长阶", "earth": "地球",
        }
        for layer_id, name in expected.items():
            self.assertIn(layer_id, by_id, layer_id)
            self.assertEqual(by_id[layer_id]["name"], name)
        self.assertFalse([i for i in by_id if i.lower().startswith("layertitle")])


if __name__ == "__main__":
    unittest.main()
