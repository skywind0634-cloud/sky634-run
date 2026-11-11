"""種牡馬のクセの網羅スキャン（2026-10-15）: 父・母父 × レース前に分かる条件（単独）で、人気から見込む3着内数との差を探す.
条件: 芝ダ / 距離延長・短縮・同距離 / 芝ダ替わり（芝→ダ・ダ→芝）/ 枠（内1-3・中4-5・外6-8）/ 間隔（連闘〜中2週・中3-8週・9週以上）/
  馬場（良・道悪）/ 坂・平坦 / 直線長・短 / 頭数（〜12・13〜15・16〜）/ 斤量増減（前走比 +1kg以上・-1kg以下）/ 前走着順（1-3着・4-9着・10着以下）/
  前走着差（0.5秒内・0.5-1.5秒・1.5秒以上）/ クラス（昇級・降級・同級）/ 年齢（2-3歳・4歳・5歳以上）/ 性別（牡セ・牝）/ 季節（春夏秋冬）。
  すべて「芝ダ×条件」で集計（芝とダートは分ける）。
採用基準は保留検証で決める: 2021-24年で選び、2025-26年に同じ向きが出る割合と上積み（tools/sire_quirks.py --validate）。
出力: data/knowledge/sire_quirks.json（3期間とも同じ向きのもの）, docs/analysis/sire_quirks.md
使い方: python3 tools/sire_quirks.py [--validate]
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLOPE = {"中山", "阪神", "中京", "東京"}
LONG = {"東京", "新潟", "阪神", "京都", "中京"}
GR = {"1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4, "G3": 5, "G2": 6, "G1": 7}


def conditions(R, x, prev):
    su = R["su"]; c = [su]
    g = x["gate"]
    if g:
        c.append(f"{su}・{'内枠1-3' if g <= 3 else '外枠6-8' if g >= 6 else '中枠4-5'}")
    c.append(f"{su}・{'良' if R['going'].startswith('良') else '道悪'}")
    c.append(f"{su}・{'坂' if R['co'] in SLOPE else '平坦'}")
    c.append(f"{su}・直線{'長' if R['co'] in LONG else '短'}")
    n = R["n"]; c.append(f"{su}・{'〜12頭' if n <= 12 else '13-15頭' if n <= 15 else '16頭〜'}")
    a = x["age"]
    if a:
        c.append(f"{su}・{'2-3歳' if a <= 3 else '4歳' if a == 4 else '5歳以上'}")
    c.append(f"{su}・{'牝' if (x['sex'] or '').startswith('牝') else '牡セ'}")
    m = int(R["date"][5:7]); c.append(f"{su}・{'春' if 3 <= m <= 5 else '夏' if 6 <= m <= 8 else '秋' if 9 <= m <= 11 else '冬'}")
    if prev:
        if prev["su"] != su:
            c.append(f"{prev['su']}→{su}")
        else:
            d = R["dist"] - prev["dist"]
            c.append(f"{su}・{'延長' if d >= 200 else '短縮' if d <= -200 else '同距離'}")
        days = (dt.date.fromisoformat(R["date"]) - dt.date.fromisoformat(prev["date"])).days
        c.append(f"{su}・{'中2週以内' if days <= 21 else '中3-8週' if days <= 63 else '9週以上'}")
        if x["wc"] and prev["wc"]:
            w = x["wc"] - prev["wc"]
            if w >= 1:
                c.append(f"{su}・斤量増")
            elif w <= -1:
                c.append(f"{su}・斤量減")
        f = prev["fin"]
        if f:
            c.append(f"{su}・前走{'1-3着' if f <= 3 else '4-9着' if f <= 9 else '10着以下'}")
        b = prev["b"]
        if b is not None and f and f > 1:
            c.append(f"{su}・前走{'0.5秒内' if b <= 0.5 else '0.5-1.5秒' if b < 1.5 else '1.5秒以上'}負け")
        g0, g1 = GR.get(prev["grade"], 4), GR.get(R["grade"], 4)
        c.append(f"{su}・{'昇級' if g1 > g0 else '降級' if g1 < g0 else '同級'}")
    return c


def collect():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, su, dist, going, n, grade in c.execute(
            "select race_id,date,course,surface,distance,going,n_runners,grade from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, going=going or "良", n=n or 16, grade=grade)
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, gate, age, sex, wc, t, sire, ds in c.execute(
            """select r.race_id,r.horse_id,r.finish,r.popularity,r.gate,r.age,r.sex,r.weight_carried,r.time_sec,h.sire,h.damsire
               from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"""):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, p=min(pop, 14), gate=gate, age=age, sex=sex, wc=wc, t=t, sire=sire, ds=ds))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = {}
    agg = defaultdict(lambda: [[0, 0, 0.0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; rs = rows[rid]
        per = 0 if R["date"] < "2024-01-01" else 1 if R["date"] < "2025-01-01" else 2
        wt = min((x["t"] for x in rs if x["fin"] == 1 and x["t"]), default=None)
        for x in rs:
            cs = conditions(R, x, hist.get(x["hid"]))
            e = exp[x["p"]]
            for who, nm in (("父", x["sire"]), ("母父", x["ds"])):
                if not nm:
                    continue
                for cd in cs:
                    a = agg[(who, nm, cd)][per]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += e
        for x in rs:
            hist[x["hid"]] = dict(date=R["date"], su=R["su"], dist=R["dist"], wc=x["wc"], fin=x["fin"], grade=R["grade"],
                                  b=(x["t"] - wt) if (x["t"] and wt and x["fin"]) else None)
    return agg


def validate(agg):
    print("2021-24年で選んで2025-26年に確かめる（同じ向きの割合・上積み）")
    for nmin, th, dmin in ((40, 1.15, 4), (60, 1.15, 6), (80, 1.2, 8), (100, 1.1, 8), (150, 1.1, 10), (200, 1.08, 12), (120, 1.15, 10)):
        tot = ok = 0; s1 = s2 = 0.0
        for k, (a, b, t) in agg.items():
            n0 = a[0] + b[0]
            if n0 < nmin or b[0] < nmin // 4 or t[0] < 20 or not a[2] or not b[2] or not t[2]:
                continue
            ra, rb = a[1] / a[2], b[1] / b[2]; d = (a[1] + b[1]) - (a[2] + b[2])
            lo = 2 - th
            if ((ra >= th and rb >= th) or (ra <= lo and rb <= lo)) and abs(d) >= dmin:
                up = ra >= th; tot += 1; rt = t[1] / t[2]; ok += (rt > 1) if up else (rt < 1)
                s1 += (t[1] - t[2]) * (1 if up else -1); s2 += t[2]
        print(f"  2021-24年 {nmin}走以上・A/E {th}/{2-th:.2f}・差{dmin}頭以上: {tot}件 → 2025-26年も同じ向き {ok/max(tot,1)*100:.0f}% / 上積み {s1/max(s2,1)*100:+.1f}%")


def main():
    agg = collect()
    if "--validate" in sys.argv:
        validate(agg); return
    out = []
    for (who, nm, cd), A in agg.items():
        if sum(x[0] for x in A[:2]) < 200 or A[1][0] < 50 or A[2][0] < 30 or not all(x[2] for x in A):
            continue
        ae = [x[1] / x[2] for x in A]
        d = sum(x[1] - x[2] for x in A)
        if ((min(ae[:2]) >= 1.08 and ae[2] >= 1.0) or (max(ae[:2]) <= 0.92 and ae[2] <= 1.0)) and abs(d) >= 12:
            out.append({"who": who, "name": nm, "cond": cd, "mark": "○" if ae[0] >= 1 else "▼", "ae": [round(v, 2) for v in ae],
                        "n": [x[0] for x in A], "diff": round(d, 1)})
    out.sort(key=lambda o: (o["who"], o["name"], o["cond"]))
    (ROOT / "data" / "knowledge" / "sire_quirks.json").write_text(json.dumps(
        {"_meta": "種牡馬（父・母父）×条件のクセ。2021-23/2024で A/E 1.08以上(○)/0.92以下(▼)・2025-26も同じ向き・2021-24で200走以上・見込みとの差±12頭以上（2021-24年で選ぶと2025-26年も同じ向き65%・上積み+4.6%）。tools/sire_quirks.py",
         "rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# 種牡馬のクセ（父・母父×条件, 網羅スキャン, 自動生成 tools/sire_quirks.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数（発見2021-23 / 確認2024 / テスト2025-26）。○＝人気以上、▼＝人気以下。",
         "- 採用: 2021-23と2024で1.08以上/0.92以下、2025-26も同じ向き、2021-24で200走以上、見込みとの差±12頭以上。この基準で2021-24年に選んだものは2025-26年も65%が同じ向き（上積み+4.6%）。", "",
         "| 父/母父 | 種牡馬 | 条件 | | A/E | 走数 | 見込みとの差 |", "|---|---|---|---|---|---|---|"]
    for o in out:
        L.append(f"| {o['who']} | {o['name']} | {o['cond']} | {o['mark']} | " + "/".join(f"{v:.2f}" for v in o["ae"]) + " | " + "/".join(map(str, o["n"])) + f" | {o['diff']:+.1f} |")
    L.append(f"\n- 計 {len(out)} 件（○{sum(o['mark'] == '○' for o in out)} / ▼{sum(o['mark'] == '▼' for o in out)}）")
    (ROOT / "docs" / "analysis" / "sire_quirks.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(L[-1])


if __name__ == "__main__":
    main()
