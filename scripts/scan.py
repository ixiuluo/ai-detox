#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai-detox 特征扫描器（Phase 1 确定性扫描）
基于 data/ai-patterns.json 特征词库，扫描文本中的 AI 写作特征。

用法:
  python3 scan.py <文件.txt>                    # 扫描文本文件（UTF-8）
  python3 scan.py --text "待扫描文本"           # 扫描命令行文本
  python3 scan.py <文件> --dict 词库.json        # 自定义词库
  python3 scan.py <文件> --min-severity medium  # 只看中危以上（high/medium/low/info）
  python3 scan.py <文件> --json                 # 输出 JSON 报告（机器可读）

说明:
  - Phase 1 只做确定性匹配（词库命中），"盲审"（上下文判断、逻辑、结构）由
    Claude 依据 SKILL.md 的七层框架完成。
  - 同一位置多个模式命中时自动去重（保留更具体/更严重的）。
"""
import json
import os
import re
import sys
import statistics

DICT_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "ai-patterns.json")
SEV_ORDER = {"high": 3, "medium": 2, "low": 1, "info": 0}
SEV_LABEL = {"high": "高危🔴", "medium": "中危🟡", "low": "低危", "info": "参考"}
FLAG_MAP = {"MULTILINE": re.MULTILINE, "DOTALL": re.DOTALL, "IGNORECASE": re.IGNORECASE}

# 统计层：常见空洞连接词与借喻场（借鉴"识别动作而非字面"的思想，代码原创）
CONJUNCTIONS = ("因为", "所以", "但是", "然而", "同时", "此外", "而且", "并且", "因此", "不仅", "一方面", "另一方面")
METAPHOR_FIELDS = {
    "温度": ("降温", "升温", "冷却", "余温", "滚烫", "微凉"),
    "生死战争": ("杀死", "死因", "战场", "开火", "引爆", "硝烟"),
    "建筑灾害": ("坍塌", "崩塌", "地基", "砖头", "支柱", "废墟"),
    "仓储租赁": ("仓库", "库房", "租金", "取货", "入库", "库存"),
    "道路竞赛": ("赛道", "跑道", "岔路", "十字路口", "终点线", "门槛"),
    "机器器官": ("齿轮", "引擎", "发动机", "血管", "骨架", "肌肉"),
    "海洋航行": ("蓝海", "浪潮", "潮水", "航船", "灯塔", "彼岸"),
}


def parse_args(argv):
    text = None
    fpath = None
    dict_path = DICT_DEFAULT
    min_sev = "info"
    as_json = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--text":
            i += 1
            text = argv[i]
        elif a == "--dict":
            i += 1
            dict_path = argv[i]
        elif a == "--min-severity":
            i += 1
            min_sev = argv[i].lower()
        elif a == "--json":
            as_json = True
        elif a.startswith("-"):
            pass
        else:
            fpath = a
        i += 1
    if text is None and fpath:
        with open(fpath, encoding="utf-8") as f:
            text = f.read()
    if text is None:
        print("用法: scan.py <文件> 或 scan.py --text \"文本\"", file=sys.stderr)
        sys.exit(1)
    if min_sev not in SEV_ORDER:
        print(f"未知严重等级: {min_sev}（可选 high/medium/low/info）", file=sys.stderr)
        sys.exit(1)
    return text, dict_path, min_sev, as_json


def load_dict(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compile_pattern(p):
    if p["type"] != "regex":
        return None
    fl = 0
    for f in p.get("flags", "").split(","):
        fl |= FLAG_MAP.get(f.strip(), 0)
    try:
        return re.compile(p["pattern"], fl)
    except re.error:
        return None


def scan(text, patterns):
    compiled = []
    for p in patterns:
        if not p.get("enabled", True):
            continue
        compiled.append((p, compile_pattern(p) if p["type"] == "regex" else None))

    raw = []
    for p, rx in compiled:
        if rx is not None:
            for m in rx.finditer(text):
                raw.append(_hit(p, m.group(0), m.start(), m.end(), text))
        else:
            start = 0
            pat = p["pattern"]
            while True:
                idx = text.find(pat, start)
                if idx < 0:
                    break
                raw.append(_hit(p, pat, idx, idx + len(pat), text))
                start = idx + len(pat)

    # 去重：同一位置多个命中，保留更严重/更长的
    raw.sort(key=lambda h: (h["start"], h["end"] - h["start"]))
    kept = []
    for h in raw:
        # 若被已保留的命中完全覆盖，跳过
        if kept and h["start"] >= kept[-1]["start"] and h["end"] <= kept[-1]["end"]:
            # 但若新命中更严重，替换
            if SEV_ORDER[h["severity"]] > SEV_ORDER[kept[-1]["severity"]]:
                kept[-1] = h
            continue
        kept.append(h)
    return kept


def _hit(p, matched, s, e, text):
    return {
        "id": p["id"],
        "layer": p["layer"],
        "category": p.get("category", ""),
        "severity": p["severity"],
        "matched": matched,
        "start": s,
        "end": e,
        "suggestion": p.get("suggestion", ""),
        "context": text[max(0, s - 15): e + 15].replace("\n", " "),
    }


def han_count(text):
    """统计汉字数（忽略标点、数字与字母）。"""
    return len(re.findall(r"[一-鿿]", text))


def sentence_stats(text):
    """句长统计：均值/标准差/变异系数。模型句长彼此接近，人写长短差距大。"""
    sents = [s for s in re.split(r"[。！？；\n]", text) if han_count(s.strip()) >= 2]
    result = {"sentence_count": len(sents), "mean": None, "std": None, "cv": None, "uniform": False, "note": ""}
    if len(sents) < 3:
        result["note"] = "句子数不足，跳过句长分析"
        return result
    lens = [han_count(s) for s in sents]
    mean = statistics.mean(lens)
    std = statistics.pstdev(lens)
    cv = std / mean if mean else 0
    result["mean"] = round(mean, 1)
    result["std"] = round(std, 1)
    result["cv"] = round(cv, 2)
    notes = []
    if std < 8:
        notes.append("⚠ 句长标准差<8，句式可能过于均匀")
        result["uniform"] = True
    if len(sents) >= 12 and cv < 0.4:
        notes.append("⚠ 句长变异系数<0.4，长短句缺乏变化")
    result["note"] = "；".join(notes)
    return result


def para_stats(text):
    """段落统计：长度变异系数与短段连击。"""
    paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 10]
    result = {"para_count": len(paras), "cv": None, "short_streak": 0, "note": ""}
    if len(paras) < 2:
        return result
    lens = [len(p) for p in paras]
    mean = statistics.mean(lens)
    std = statistics.pstdev(lens)
    cv = std / mean if mean else 0
    result["cv"] = round(cv, 2)
    notes = []
    if cv < 0.25:
        notes.append("⚠ 段落长度变异系数<0.25，段落可能过于均匀")
    streak = max_streak = 0
    for p in paras:
        if han_count(p) <= 24 and len(re.findall(r"[。！？]", p)) <= 1:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    result["short_streak"] = max_streak
    if max_streak >= 4:
        notes.append(f"⚠ 连续{max_streak}段短句，节奏像固定鼓点")
    result["note"] = "；".join(notes)
    return result


def conjunction_density(text):
    """连词密度：空洞连接词占句子的比例，偏高说明句间靠连接词硬转。"""
    sents = [s for s in re.findall(r"[^。！？；\n]+[。！？；]?", text) if han_count(s) >= 2]
    total = len(sents)
    count = sum(text.count(c) for c in CONJUNCTIONS)
    density = round(count / total, 2) if total else 0
    note = ""
    if total and density > 0.8:
        note = f"⚠ 连词密度{density}偏高，句间多靠连接词硬转，缺逻辑承接"
    return {"count": count, "sentence_count": total, "density": density, "note": note}


def heavy_de_sentences(text):
    """'的'字长句：汉字≥38 且含≥4 个'的'，主干被定语压到后面。"""
    matches = []
    for m in re.finditer(r"[^。！？\n]+[。！？]?", text):
        value = m.group()
        if han_count(value) >= 38 and value.count("的") >= 4:
            matches.append(value.strip())
    return {"count": len(matches), "examples": matches[:3]}


def anaphora_runs(text):
    """同字排比：一句内 3+ 小句用同一两字开头，模板化排比。"""
    runs = []
    for m in re.finditer(r"[^。！？\n]+[。！？]?", text):
        sentence = m.group()
        clauses = [c.strip() for c in re.split(r"[，、；,;]", sentence) if han_count(c.strip()) >= 3]
        if len(clauses) < 3:
            continue
        streak = 1
        for prev, cur in zip(clauses, clauses[1:]):
            if prev[:2] == cur[:2] and re.match(r"[一-鿿]{2}", cur):
                streak += 1
                if streak >= 3:
                    runs.append(sentence.strip())
                    break
            else:
                streak = 1
    return {"count": len(runs), "examples": runs[:3]}


def bracket_highlights(text):
    """「」金句密度：短括号短语过密说明在批量造金句。"""
    matches = list(re.finditer(r"[「『][^」』\n]{1,6}[」』]", text))
    han = han_count(text)
    density = round(len(matches) / max(1, han) * 1000, 2)
    note = ""
    if len(matches) >= 3 and density > 5:
        note = f"⚠ 「」金句密度{density}‰，可能批量造金句"
    return {"count": len(matches), "density": density, "note": note}


def metaphor_clusters(text):
    """借喻簇：800 字内出现≥3 套借喻场，抽象内容靠比喻包装。"""
    hits = []
    for field, words in METAPHOR_FIELDS.items():
        for w in words:
            for m in re.finditer(re.escape(w), text):
                hits.append((m.start(), field, w))
    hits.sort()
    for i, (start, _, _) in enumerate(hits):
        window = [h for h in hits[i:] if h[0] - start <= 800]
        fields = {h[1] for h in window}
        if len(fields) >= 3:
            ctx = text[max(0, start - 30): start + 30].replace("\n", " ")
            return {"found": True, "fields": sorted(fields), "context": ctx}
    return {"found": False, "fields": [], "context": ""}


def build_report(text, hits, dict_meta, min_sev):
    total = len(text)
    per500 = max(1, total / 500.0)
    layers = dict_meta.get("layers", {})
    by_layer = {}
    for h in hits:
        if SEV_ORDER[h["severity"]] < SEV_ORDER[min_sev]:
            continue
        by_layer.setdefault(h["layer"], []).append(h)

    report = {
        "summary": {
            "total_chars": total,
            "flagged_hits": sum(len(v) for v in by_layer.values()),
            "by_severity": {"high": 0, "medium": 0, "low": 0, "info": 0},
            "layers_flagged": [],
        },
        "layers": {},
        "structure": {
            "sentence": sentence_stats(text),
            "paragraph": para_stats(text),
            "conjunction": conjunction_density(text),
            "de_heavy": heavy_de_sentences(text),
            "anaphora": anaphora_runs(text),
            "brackets": bracket_highlights(text),
            "metaphors": metaphor_clusters(text),
        },
    }
    for layer, layer_name in layers.items():
        hits_l = by_layer.get(layer, [])
        sev_cnt = {"high": 0, "medium": 0, "low": 0, "info": 0}
        for h in hits_l:
            sev_cnt[h["severity"]] += 1
            report["summary"]["by_severity"][h["severity"]] += 1
        density = round(len(hits_l) / per500, 2)
        flagged = density >= 3 or sev_cnt["high"] >= 2
        if flagged:
            report["summary"]["layers_flagged"].append(layer)
        report["layers"][layer] = {
            "name": layer_name,
            "hits": len(hits_l),
            "per_500": density,
            "by_severity": sev_cnt,
            "flagged": flagged,
            "findings": [
                {
                    "id": h["id"],
                    "severity": h["severity"],
                    "matched": h["matched"],
                    "category": h["category"],
                    "context": h["context"],
                    "suggestion": h["suggestion"],
                }
                for h in hits_l
            ],
        }
    return report


def print_report(report, layers_meta):
    s = report["summary"]
    print("=" * 60)
    print(f"ai-detox 特征扫描报告（Phase 1 确定性扫描）")
    print(f"总字符数: {s['total_chars']}   命中总数: {s['flagged_hits']}")
    print(f"高危:{s['by_severity']['high']} 中危:{s['by_severity']['medium']} 低危:{s['by_severity']['low']} 参考:{s['by_severity']['info']}")
    print("=" * 60)
    for layer, layer_name in layers_meta.items():
        if layer not in report["layers"]:
            continue
        r = report["layers"][layer]
        if r["hits"] == 0:
            continue
        mark = "⚠" if r["flagged"] else "  "
        print(f"\n{mark} {layer} {r['name']}  ({r['hits']}命中, {r['per_500']}/500字)")
        for f in r["findings"]:
            print(f"    [{SEV_LABEL.get(f['severity'], f['severity'])}] {f['matched']}  ← …{f['context']}…")
            print(f"        建议: {f['suggestion']}")
    print("\n" + "=" * 60)
    print("结构统计（参考，供 Phase 2 盲审使用）")
    st = report["structure"]["sentence"]
    print(f"  句长: 共{st['sentence_count']}句, 均值{st['mean']}字, 标准差{st['std']}, 变异系数{st['cv']}  {st['note']}")
    pt = report["structure"]["paragraph"]
    if pt["cv"] is not None:
        print(f"  段落: 共{pt['para_count']}段, 长度变异系数{pt['cv']}, 短段连击{pt['short_streak']}  {pt['note']}")
    cj = report["structure"]["conjunction"]
    if cj["count"]:
        print(f"  连词: {cj['count']}处/{cj['sentence_count']}句, 密度{cj['density']}  {cj['note']}")
    dh = report["structure"]["de_heavy"]
    if dh["count"]:
        print(f"  '的'字长句: {dh['count']}句, 例: {' / '.join(e[:24] for e in dh['examples'])}")
    an = report["structure"]["anaphora"]
    if an["count"]:
        print(f"  同字排比: {an['count']}句, 例: {' / '.join(e[:24] for e in an['examples'])}")
    bk = report["structure"]["brackets"]
    if bk["count"]:
        print(f"  「」金句: {bk['count']}处, 密度{bk['density']}‰  {bk['note']}")
    mp = report["structure"]["metaphors"]
    if mp["found"]:
        print(f"  借喻簇: 800字内{len(mp['fields'])}套借喻场({'/'.join(mp['fields'])}) …{mp['context']}")
    print("=" * 60)
    if s["layers_flagged"]:
        print(f"⚠ 需改写: 层级 {', '.join(s['layers_flagged'])}（命中/500字≥3 或 高危≥2）")
        print("  请按 SKILL.md 的 S1-S6 策略改写，改写后重新扫描对比。")
    else:
        print("✓ 各层特征密度均低于阈值。如仍需降级，请以人工盲审(Phase 2)为准。")


def main():
    text, dict_path, min_sev, as_json = parse_args(sys.argv[1:])
    data = load_dict(dict_path)
    hits = scan(text, data["patterns"])
    report = build_report(text, hits, data["meta"], min_sev)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, data["meta"]["layers"])


if __name__ == "__main__":
    main()
