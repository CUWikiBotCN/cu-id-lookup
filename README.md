# cu-id-lookup

生成《未知伤亡》中文维基的 `Data:Editor/IDLookup.json`——wiki 编辑器用的 ID → 名称对照表。

输入是两份语言文件加一份人工维护的覆盖表，输出与线上现行格式逐字节一致（1583 条）。

```
data/locale/zh-CN.json ─┐
data/locale/EN.json ────┼─► gen_idlookup.py ─► out/IDLookup.json ─► Data:Editor/IDLookup.json
data/overrides.json ────┘
```

## 为什么单独一个仓库

这份页面原先由 bot 直接改（`Hao-Ming-Bot` 的「适配正式版 1.0」「适配 1.0.1」），
`dodo_wiki_updater_gui` 的验收记录里也写明它「不属于现有生产发布目标」「更新来源待核对」。
与其继续手工维护，不如把规则写死：语言文件自动跟随，只把真正的差异留在覆盖表里。

## 规则

1. 只取 `main`、`buildings`、`moodles`、`other` 四个命名空间（`character`/`notes`/`pdaNotes`/`pauseQuotes` 不进入）；
2. 跳过以 `dsc` 结尾的键——那是对应条目的描述文案，不是条目本身；
3. 条目形如 `{"id": 键名, "group": 命名空间, "name": 中文名, "aliases": []}`，id 保留原键的大小写；
4. 名称取简体中文，缺失或为空时回退英文；
5. 输出按命名空间分组（main → buildings → moodles → other），组内按 id 升序，紧凑 JSON、无换行；
6. 只有三种情况写进覆盖表：中文名歧义、别名、语言文件缺键。

## 用法

```bash
python3 gen_idlookup.py                 # 生成 out/IDLookup.json，并与 data/snapshot 对比
python3 gen_idlookup.py --check path    # 与指定旧版本对比
python3 -m unittest discover -s tests -q
```

`--check` 发现条目增删、改名、别名变化或顺序变化时以非零码退出，并列出差异；没有变化时打印「完全一致」。

当前输出：`main:302 buildings:146 moodles:173 other:962`，共 1583 条、148 595 字节，与线上 rev 16858 逐字节相同。

## 覆盖表

`data/overrides.json` 只写与语言文件不一致的部分：

```json
{
  "schemaVersion": 1,
  "groups": ["main", "buildings", "moodles", "other"],
  "excludeSuffixes": ["dsc"],
  "entries": {
    "buildings/fan": {
      "name": "风扇",
      "aliases": ["老旧机械"],
      "note": "语言文件里叫「老旧机械」，与弹跳板、活塞、尖刺陷阱同名，这里用具体名字"
    }
  },
  "additions": [
    {
      "id": "bloodsuckerden",
      "group": "buildings",
      "name": "吸血巢",
      "aliases": ["bloodsuckerden"],
      "note": "语言文件缺这个键，游戏内以预制体名出现"
    }
  ]
}
```

- `entries` 的键是 `分组/id`，指向的条目必须存在，否则直接报错（防止改了 id 之后覆盖静默失效）；
- 可选字段：`name`、`aliases`、`exclude`（置 `true` 表示从输出里剔除）；
- `additions` 用于语言文件里没有、但编辑器需要识别的条目；
- `note` 是给人看的，写清为什么改：生成器不读它，也不会进入输出 JSON；改 note 不影响结果。
- 字段名写错（比如把 `aliases` 拼成 `alises`）会直接报错，避免覆盖静默失效；`entries` / `additions` 的其它未知字段同样报错。

现有的 21 条覆盖都是「语言文件名太笼统」造成的：`beartrap`/`fan`/`jumppad`/`piston`/`spikestabber` 在语言文件里都叫「老旧机械」，
`crystal*` 六个都叫「水晶」，`corpse` 叫「？？？」。编辑器需要能区分它们。

## 更新流程

1. 拉取最新的 `Data:Localization/zh-CN.json` 与 `EN.json` 到 `data/locale/`（用 `cwb sync` 或 `wiki-batch-grab` 都行）；
2. `python3 gen_idlookup.py`，看 `--check` 报出的增删与改名；
3. 新键会自动出现在输出里，只需处理歧义与别名；
4. 确认无误后，把 `out/IDLookup.json` 覆盖到页面 `Data:Editor/IDLookup.json`（Data 页是纯 JSON，不带 `[PAGE_INFO]` 头），
   同时把新版本另存为 `data/snapshot/IDLookup.json` 作为下次对比的基线。

## 目录

```
data/locale/zh-CN.json     语言文件快照（社区翻译）
data/locale/EN.json        语言文件快照（英文）
data/overrides.json        人工覆盖表
data/snapshot/IDLookup.json 线上基线，用于 --check 与回归测试
out/IDLookup.json          生成的页面正文
gen_idlookup.py            生成器
tests/test_idlookup.py     规则测试 + 快照逐字节一致测试
```
