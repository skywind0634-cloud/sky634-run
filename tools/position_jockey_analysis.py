"""位置取り（脚質・展開）と騎手から人気薄（7〜12番人気）の好走条件を探す（2026-10-11）.

各馬の特徴はそのレースより前の成績だけから作る（未来の情報は使わない）。騎手の成績は前年1年分。
発見期間（2021〜2023）で選び、テスト期間（2024〜2026）で確かめる。
評価: 3着内率の人気からの期待比（A/E）、複勝・ワイド（1番人気と）・3連複（軸−1番人気−2番人気）の実払戻での回収率。

使い方: python3 tools/position_jockey_analysis.py  → docs/analysis/position_jockey.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "keiba.db"
OUT = ROOT / "docs" / "analysis" / "position_jockey.md"


def first_last(passing, n):
    try:
        ps = [int(x) for x in str(passing).split("-") if x.strip().isdigit()]
    except ValueError:
        return None, None
    if not ps or not n:
        return None, None
    return ps[0] / n, ps[-1] / n


def load():
    c = sqlite3.connect(DB)
    races = {}
    for rid, date, course, surf, dist, n, pay, grade in c.execute(
            "select race_id,date,course,surface,distance,n_runners,payouts,grade from races where date>='2020-12-01'"):
        races[rid] = dict(date=date, ck=f"{course}{surf}{dist}", surf=surf, dist=dist, n=n,
                          pay=json.loads(pay) if pay else {}, grade=grade)
    rows = defaultdict(list)
    for rid, hid, fin, num, jockey, margin, passing, l3, pop in c.execute(
            "select race_id,horse_id,finish,number,jockey,time_sec,passing,last3f,popularity from results"):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, num=num, j=(jockey or "").lstrip("▲△☆★◇"), margin=margin,
                                  passing=passing, l3=l3, pop=pop))
    return races, rows


def main():
    races, rows = load()
    order = sorted(races, key=lambda r: (races[r]["date"], r))
    # 上がり順位・勝ち馬とのタイム差（margin に秒差を入れ直す）
    for rid in order:
        ts = [x["margin"] for x in rows[rid] if x["margin"]]
        w = min(ts) if ts else None
        for x in rows[rid]:
            x["margin"] = round(x["margin"] - w, 1) if (w is not None and x["margin"]) else None
        rs = [x for x in rows[rid] if x["l3"]]
        for i, x in enumerate(sorted(rs, key=lambda x: x["l3"])):
            x["l3rank"] = i + 1
    hist = defaultdict(list)  # horse -> past runs
    jstat = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))  # year -> jockey -> [rides, wins, front]
    samples = []
    for rid in order:
        R = races[rid]; n = R["n"] or len(rows[rid]); yr = int(R["date"][:4])
        ent = rows[rid]
        # 各馬の事前プロファイル
        prof = {}
        for x in ent:
            h = hist[x["hid"]][-3:]
            fr = [p["fr"] for p in h if p["fr"] is not None]
            prof[x["hid"]] = dict(fr=sum(fr) / len(fr) if fr else None, h=h)
        front_n = sum(1 for p in prof.values() if p["fr"] is not None and p["fr"] <= 0.2)
        mins = sorted(p["fr"] for p in prof.values() if p["fr"] is not None)
        prevj = jstat.get(yr - 1, {})
        for x in ent:
            P = prof[x["hid"]]; h = P["h"]
            if x["pop"] and 7 <= x["pop"] <= 12 and len(h) >= 2 and P["fr"] is not None and x["fin"]:
                last = h[-1]
                f = {}
                fr = P["fr"]
                f["逃げ先行型（過去3走の位置が前20%）"] = fr <= 0.2
                f["単騎逃げ候補（最も前で、他に前20%の馬がいない）"] = fr == mins[0] and front_n <= 1 and fr <= 0.2
                f["前に行く馬が少ない（前20%が1頭以下）×先行型(前35%)"] = front_n <= 1 and fr <= 0.35
                f["前に行く馬が多い（前20%が4頭以上）×差し追込型(後ろ55%)"] = front_n >= 4 and fr >= 0.55
                f["前走 後方(4角後ろ60%)から上がり2位以内で4着以下"] = (last["lr"] or 0) >= 0.6 and (last["l3rank"] or 99) <= 2 and (last["fin"] or 0) >= 4
                f["前走 先行(前25%)して0.5秒差以内"] = (last["fr"] or 1) <= 0.25 and (last["margin"] or 9) <= 0.5
                f["過去3走の上がり順位平均3位以内"] = (sum(p["l3rank"] or 9 for p in h) / len(h)) <= 3
                f["前走より位置を取れる見込み（前走後ろ60%→普段前35%）"] = (last["fr"] or 0) >= 0.6 and fr <= 0.35
                pj, cj = last["j"], x["j"]
                ps, cs = prevj.get(pj), prevj.get(cj)
                cwr = cs[1] / cs[0] if cs and cs[0] >= 100 else None
                pwr = ps[1] / ps[0] if ps and ps[0] >= 100 else 0.0
                cfront = cs[2] / cs[0] if cs and cs[0] >= 100 else None
                f["乗り替わりで騎手の勝率が上がる（前年勝率が前騎手の1.5倍以上・10%以上）"] = pj != cj and cwr is not None and cwr >= 0.10 and cwr >= 1.5 * max(pwr, 0.01)
                f["騎手の前年勝率12%以上"] = cwr is not None and cwr >= 0.12
                f["前に行かせる騎手（前年の騎乗の45%以上で前25%）"] = cfront is not None and cfront >= 0.45
                f["前に行かせる騎手×中団型(前25〜50%)"] = cfront is not None and cfront >= 0.45 and 0.25 < fr <= 0.5
                f["同じ騎手で継続騎乗"] = pj == cj
                samples.append(dict(rid=rid, yr=yr, pop=x["pop"], num=x["num"], fin=x["fin"], f=f))
        # 当日の結果を履歴に追加
        for x in ent:
            fr, lr = first_last(x["passing"], n)
            hist[x["hid"]].append(dict(fr=fr, lr=lr, fin=x["fin"], margin=x["margin"], l3rank=x.get("l3rank"), j=x["j"]))
            s = jstat[yr][x["j"]]; s[0] += 1; s[1] += x["fin"] == 1; s[2] += fr is not None and fr <= 0.25
    report(samples, races, rows)


def pays(R, kind, key):
    for c, y in R["pay"].get(kind, []):
        if c == key:
            return y
    return 0


def report(samples, races, rows):
    base = defaultdict(lambda: [0, 0])
    for s in samples:
        b = base[(s["yr"] <= 2023, s["pop"])]; b[0] += 1; b[1] += s["fin"] <= 3
    names = list(samples[0]["f"])
    L = ["# 位置取り（脚質・展開）と騎手から見た人気薄の好走条件（自動生成, tools/position_jockey_analysis.py）", "",
         f"- 対象: 7〜12番人気で過去2走以上ある馬 {len(samples)} 頭。特徴はそのレースより前の情報だけで作成（騎手は前年の成績）。",
         "- 発見＝2021〜2023年、テスト＝2024〜2026年。A/E＝3着内の実数÷人気から見込む数。",
         "- ワイド＝その馬と1番人気、3連複＝その馬−1番人気−2番人気（各1点）。いずれも実際の払戻。", "",
         "| 特徴 | 頭数 発見/テスト | 3着内率 | A/E 発見/テスト | 複勝回収 発見/テスト | ワイド(1人気と) | 3連複(1・2人気と) |",
         "|---|--:|--:|--:|--:|--:|--:|"]
    res = []
    for nm in names + ["(全体)"]:
        agg = {True: [0, 0, 0.0, 0, 0, 0], False: [0, 0, 0.0, 0, 0, 0]}
        for s in samples:
            if nm != "(全体)" and not s["f"][nm]:
                continue
            a = agg[s["yr"] <= 2023]; R = races[s["rid"]]
            a[0] += 1; a[1] += s["fin"] <= 3
            b = base[(s["yr"] <= 2023, s["pop"])]; a[2] += b[1] / b[0]
            a[3] += pays(R, "複勝", str(s["num"]))
            fav = {x["pop"]: x["num"] for x in rows[s["rid"]] if x["pop"]}
            if 1 in fav:
                a[4] += pays(R, "ワイド", "-".join(map(str, sorted((s["num"], fav[1])))))
            if 1 in fav and 2 in fav:
                a[5] += pays(R, "3連複", "-".join(map(str, sorted((s["num"], fav[1], fav[2])))))
        d, t = agg[True], agg[False]
        if d[0] < 100 or t[0] < 100:
            continue
        res.append((nm, d, t))
    for nm, d, t in sorted(res, key=lambda x: -min(x[1][1] / x[1][2], x[2][1] / x[2][2])):
        L.append(f"| {nm} | {d[0]}/{t[0]} | {(d[1]+t[1])/(d[0]+t[0]):.1%} | {d[1]/d[2]:.2f} / {t[1]/t[2]:.2f} | "
                 f"{d[3]/d[0]:.0f}% / {t[3]/t[0]:.0f}% | {d[4]/d[0]:.0f}% / {t[4]/t[0]:.0f}% | {d[5]/d[0]:.0f}% / {t[5]/t[0]:.0f}% |")
    # 2つの組み合わせ（発見でA/E 1.2以上 → テスト確認）
    L += ["", "## 特徴2つの組み合わせ（発見でA/E 1.25以上・150頭以上を選び、テストで確認）", "",
          "| 組み合わせ | 頭数 発見/テスト | 3着内率 | A/E 発見/テスト | 複勝回収 | ワイド(1人気と) | 3連複(1・2人気と) |", "|---|--:|--:|--:|--:|--:|--:|"]
    for i, a1 in enumerate(names):
        for a2 in names[i + 1:]:
            agg = {True: [0, 0, 0.0, 0, 0, 0], False: [0, 0, 0.0, 0, 0, 0]}
            for s in samples:
                if not (s["f"][a1] and s["f"][a2]):
                    continue
                a = agg[s["yr"] <= 2023]; R = races[s["rid"]]
                a[0] += 1; a[1] += s["fin"] <= 3
                b = base[(s["yr"] <= 2023, s["pop"])]; a[2] += b[1] / b[0]
                a[3] += pays(R, "複勝", str(s["num"]))
                fav = {x["pop"]: x["num"] for x in rows[s["rid"]] if x["pop"]}
                if 1 in fav:
                    a[4] += pays(R, "ワイド", "-".join(map(str, sorted((s["num"], fav[1])))))
                if 1 in fav and 2 in fav:
                    a[5] += pays(R, "3連複", "-".join(map(str, sorted((s["num"], fav[1], fav[2])))))
            d, t = agg[True], agg[False]
            if d[0] < 150 or t[0] < 80 or d[1] / d[2] < 1.25:
                continue
            L.append(f"| {a1} × {a2} | {d[0]}/{t[0]} | {(d[1]+t[1])/(d[0]+t[0]):.1%} | {d[1]/d[2]:.2f} / {t[1]/t[2]:.2f} | "
                     f"{d[3]/d[0]:.0f}% / {t[3]/t[0]:.0f}% | {d[4]/d[0]:.0f}% / {t[4]/t[0]:.0f}% | {d[5]/d[0]:.0f}% / {t[5]/t[0]:.0f}% |")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
