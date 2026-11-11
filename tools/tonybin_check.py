"""母系のトニービン（母父・母父の父など、母の側の5代以内）と父系統のニックス（2026-10-24, ユーザー「トニービンは母父の場合ニックスが良くなる」）.
5代血統表（sky634-run の ped-data ブランチ data/ped5_full.json）で、トニービンがいる位置（母父／母の側の5代以内／父の側）ごとに、
芝の3着内A/E（人気から見込む数との比）を 2021-23 / 2024 / 2025-26 で出し、父系統・距離・馬場・京都で分ける。
使い方: python3 tools/tonybin_check.py <ped5_full.json> → docs/analysis/tonybin_check.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pf):
    P = json.load(open(pf)); pos = P["pos"]
    tb = {}
    for hid, anc in P["horses"].items():
        ps = [p for p, a in zip(pos, anc) if a == "トニービン"]
        tb[hid] = ("母父" if "DS" in ps else "母の側" if any(p.startswith("D") for p in ps) else "父の側" if ps else "なし")
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0])
    rows = c.execute("select r.horse_id,r.finish,r.popularity,ra.date,ra.course,ra.distance,ra.going,h.sire_line,r.odds from results r join races ra using(race_id) "
                     "join horses h using(horse_id) where ra.surface='芝' and r.finish and r.popularity").fetchall()
    for x in rows:
        b = base[min(x[2], 16)]; b[0] += 1; b[1] += x[1] <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}
    agg = defaultdict(lambda: [[0, 0.0, 0, 0.0] for _ in range(3)])
    KM = {"キングカメハメハ系", "キングマンボ系"}
    for hid, fin, pop, d, co, dist, going, sl, odds in rows:
        if hid not in tb:
            continue
        t = tb[hid]
        line = "父キングマンボ系" if sl in KM else "父ディープ系" if sl == "ディープインパクト系" else f"父{country_type(sl) if sl else '-'}"
        keys = [("全体", t), ("父系統", t, line),
                ("距離", t, "2400m以上" if dist >= 2400 else "2000-2399m" if dist >= 2000 else "2000m未満"),
                ("馬場", t, "良" if (going or "良").startswith("良") else "道悪"),
                ("京都2200m以上", t) if co == "京都" and dist >= 2200 else None,
                ("2200m以上×父系統", t, line) if dist >= 2200 else None,
                ("2200m以上×道悪", t) if dist >= 2200 and not (going or "良").startswith("良") else None]
        for k in keys:
            if k:
                a = agg[k][per(d)]; a[0] += fin <= 3; a[1] += exp[min(pop, 16)]; a[2] += 1; a[3] += (odds or 0) * 100 if fin == 1 else 0
    L = ["# 母系のトニービン（tools/tonybin_check.py）", "",
         f"5代血統表 {len(tb)}頭（トニービンが母父 {sum(v == '母父' for v in tb.values())}頭・母の側の5代以内 {sum(v == '母の側' for v in tb.values())}頭・父の側 {sum(v == '父の側' for v in tb.values())}頭）。芝のみ。",
         "A/E＝3着内の実数÷人気から見込む数。3期＝2021-23 / 2024 / 2025-26。単勝回収は通算。", "",
         "| 切り口 | トニービンの位置 | 条件 | A/E 3期 | A/E 通算 | 単勝回収 | 走数 |", "|---|---|---|---|---|---|---|"]
    order = {"なし": 9, "父の側": 2, "母の側": 1, "母父": 0}
    for k in sorted(agg, key=lambda k: (k[0], k[2] if len(k) > 2 else "", order[k[1]])):
        cs = agg[k]; n = sum(x[2] for x in cs)
        if n < 80:
            continue
        ae = [x[0] / x[1] if x[1] and x[2] >= 20 else None for x in cs]
        tot = sum(x[0] for x in cs) / sum(x[1] for x in cs)
        L.append(f"| {k[0]} | {k[1]} | {k[2] if len(k) > 2 else ''} | " + " / ".join("-" if v is None else f"{v:.2f}" for v in ae)
                 + f" | **{tot:.2f}** | {sum(x[3] for x in cs) / n:.0f}% | {n} |")
    (ROOT / "docs" / "analysis" / "tonybin_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
