"""亀谷『血統の教科書』第4章 ナスルーラ系（p112-125）の検証（2026-10-12）.
- 父プリンスリーギフト系（本では日本型。DBの機械分類は欧州型）: 芝・良/道悪、芝1200以下、平坦/坂
- 5代にサクラバクシンオー / 母父サクラバクシンオー: 芝1200以下×平坦（小倉・福島・新潟・札幌・函館・京都）/坂、良/道悪
- 5代にカロ・コジーン・フォルティノ（グレイソヴリン〜フォルティノ系）: 芝1400以下 / 芝1600以上、前に行く馬の多いレース
- 5代にトニービン: 芝2500以上、実際のペース型（持続・平均 vs 瞬発）
- 母父ジャングルポケット: 芝・直線短/長、芝・上がり（レースの後半3F）がかかる/速い
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch4_nasrullah.py <ped5_full.json> → docs/analysis/book_ch4_nasrullah.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAT = {"小倉", "福島", "新潟", "札幌", "函館", "京都"}
LONG = {"東京", "新潟", "阪神", "京都", "中京"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pedpath):
    H = json.loads(Path(pedpath).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, co, su, dist, going, pt, l3r, hid, fin, pop, num, sl, ds, pay in c.execute(
            """select ra.date, ra.course, ra.surface, ra.distance, ra.going, ra.pace_type, ra.last3f, r.horse_id, r.finish, r.popularity, r.number,
                      h.sire_line, h.damsire, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface='芝' and r.finish is not null and r.popularity is not null"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, co, dist or 1600, going or "良", pt, l3r, hid, fin, p, num, sl, ds, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    # レース上がり3Fの距離帯別の中央値で「かかる/速い」
    l3 = defaultdict(list)
    for r in rows:
        if r[5]:
            l3[(r[2] // 200)].append(r[5])
    med = {k: sorted(v)[len(v) // 2] for k, v in l3.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}
    for date, co, dist, going, pt, l3r, hid, fin, p, num, sl, ds, pay in rows:
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0); pr = per(date)
        names = set(n for n in (H.get(hid) or []) if n)
        good = going.startswith("良")
        K = []
        if sl == "プリンスリーギフト系":
            K += [("父プリンスリーギフト系", f"芝・{'良' if good else '道悪'}")]
            if dist <= 1200:
                K += [("父プリンスリーギフト系", f"芝1200以下・{'平坦' if co in FLAT else '坂'}")]
        if "サクラバクシンオー" in names:
            if dist <= 1200:
                K += [("5代にサクラバクシンオー", f"芝1200以下・{'平坦' if co in FLAT else '坂'}"), ("5代にサクラバクシンオー", f"芝1200以下・{'良' if good else '道悪'}")]
            else:
                K += [("5代にサクラバクシンオー", "芝1400以上")]
        if ds == "サクラバクシンオー":
            K += [("母父サクラバクシンオー", "芝1200以下" if dist <= 1200 else "芝1400-1800" if dist <= 1800 else "芝2000以上")]
        if names & {"Caro", "カロ", "Cozzene", "コジーン", "Fortino", "フォルティノ"}:
            K += [("5代にカロ/コジーン/フォルティノ", "芝1400以下" if dist <= 1400 else "芝1600以上")]
        if names & {"Tony Bin", "トニービン"}:
            if dist >= 2500:
                K += [("5代にトニービン", "芝2500以上")]
            if pt:
                K += [("5代にトニービン", f"芝・実際のペース{pt}")]
        if ds == "ジャングルポケット":
            K += [("母父ジャングルポケット", f"芝・直線{'長' if co in LONG else '短'}")]
            if l3r and (dist // 200) in med:
                K += [("母父ジャングルポケット", f"芝・上がり{'かかる' if l3r > med[dist // 200] else '速い'}")]
        for k in K:
            x = agg[k][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 ナスルーラ系（p112-125）の検証（自動生成 tools/book_ch4_nasrullah.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    keep = []
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 40:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
        if m:
            keep.append({"blood": k[0], "cond": k[1], "mark": m, "ae": [round(v, 2) for v in ae]})
    (ROOT / "docs" / "analysis" / "book_ch4_nasrullah.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "book_ch4_nasrullah.json").write_text(json.dumps({"_meta": "tools/book_ch4_nasrullah.py", "rows": keep}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
