"""父の血統をどの細かさでまとめると、条件ごとの走りを一番よく当てられるか（2026-10-11）.

細かさ: 種牡馬 / 系統（sire_lines.json の約50系統）/ 親系統（その一つ上: サンデー系・ミスプロ系・ロベルト系…）/ 国別タイプ（日本/米国/欧州型）、
と、種牡馬→系統→親系統の順に頭数が少ないほど上の成績に寄せる「階層まとめ」。
条件セル: 競馬場×芝ダ×距離帯 と 芝ダ×距離帯×馬場（良/道悪）。
発見（2021〜2023）で各まとめの3着内A/E（人気からの期待比）を出し、テスト（2024〜2026）の3着内を
「人気から見込む率 × A/E」で予測したときの対数損失を比べる（小さいほど良い。人気だけ＝基準）。

使い方: python3 tools/line_granularity.py → docs/analysis/line_granularity.md
"""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

DB = ROOT / "data" / "keiba.db"
OUT = ROOT / "docs" / "analysis" / "line_granularity.md"
WIKI = json.loads((ROOT / "data" / "knowledge" / "wiki_sire_lines.json").read_text(encoding="utf-8"))["horse_line"]
LINES = json.loads((ROOT / "data" / "knowledge" / "sire_lines.json").read_text(encoding="utf-8"))["lines"]


def band(d):
    return "短" if d <= 1400 else "マ" if d <= 1800 else "中" if d <= 2200 else "長"


def main():
    c = sqlite3.connect(DB)
    rows = []
    base = defaultdict(lambda: [0, 0])
    for date, co, su, dist, going, fin, pop, sire, sl, dsire, dsl in c.execute(
            """select ra.date,ra.course,ra.surface,ra.distance,ra.going,r.finish,r.popularity,h.sire,h.sire_line,h.damsire,h.damsire_line
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null and h.sire is not null"""):
        p = min(pop, 14)
        if date < "2024-01-01":
            b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, su, band(dist or 1600), "良" if (going or "良").startswith("良") else "道悪", fin <= 3, p,
                     sire, sl, dsire, dsl))
    exp = {p: v[1] / v[0] for p, v in base.items()}

    def keys(r, who):
        date, co, su, bd, gd, top, p, sire, sl, dsire, dsl = r
        nm, line = (sire, sl) if who == "父" else (dsire, dsl)
        par = (LINES.get(line) or {}).get("parent") or line
        ct = country_type(line) if line else None
        return {"種牡馬": nm, "系統": line, "Wiki系統": WIKI.get(nm or ""), "親系統": par, "国別タイプ": ct}

    cells = {"競馬場×芝ダ×距離帯": lambda r: (r[1], r[2], r[3]), "芝ダ×距離帯×馬場": lambda r: (r[2], r[3], r[4])}
    L = ["# 父・母父の血統をどの細かさでまとめるのが良いか（自動生成, tools/line_granularity.py）", "",
         "- 発見（2021〜23年）で条件セルごとの3着内A/Eを出し、テスト（2024〜26年）の3着内を「人気から見込む率×A/E」で予測したときの対数損失の改善（人気だけとの差, ×10000）。大きいほど良い。",
         "- A/E は頭数 k=100 で1.0に寄せる（少数のぶれを抑える）。階層まとめ＝種牡馬の成績を系統→親系統の成績に、頭数が少ないほど寄せたもの。", "",
         "| 対象 | 条件セル | 種牡馬 | 系統 | Wiki系統 | 親系統 | 国別タイプ | 階層まとめ（種牡馬→系統→親系統） |", "|---|---|--:|--:|--:|--:|--:|--:|"]
    K = 100.0
    for who in ("父", "母父"):
        for cname, cf in cells.items():
            agg = {lv: defaultdict(lambda: [0, 0.0]) for lv in ("種牡馬", "系統", "Wiki系統", "親系統", "国別タイプ")}
            for r in rows:
                if r[0] >= "2024-01-01":
                    continue
                cell = cf(r); ks = keys(r, who)
                for lv, v in ks.items():
                    if v:
                        a = agg[lv][(cell, v)]; a[0] += r[5]; a[1] += exp[r[6]]

            def ae(lv, cell, v, prior=1.0):
                """(実数 + K×prior) / (期待数 + K): 頭数が少ないほど prior に寄せた A/E."""
                a = agg[lv].get((cell, v))
                if not a:
                    return prior, 0.0
                return (a[0] + K * prior) / (a[1] + K), a[1]

            loss = defaultdict(float); n = 0
            for r in rows:
                if r[0] < "2024-01-01":
                    continue
                cell = cf(r); ks = keys(r, who); y = r[5]; q = exp[r[6]]
                preds = {"人気だけ": q}
                for lv in ("種牡馬", "系統", "Wiki系統", "親系統", "国別タイプ"):
                    preds[lv] = q * (ae(lv, cell, ks[lv])[0] if ks[lv] else 1.0)
                pp, _ = ae("親系統", cell, ks["親系統"]) if ks["親系統"] else (1.0, 0)
                pl, _ = ae("系統", cell, ks["系統"], pp) if ks["系統"] else (pp, 0)
                ps, _ = ae("種牡馬", cell, ks["種牡馬"], pl) if ks["種牡馬"] else (pl, 0)
                preds["階層"] = q * ps
                for k_, v in preds.items():
                    v = min(max(v, 1e-4), 0.999)
                    loss[k_] += -(y * math.log(v) + (1 - y) * math.log(1 - v))
                n += 1
            b0 = loss["人気だけ"]
            imp = {k_: (b0 - loss[k_]) / n * 10000 for k_ in loss}
            L.append(f"| {who} | {cname} | {imp['種牡馬']:+.1f} | {imp['系統']:+.1f} | {imp['Wiki系統']:+.1f} | {imp['親系統']:+.1f} | {imp['国別タイプ']:+.1f} | {imp['階層']:+.1f} |")
    L += ["", f"- テストの頭数: {sum(1 for r in rows if r[0] >= '2024-01-01')}"]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
