"""同じコース（競馬場×芝ダ×距離）の直近のレースで3着内に来ていた血統タイプ・脚質は、次の同じコースでも走るか（2026-10-11, SmartRc「傾向速報コース」の考え方の検証）.

各レース R の前に行われた同じコースの直近12レース（60日以内）の3着内馬から、グループ別の3着内A/E（人気からの期待比）を出し、
「好調(1.3以上・10頭以上)」「不調(0.7以下)」「普通」に分け、R でそのグループに入る馬の A/E と複勝回収率を集計する。
グループ: 父タイプ・母父タイプ・父タイプ×母父タイプ（日本/米国/欧州型）・父系統・脚質（過去3走から予想した 前/後）。
発見＝2021〜2023年、テスト＝2024〜2026年。データは各日の7R以降（未勝利除く）のみ。

使い方: python3 tools/course_recent_trend.py → docs/analysis/course_recent_trend.md
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

DB = ROOT / "data" / "keiba.db"
OUT = ROOT / "docs" / "analysis" / "course_recent_trend.md"


def fr(passing, n):
    try:
        return int(str(passing).split("-")[0]) / (n or 16)
    except (ValueError, TypeError):
        return None


def main():
    c = sqlite3.connect(DB)
    races = {}
    for rid, date, co, su, dist, n, pay in c.execute(
            "select race_id,date,course,surface,distance,n_runners,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, key=f"{co}{su}{dist}", n=n, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list)
    base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, num, pas, pop, sl, dsl in c.execute(
            """select r.race_id,r.horse_id,r.finish,r.number,r.passing,r.popularity,h.sire_line,h.damsire_line
               from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"""):
        if rid in races:
            p = min(pop, 14)
            st, dt_ = country_type(sl) if sl else None, country_type(dsl) if dsl else None
            rows[rid].append(dict(hid=hid, fin=fin, num=num, pas=pas, pop=p, sl=sl, st=st, dt=dt_))
            b = base[p]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    order = sorted(races, key=lambda r: (races[r]["date"], r))
    hist = defaultdict(list)
    for rid in order:
        for x in rows[rid]:
            h = [v for v in hist[x["hid"]][-3:] if v is not None]
            x["ps"] = None if not h else "前" if sum(h) / len(h) <= 0.35 else "後" if sum(h) / len(h) >= 0.55 else None
        for x in rows[rid]:
            hist[x["hid"]].append(fr(x["pas"], races[rid]["n"]))

    def groups(x, style):
        g = []
        if x["st"]:
            g.append(("父タイプ", x["st"]))
        if x["dt"]:
            g.append(("母父タイプ", x["dt"]))
        if x["st"] and x["dt"]:
            g.append(("父×母父タイプ", f"{x['st']}×{x['dt']}"))
        if x["sl"]:
            g.append(("父系統", x["sl"]))
        if style:
            g.append(("脚質", style))
        return g

    recent = defaultdict(deque)  # course key -> deque of (date, rid)
    res = defaultdict(lambda: [0, 0, 0.0, 0])
    for rid in order:
        R = races[rid]; q = recent[R["key"]]
        D = dt.date.fromisoformat(R["date"])
        prev = [r for d, r in q if 0 < (D - d).days <= 60][-12:]
        if len(prev) >= 6:
            stat = defaultdict(lambda: [0, 0, 0.0])
            for pr in prev:
                n = races[pr]["n"]
                for x in rows[pr]:
                    f = fr(x["pas"], n)
                    style = None if f is None else "前" if f <= 0.35 else "後" if f >= 0.55 else None
                    for g in groups(x, style):
                        s = stat[g]; s[0] += 1; s[1] += x["fin"] <= 3; s[2] += exp[x["pop"]]
            per = "発見" if R["date"] < "2024-01-01" else "テスト"
            fk = {cc: y for cc, y in R["pay"].get("複勝", [])}
            for x in rows[rid]:
                for g in groups(x, x["ps"]):
                    s = stat.get(g)
                    lab = "データ少" if not s or s[0] < 10 else ("好調" if s[1] / s[2] >= 1.3 else "不調" if s[1] / s[2] <= 0.7 else "普通")
                    for key in ((per, g[0], lab, "全人気"), (per, g[0], lab, "7人気以下" if x["pop"] >= 7 else "1〜6人気")):
                        r = res[key]; r[0] += 1; r[1] += x["fin"] <= 3; r[2] += exp[x["pop"]]; r[3] += fk.get(str(x["num"]), 0)
        q.append((D, rid))
        while q and (D - q[0][0]).days > 90:
            q.popleft()
    L = ["# 同じコースの直近の傾向は次も続くか（自動生成, tools/course_recent_trend.py）", "",
         "- 同じ競馬場×芝ダ×距離の直近12レース（60日以内・6レース以上）で、グループ別の3着内A/Eを出し、好調(1.3以上)・不調(0.7以下)・普通に分類（10頭以上）。",
         "- 次の同じコースのレースで、そのグループの馬の A/E（人気からの期待比）と複勝回収率。発見＝2021〜23年 / テスト＝2024〜26年。各日7R以降のみ。", "",
         "| グループ | 直近の状態 | 人気 | 頭数 発見/テスト | A/E 発見/テスト | 複勝回収 発見/テスト |", "|---|---|---|--:|--:|--:|"]
    for gk in ("父タイプ", "母父タイプ", "父×母父タイプ", "父系統", "脚質"):
        for lab in ("好調", "普通", "不調"):
            for sub in ("全人気", "1〜6人気", "7人気以下"):
                a = res.get(("発見", gk, lab, sub)); b = res.get(("テスト", gk, lab, sub))
                if not a or not b or a[0] < 200 or b[0] < 200:
                    continue
                L.append(f"| {gk} | {lab} | {sub} | {a[0]}/{b[0]} | {a[1]/a[2]:.2f} / {b[1]/b[2]:.2f} | {a[3]/a[0]:.0f}% / {b[3]/b[0]:.0f}% |")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
