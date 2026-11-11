"""同じ週末（前日・前々日）に走れていた血統・位置取り・枠は、翌日も走るか（2026-10-11, 亀谷敬正氏の「当日までの馬場傾向→翌日の傾向該当馬」の検証）.

各開催日 D・競馬場×芝ダごとに、3日以内の前の開催日（同じ週末）の結果から、グループ別の3着内A/E（人気からの期待比）を出し、
「好調（A/E 1.3以上・8頭以上）」「不調（0.7以下）」「普通」に分ける。D 当日、各グループに入る馬の A/E と複勝回収率を集計する。
グループ: 父系統・母父系統・父の国別タイプ（日本/米国/欧州型）・脚質（過去3走の位置から予想した 前/後）・枠（内1-3/外7-8）。
D の脚質は過去の走りから予想したもの（当日の通過順は使わない）。前日側は実際の通過順。
発見＝2021〜2023年、テスト＝2024〜2026年。3日間開催の3日目（月曜など）も別に集計。

使い方: python3 tools/weekend_bias_analysis.py → docs/analysis/weekend_bias.md
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

DB = ROOT / "data" / "keiba.db"
OUT = ROOT / "docs" / "analysis" / "weekend_bias.md"


def first_ratio(passing, n):
    try:
        p = int(str(passing).split("-")[0])
    except (ValueError, TypeError):
        return None
    return p / n if n else None


def main():
    c = sqlite3.connect(DB)
    races = {}
    for rid, date, course, surf, n, pay in c.execute(
            "select race_id,date,course,surface,n_runners,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, course=course, surf=surf, n=n, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list)
    for rid, hid, fin, num, gate, passing, pop, sl, dsl in c.execute(
            """select r.race_id,r.horse_id,r.finish,r.number,r.gate,r.passing,r.popularity,h.sire_line,h.damsire_line
               from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"""):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, num=num, gate=gate, passing=passing, pop=min(pop, 14), sl=sl, dsl=dsl))
    # 人気別の基準3着内率
    base = defaultdict(lambda: [0, 0])
    for rid, rs in rows.items():
        for x in rs:
            b = base[x["pop"]]; b[0] += 1; b[1] += x["fin"] <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    # 予想脚質（そのレースより前の過去3走の最初の位置）
    order = sorted(races, key=lambda r: (races[r]["date"], r))
    hist = defaultdict(list)
    for rid in order:
        n = races[rid]["n"] or len(rows[rid])
        for x in rows[rid]:
            h = [v for v in hist[x["hid"]][-3:] if v is not None]
            x["pstyle"] = (None if not h else "前" if sum(h) / len(h) <= 0.35 else "後" if sum(h) / len(h) >= 0.55 else None)
            x["astyle"] = (lambda fr: None if fr is None else "前" if fr <= 0.35 else "後" if fr >= 0.55 else None)(first_ratio(x["passing"], n))
        for x in rows[rid]:
            hist[x["hid"]].append(first_ratio(x["passing"], n))

    def groups(x, actual):
        g = []
        if x["sl"]:
            g.append(("父系統", x["sl"]))
            ct = country_type(x["sl"])
            if ct:
                g.append(("父の国別タイプ", ct))
        if x["dsl"]:
            g.append(("母父系統", x["dsl"]))
        st = x["astyle"] if actual else x["pstyle"]
        if st:
            g.append(("脚質", st))
        if x["gate"]:
            g.append(("枠", "内" if x["gate"] <= 3 else "外" if x["gate"] >= 7 else "中"))
        return g

    byday = defaultdict(list)  # (course, surf, date) -> race ids
    for rid, R in races.items():
        byday[(R["course"], R["surf"], R["date"])].append(rid)
    dates = defaultdict(set)
    for (co, su, d) in byday:
        dates[(co, su)].add(d)
    res = defaultdict(lambda: [0, 0, 0.0, 0])  # key -> n, top3, exp, fukusho
    for (co, su), ds in dates.items():
        for d in sorted(ds):
            D = dt.date.fromisoformat(d)
            prev = [p for p in ds if 1 <= (D - dt.date.fromisoformat(p)).days <= 3]
            if not prev:
                continue
            third = len(prev) >= 2  # 3日間開催の3日目（前の2日もある）
            stat = defaultdict(lambda: [0, 0, 0.0])
            for p in prev:
                for rid in byday[(co, su, p)]:
                    for x in rows[rid]:
                        for g in groups(x, True):
                            s = stat[g]; s[0] += 1; s[1] += x["fin"] <= 3; s[2] += exp[x["pop"]]
            period = "発見" if d < "2024-01-01" else "テスト"
            for rid in byday[(co, su, d)]:
                R = races[rid]
                for x in rows[rid]:
                    fk = 0
                    for cc, y in R["pay"].get("複勝", []):
                        if cc == str(x["num"]):
                            fk = y
                    for g in groups(x, False):
                        s = stat.get(g)
                        if not s or s[0] < 8:
                            lab = "データ少"
                        else:
                            ae = s[1] / s[2] if s[2] else 1
                            lab = "好調" if ae >= 1.3 else "不調" if ae <= 0.7 else "普通"
                        for key in ((period, g[0], lab, "全体"), (period, g[0], lab, "3日目" if third else "1〜2日目")):
                            r = res[key]; r[0] += 1; r[1] += x["fin"] <= 3; r[2] += exp[x["pop"]]; r[3] += fk
                        if g[0] in ("脚質", "枠"):
                            for key in ((period, f"{g[0]}={g[1]}", lab, su),):
                                r = res[key]; r[0] += 1; r[1] += x["fin"] <= 3; r[2] += exp[x["pop"]]; r[3] += fk
    L = ["# 前日までの週末の傾向は翌日も続くか（自動生成, tools/weekend_bias_analysis.py）", "",
         "- 前の1〜3日以内（同じ週末）の同じ競馬場×芝ダの結果で、グループごとの3着内A/E（人気からの期待比）を出し、好調(1.3以上)・不調(0.7以下)・普通に分類（8頭以上）。",
         "- その翌日、各グループの馬が人気以上に走ったか（A/E）と複勝回収率。発見＝2021〜2023年、テスト＝2024〜2026年。データは各日の7R以降のみ。",
         "- 脚質は当日の通過順ではなく過去3走から予想したもの（前＝前35%以内、後＝後ろ45%）。", "",
         "| グループ | 前日までの状態 | 区分 | 頭数 発見/テスト | A/E 発見/テスト | 複勝回収 発見/テスト |", "|---|---|---|--:|--:|--:|"]
    keys = sorted({k[1:] for k in res})
    for gk, lab, sub in keys:
        a = res.get(("発見", gk, lab, sub)); b = res.get(("テスト", gk, lab, sub))
        if not a or not b or a[0] < 150 or b[0] < 150:
            continue
        L.append(f"| {gk} | {lab} | {sub} | {a[0]}/{b[0]} | {a[1]/a[2]:.2f} / {b[1]/b[2]:.2f} | {a[3]/a[0]:.0f}% / {b[3]/b[0]:.0f}% |")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
