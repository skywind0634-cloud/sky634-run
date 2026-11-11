"""主流／反主流のずれ（亀谷『血統の教科書』p13-14, 46-55）の検証（2026-10-12）.

主張: 反主流馬場（タフな芝・道悪・小回り/平坦・非根幹距離など）なのに人気上位が主流血統（日本型）に偏ると、反主流血統（欧州・米国型）の人気薄が来て荒れる。
検証: 芝のレースを馬場の主流度で分け、1〜3番人気の日本型の頭数で分ける。4番人気以下の反主流血統（父が欧州型か米国型）の3着内A/E・単複回収率、
1〜3番人気の3着内A/E、3連複の平均配当を、発見2021-23 / 確認2024 / テスト2025-26 で集計する。
使い方: python3 tools/mainstream_gap.py → docs/analysis/mainstream_gap.md
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

MAIN4 = {"東京", "中山", "京都", "阪神"}
ROOT_DIST = {1600, 2000, 2400}


def field_class(co, dist, going):
    good = (going or "良").startswith("良")
    if co in MAIN4 and dist in ROOT_DIST and good:
        return "主流（中央4場・芝1600/2000/2400・良）"
    if not good:
        return "反主流（道悪）"
    if co in ("札幌", "函館"):
        return "反主流（洋芝）"
    if co in ("福島", "小倉") or dist <= 1200:
        return "反主流（小回り平坦・芝1200以下）"
    if dist not in (1200, 1600, 2000, 2400):
        return "準主流（良・非根幹距離）"
    return "準主流（良・その他）"


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {r[0]: dict(date=r[1], co=r[2], dist=r[3] or 1600, going=r[4], pay=json.loads(r[5]) if r[5] else {})
             for r in c.execute("select race_id,date,course,distance,going,payouts from races where surface='芝'")}
    rows = defaultdict(list)
    base = defaultdict(lambda: [0, 0])
    for rid, fin, pop, num, sl in c.execute(
            "select r.race_id, r.finish, r.popularity, r.number, h.sire_line from results r join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid in races:
            rows[rid].append((fin, min(pop, 14), num, country_type(sl) if sl else None, pop))
    for rs in rows.values():
        for fin, p, *_ in rs:
            b = base[p]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    fav = defaultdict(lambda: [[0, 0, 0.0] for _ in range(3)])
    tri = defaultdict(lambda: [[] for _ in range(3)])
    for rid, R in races.items():
        rs = rows[rid]
        if len(rs) < 8:
            continue
        top = [t for fin, p, num, t, pop in rs if pop <= 3]
        if len(top) < 3 or None in top:
            continue
        nj = sum(t == "日本型" for t in top)
        grp = "1〜3人気すべて日本型" if nj == 3 else "1〜3人気に反主流あり"
        fc = field_class(R["co"], R["dist"], R["going"]); pr = per(R["date"])
        fk = {cc: y for cc, y in R["pay"].get("複勝", [])}; tk = {cc: y for cc, y in R["pay"].get("単勝", [])}
        t3 = R["pay"].get("3連複") or []
        for key in ((fc, grp), ("全体", grp)):
            if t3:
                tri[key][pr].append(t3[0][1])
            for fin, p, num, t, pop in rs:
                if pop <= 3:
                    f = fav[key][pr]; f[0] += 1; f[1] += fin <= 3; f[2] += exp[p]
                elif t in ("欧州型", "米国型"):
                    for sub in ("4番人気以下", "4-9番人気" if pop <= 9 else "10番人気以下"):
                        a = agg[key + (sub,)][pr]
                        a[0] += 1; a[1] += fin <= 3; a[2] += exp[p]; a[3] += fk.get(str(num), 0); a[4] += tk.get(str(num), 0)
    L = ["# 主流／反主流のずれ（亀谷『血統の教科書』の考え方, 自動生成 tools/mainstream_gap.py）", "",
         "- 芝のレース。A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。反主流血統＝父が欧州型か米国型。", ""]
    for fc in sorted({k[0] for k in fav}):
        L += [f"## {fc}", "", "| 人気上位 | レース数 | 1〜3人気のA/E | 3連複の平均配当 | 反主流血統の人気薄 | 頭数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|---|"]
        for grp in ("1〜3人気すべて日本型", "1〜3人気に反主流あり"):
            F = fav.get((fc, grp)); T = tri.get((fc, grp))
            if not F:
                continue
            for sub in ("4番人気以下", "4-9番人気", "10番人気以下"):
                A = agg.get((fc, grp, sub))
                if not A:
                    continue
                L.append(f"| {grp} | " + "/".join(str(len(t)) for t in T) + " | " + "/".join(f"{f[1]/f[2]:.2f}" if f[2] else "-" for f in F)
                         + " | " + "/".join(f"{statistics.mean(t):,.0f}" if t else "-" for t in T) + f" | {sub} | " + "/".join(str(a[0]) for a in A)
                         + " | " + "/".join(f"{a[1]/a[2]:.2f}" if a[2] else "-" for a in A) + " | " + "/".join(f"{a[3]/a[0]:.0f}" if a[0] else "-" for a in A)
                         + "% | " + "/".join(f"{a[4]/a[0]:.0f}" if a[0] else "-" for a in A) + "% |")
        L.append("")
    (ROOT / "docs" / "analysis" / "mainstream_gap.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
