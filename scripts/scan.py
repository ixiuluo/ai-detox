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


def sentence_stats(text):
    sents = [s.strip() for s in re.split(r"[。！？；]", text) if len(s.strip()) >= 2]
    if len(sents) < 3:
        return {"sentence_count": len(sents), "std": None, "mean": None, "note": "句子数不足，跳过句长分析"}
    lens = [len(s) for s in sents]
    std = statistics.pstdev(lens)
    mean = statistics.mean(lens)
    note = ""
    if std < 8:
        note = "⚠ 句长标准差<8，句式可能过于均匀"
    return {"sentence_count": len(sents), "std": round(std, 1), "mean": round(mean, 1), "note": note}


def para_stats(text):
    paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 10]
    if len(paras) < 2:
        return {"para_count": len(paras), "cv": None, "note": ""}
    lens = [len(p) for p in paras]
    mean = statistics.mean(lens)
    std = statistics.pstdev(lens)
    cv = std / mean if mean else 0
    note = ""
    if cv < 0.25:
        note = "⚠ 段落长度变异系数<0.25，段落可能过于均匀"
    return {"para_count": len(paras), "cv": round(cv, 2), "note": note}


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
        "structure": {"sentence": sentence_stats(text), "paragraph": para_stats(text)},
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
    print(f"  句长: 共{st['sentence_count']}句, 均值{st['mean']}字, 标准差{st['std']}  {st['note']}")
    pt = report["structure"]["paragraph"]
    if pt["cv"] is not None:
        print(f"  段落: 共{pt['para_count']}段, 长度变异系数{pt['cv']}  {pt['note']}")
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
