"""ダートの道悪（重・不良）で何が浮くか（2026-10-24, ユーザー指摘「京都ダート不良・東京も雨。血統傾向出るよね」）.

ダートのレースを馬場（良 / 稍重 / 重・不良）で分け、父系統・父の型（日本/米国/欧州）・母父の型・種牡馬・
前走の位置取り・前走芝・馬体重・枠について、3着内A/E（人気から見込む3着内数との比）を
2021-23 / 2024 / 2025-26 で出す。3期とも同じ向きで、良との差もあるものだけを「傾向」とする。
使い方: python3 tools/wet_dirt.py [--course 京都] → docs/analysis/wet_dirt.md
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def gclass(g):
    g = g or "良"
    return "良" if g.startswith("良") else "稍重" if g.startswith("稍") else "重不良"


def first_pos(passing):
    try:
        return int(str(passing).split("-")[0])
    except (ValueError, AttributeError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--course")
    ap.add_argument("--min", type=int, default=60)
    a = ap.parse_args()
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {r[0]: r[1:] for r in c.execute("select race_id,date,course,surface,distance,going,n_runners from races")}
    hist = defaultdict(list)  # horse → [(date, surface, first corner pos, n)]
    rows = []
    for rid, hid, fin, pop, gate, num, pas, bw, sire, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.gate,r.number,r.passing,r.body_weight,h.sire,h.sire_line,h.damsire_line "
            "from results r join horses h using(horse_id) where r.finish is not null"):
        if rid not in races:
            continue
        d, co, su, dist, going, n = races[rid]
        hist[hid].append((d, su, first_pos(pas), n or 0))
        if su == "ダ" and pop:
            rows.append(dict(rid=rid, hid=hid, d=d, co=co, dist=dist or 0, g=gclass(going), fin=fin, pop=min(pop, 14),
                             gate=gate, bw=bw, sire=sire, sl=sl, ct=country_type(sl) if sl else None,
                             dct=country_type(dsl) if dsl else None))
    for v in hist.values():
        v.sort()
    base = defaultdict(lambda: [0, 0])
    for r in rows:
        b = base[r["pop"]]; b[0] += 1; b[1] += r["fin"] <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}

    def prev(r):
        h = [x for x in hist[r["hid"]] if x[0] < r["d"]]
        return h[-1] if h else None

    feats = []
    for r in rows:
        if a.course and r["co"] != a.course:
            continue
        f = [f"父系統={r['sl']}", f"父の型={r['ct']}", f"母父の型={r['dct']}", f"父={r['sire']}"]
        p = prev(r)
        if p:
            pos = p[2]
            if pos is not None and p[3]:
                f.append("前走の1角=" + ("前(3番手以内)" if pos <= 3 else "中団" if pos <= p[3] * 0.6 else "後方"))
            if p[1] == "芝":
                f.append("前走=芝")
        if r["bw"]:
            f.append("馬体重=" + ("〜459" if r["bw"] < 460 else "460〜499" if r["bw"] < 500 else "500〜"))
        if r["gate"]:
            f.append("枠=" + ("内(1-3)" if r["gate"] <= 3 else "中(4-6)" if r["gate"] <= 6 else "外(7-8)"))
        f.append("人気=" + ("1-3" if r["pop"] <= 3 else "4-6" if r["pop"] <= 6 else "7-9" if r["pop"] <= 9 else "10-"))
        feats.append((r, f))
    agg = defaultdict(lambda: defaultdict(lambda: [[0, 0.0, 0] for _ in range(3)]))
    for r, fs in feats:
        for f in fs:
            x = agg[f][r["g"]][per(r["d"])]
            x[0] += r["fin"] <= 3; x[1] += exp[r["pop"]]; x[2] += 1

    def ae(cell):
        return cell[0] / cell[1] if cell[1] else None

    out = [f"# ダート道悪の傾向（{a.course or '全場'}・第7R以降）", "",
           "3着内A/E（実際の3着内数÷人気から見込む数）。左から 2021-23 / 2024 / 2025-26、()内は頭数。",
           "「道悪で浮く」= 重・不良で3期とも1.05以上かつ良より0.08以上高い。「道悪で沈む」= 3期とも0.95以下かつ良より0.08以上低い。", ""]
    up, down, table = [], [], []
    for f, gs in agg.items():
        w = gs.get("重不良")
        if not w or min(x[2] for x in w) < a.min // 3 or sum(x[2] for x in w) < a.min:
            continue
        wa = [ae(x) for x in w]
        g = gs.get("良")
        ga = ae([sum(x[0] for x in g), sum(x[1] for x in g), 0]) if g else None
        wall = ae([sum(x[0] for x in w), sum(x[1] for x in w), 0])
        line = (f, wa, [x[2] for x in w], ga, wall)
        table.append(line)
        if ga and all(v and v >= 1.05 for v in wa) and wall - ga >= 0.08:
            up.append(line)
        if ga and all(v is not None and v <= 0.95 for v in wa) and ga - wall >= 0.08:
            down.append(line)

    def fmt(line):
        f, wa, ns, ga, wall = line
        return (f"| {f} | " + " / ".join(f"{v:.2f}" for v in wa) + f" ({'/'.join(map(str, ns))}) | {wall:.2f} | "
                + (f"{ga:.2f}" if ga else "-") + " |")
    hdr = ["| 条件 | 重・不良 A/E 3期 | 重・不良 通算 | 良 通算 |", "|---|---|---|---|"]
    out += ["## 道悪で浮く（3期とも）", ""] + hdr + [fmt(x) for x in sorted(up, key=lambda x: -x[4])] + [""]
    out += ["## 道悪で沈む（3期とも）", ""] + hdr + [fmt(x) for x in sorted(down, key=lambda x: x[4])] + [""]
    out += ["## 全条件（頭数の多い順）", ""] + hdr + [fmt(x) for x in sorted(table, key=lambda x: -sum(x[2]))]
    name = "wet_dirt" + (f"_{a.course}" if a.course else "")
    (ROOT / "docs" / "analysis" / f"{name}.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:4 + len(up) + len(down) + 12]))


if __name__ == "__main__":
    main()
