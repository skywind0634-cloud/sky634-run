"""新馬戦の分析（data/debut.db: tools/debut_import.py が取り込み。血統・兄姉は data/keiba.db も参照）.

1. 人気別の勝率・3着内率・単勝回収率（新馬戦は単勝オッズが勝ち馬分だけ取れるので、単勝回収率は正確に出る）
2. 特徴（父・父×芝ダ・父×距離・母父・父系統・騎手・調教師・兄姉の成績・枠・頭数・競馬場…）ごとに、
   人気から見込む3着内数との比（A/E）と単勝回収率を、前半・後半の2期間で出し、両期間で人気以上が続くものを残す。
   ランダムな特徴でも同じ数を数えて、偶然でどれくらい残るかの基準を出す。
3. 新馬スコア: 前半で学習した「人気以上に走る条件」の合計点で、後半の4〜9番人気・10番人気以下の単勝回収率を検証。
出力: docs/analysis/debut.md、data/knowledge/debut_model.json（予想で使う学習結果）
"""
from __future__ import annotations

import collections
import json
import random
import sqlite3
import statistics as stt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEBUT = Path(__import__("os").environ.get("DEBUT_DB", ROOT / "data/debut.db"))
MAIN = ROOT / "data/keiba.db"
SPLIT = "2025-04-01"
PRIOR = 30          # 縮小の強さ（頭数がこれくらいあると半分信じる）


def dband(d):
    return "〜1400" if d <= 1400 else "1500-1800" if d <= 1800 else "2000〜"


def load():
    c = sqlite3.connect(str(DEBUT))
    c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT ra.race_id, ra.date, ra.course, ra.surface, ra.distance, ra.n_runners, ra.going,
        r.horse_id, r.finish, r.popularity, r.odds, r.gate, r.number, r.sex, r.jockey, r.trainer, r.weight_carried, r.body_weight,
        h.name, h.sire, h.dam, h.damsire, h.sire_line, h.damsire_line, h.family
        FROM results r JOIN races ra USING(race_id) LEFT JOIN horses h USING(horse_id)
        WHERE ra.grade='新馬' AND r.finish IS NOT NULL AND r.popularity IS NOT NULL ORDER BY ra.date""").fetchall()
    return [dict(r) for r in rows]


def sibling_index():
    """母ごとの産駒の出走（日付・着順・クラス）。新馬戦（debut.db）と7R以降（keiba.db）の両方。"""
    idx = collections.defaultdict(list)
    for p, q in ((DEBUT, "SELECT h.dam, ra.date, r.finish, r.horse_id, ra.grade FROM results r JOIN races ra USING(race_id) JOIN horses h USING(horse_id) WHERE r.finish IS NOT NULL"),
                 (MAIN, "SELECT h.dam, ra.date, r.finish, r.horse_id, ra.grade FROM results r JOIN races ra USING(race_id) JOIN horses h USING(horse_id) WHERE r.finish IS NOT NULL")):
        if not Path(p).exists():
            continue
        c = sqlite3.connect(str(p))
        for dam, date, fin, hid, grade in c.execute(q):
            if dam:
                idx[dam].append((date, fin, hid, grade))
    return idx


def sib_feature(sib, row):
    """レース日より前の兄姉の成績だけを使う（未来の情報を混ぜない）。"""
    past = [(d, f, h, g) for d, f, h, g in sib.get(row["dam"], []) if d < row["date"] and h != row["horse_id"]]
    if not past:
        return "DBに兄姉の記録なし"
    debut = [f for d, f, h, g in past if g == "新馬"]
    upper = [h for d, f, h, g in past if g and g not in ("新馬",)]   # 7R以降（1勝クラス以上）を走った兄姉がいる＝勝ち上がり
    if upper:
        return "兄姉に勝ち上がり馬あり"
    if debut and min(debut) <= 3:
        return "兄姉が新馬戦で3着内"
    return "兄姉は走っているが勝ち上がりなし"


def feats(r, sib):
    sf = r["surface"]
    f = {
        "父": r["sire"], "父×芝ダ": f"{r['sire']}×{sf}", "父×距離": f"{r['sire']}×{sf}{dband(r['distance'])}",
        "母父": r["damsire"], "母父×芝ダ": f"{r['damsire']}×{sf}",
        "父系統×芝ダ": f"{r['sire_line']}×{sf}", "母父系統×芝ダ": f"{r['damsire_line']}×{sf}",
        "騎手": r["jockey"], "調教師": r["trainer"], "調教師×芝ダ": f"{r['trainer']}×{sf}",
        "兄姉": sib_feature(sib, r), "性": r["sex"],
        "枠": "内(1-2)" if (r["gate"] or 0) <= 2 else "外(7-8)" if (r["gate"] or 0) >= 7 else "中(3-6)",
        "競馬場×芝ダ": f"{r['course']}{sf}", "距離": f"{sf}{dband(r['distance'])}",
        "牝系": r["family"],
        # 初戦から走れるか（仕上がり）の手がかり
        "騎手×調教師": f"{r['jockey']}×{r['trainer']}",
        "減量騎手": "減量騎手" if r.get("weight_carried") and r["weight_carried"] < (55 if r["sex"] == "牝" else 57) - 0.5 else None,
        "馬体重": None if not r.get("body_weight") else "〜439kg" if r["body_weight"] < 440 else "440-479kg" if r["body_weight"] < 480 else "480kg〜",
    }
    return {k: v for k, v in f.items() if v and "None" not in str(v)}


class Acc:
    __slots__ = ("n", "t3", "w", "et3", "ew", "ret")

    def __init__(self):
        self.n = self.t3 = self.w = 0
        self.et3 = self.ew = self.ret = 0.0

    def add(self, r, exp):
        self.n += 1
        self.t3 += r["finish"] <= 3
        self.w += r["finish"] == 1
        e3, ew = exp[min(r["popularity"], 12)]
        self.et3 += e3
        self.ew += ew
        if r["finish"] == 1 and r["odds"]:
            self.ret += r["odds"] * 100


def pop_table(rows):
    b = collections.defaultdict(Acc)
    tmp = collections.defaultdict(lambda: [0, 0, 0])
    for r in rows:
        x = tmp[min(r["popularity"], 12)]
        x[0] += 1
        x[1] += r["finish"] <= 3
        x[2] += r["finish"] == 1
    exp = {k: (v[1] / v[0], v[2] / v[0]) for k, v in tmp.items()}
    for r in rows:
        b[min(r["popularity"], 10)].add(r, exp)
    return exp, b


def main():
    rows = load()
    if not rows:
        print("データなし")
        return
    sib = sibling_index()
    exp, popb = pop_table(rows)
    for r in rows:
        r["_f"] = feats(r, sib)
        r["_h"] = "前半" if r["date"] < SPLIT else "後半"
    races = {r["race_id"] for r in rows}
    L = ["# 新馬戦の分析（自動生成, tools/debut_analysis.py）", "",
         f"- データ: JRA公式の新馬戦 {len(races)} レース・{len(rows)} 頭（{rows[0]['date']}〜{rows[-1]['date']}）。前半＝{SPLIT}より前。",
         "- A/E＝3着内の実数÷人気から見込む数（1.00が人気どおり）。単勝回収率は勝ち馬の単勝オッズから計算。", ""]
    L += ["## 人気別", "", "| 人気 | 頭数 | 勝率 | 3着内率 | 単勝回収率 |", "|---|--:|--:|--:|--:|"]
    for p in sorted(popb):
        a = popb[p]
        L.append(f"| {p if p < 10 else '10↓'} | {a.n} | {a.w / a.n:.1%} | {a.t3 / a.n:.1%} | {a.ret / a.n:.0f}% |")
    L.append("")

    # 特徴ごと・期間ごと
    acc = collections.defaultdict(lambda: {"前半": Acc(), "後半": Acc()})
    for r in rows:
        for k, v in r["_f"].items():
            acc[(k, v)][r["_h"]].add(r, exp)
    min_n = max(20, len(rows) // 1500)
    keep, tested = [], 0
    for (k, v), d in acc.items():
        a, b = d["前半"], d["後半"]
        if a.n < min_n or b.n < min_n * 0.6:
            continue
        tested += 1
        ae_a, ae_b = a.t3 / a.et3 if a.et3 else 0, b.t3 / b.et3 if b.et3 else 0
        if ae_a >= 1.15 and ae_b >= 1.15:
            keep.append((k, v, a, b, ae_a, ae_b))
    # 偶然の基準
    base = []
    for seed in range(5):
        random.seed(seed)
        racc = collections.defaultdict(lambda: {"前半": Acc(), "後半": Acc()})
        for r in rows:
            for j in range(4):
                racc[(j, random.randrange(max(10, len(rows) // 300)))][r["_h"]].add(r, exp)
        t = s = 0
        for d in racc.values():
            a, b = d["前半"], d["後半"]
            if a.n < min_n or b.n < min_n * 0.6:
                continue
            t += 1
            s += a.t3 / a.et3 >= 1.15 and b.t3 / b.et3 >= 1.15
        base.append(s / max(t, 1))
    L += ["## 前半・後半とも人気以上に3着内に来る特徴（A/E 1.15以上が両期間）", "",
          f"- 調べた特徴 {tested}、残った {len(keep)}（{len(keep) / max(tested, 1):.1%}）。同じ規模のランダムな特徴だと {stt.mean(base):.1%} が偶然残る。", "",
          "| 特徴 | 頭数 前/後 | A/E 前/後 | 3着内率 | 単勝回収率 前/後 |", "|---|--:|--:|--:|--:|"]
    for k, v, a, b, x, y in sorted(keep, key=lambda t: -min(t[4], t[5]) * (t[2].n + t[3].n) ** .5)[:60]:
        L.append(f"| {k}＝{v} | {a.n}/{b.n} | {x:.2f} / {y:.2f} | {(a.t3 + b.t3) / (a.n + b.n):.0%} | {a.ret / a.n:.0f}% / {b.ret / b.n:.0f}% |")
    L.append("")
    # 兄姉の効き方（全体）
    L += ["## 兄姉の成績と新馬戦", "", "| 兄姉 | 頭数 | 3着内率 | A/E | 単勝回収率 |", "|---|--:|--:|--:|--:|"]
    g = collections.defaultdict(Acc)
    for r in rows:
        g[r["_f"].get("兄姉")].add(r, exp)
    for k, a in sorted(g.items(), key=lambda x: -x[1].n):
        L.append(f"| {k} | {a.n} | {a.t3 / a.n:.1%} | {a.t3 / a.et3:.2f} | {a.ret / a.n:.0f}% |")
    L.append("")

    # 初戦から走るか: 父・厩舎ごとに「新馬戦の3着内 A/E」と「のちの勝ち上がり率」を並べる
    won = set()
    if MAIN.exists():
        won = {h for (h,) in sqlite3.connect(str(MAIN)).execute("SELECT DISTINCT horse_id FROM results")}   # 7R以降（1勝クラス以上）を走った＝勝ち上がった馬
    debut_won = {r["horse_id"] for r in rows if r["finish"] == 1}
    for key, lab in (("sire", "父"), ("trainer", "調教師")):
        g = collections.defaultdict(lambda: [Acc(), set(), set()])
        for r in rows:
            x = g[r[key]]
            x[0].add(r, exp)
            x[1].add(r["horse_id"])
            if r["horse_id"] in won or r["horse_id"] in debut_won:
                x[2].add(r["horse_id"])
        items = [(k, a, len(hs), len(w)) for k, (a, hs, w) in g.items() if k and a.n >= 40]
        if not items:
            continue
        L += [f"## 初戦から走る{lab}・叩いて良くなる{lab}（新馬戦のA/E と、のちに勝ち上がった割合）", "",
              "- 新馬戦のA/Eが高い＝初戦から人気以上に走る。勝ち上がり率が高いのに新馬戦A/Eが低い＝叩いて良くなる（初戦は割引、2戦目以降に狙う）。", "",
              f"| {lab} | 新馬戦の頭数 | 3着内率 | 新馬戦A/E | 新馬単勝回収率 | 勝ち上がり率 | 型 |", "|---|--:|--:|--:|--:|--:|---|"]
        avg_up = stt.mean(w / n for _, _, n, w in items)
        for k, a, n, w in sorted(items, key=lambda t: -(t[1].t3 / t[1].et3)):
            ae = a.t3 / a.et3
            typ = "初戦から走る" if ae >= 1.15 else ("叩き良化" if ae <= 0.85 and w / n >= avg_up else "")
            L.append(f"| {k} | {a.n} | {a.t3 / a.n:.0%} | {ae:.2f} | {a.ret / a.n:.0f}% | {w / n:.0%} | {typ} |")
        L.append("")

    # 新馬スコア（前半で学習 → 後半で検証）, 最後に全期間で学習して保存
    def learn(train):
        s = collections.defaultdict(lambda: [0, 0.0])
        for r in train:
            x = (r["finish"] <= 3) - exp[min(r["popularity"], 12)][0]
            for kv in r["_f"].items():
                s[kv][0] += 1
                s[kv][1] += x
        return {kv: (t / n) * n / (n + PRIOR) for kv, (n, t) in s.items() if n >= 8}

    def score(m, r):
        return sum(m.get(kv, 0) for kv in r["_f"].items())

    m = learn([r for r in rows if r["_h"] == "前半"])
    test = [r for r in rows if r["_h"] == "後半"]
    L += ["## 新馬スコア（前半で学習 → 後半で検証）", "",
          "| 対象（後半） | 頭数 | 勝率 | 3着内率 | A/E | 単勝回収率 |", "|---|--:|--:|--:|--:|--:|"]
    for lo, hi in ((1, 3), (4, 9), (10, 99)):
        for th in (0.0, 0.15, 0.3, 0.5):
            a = Acc()
            for r in test:
                if lo <= r["popularity"] <= hi and score(m, r) >= th:
                    a.add(r, exp)
            if a.n >= 20:
                L.append(f"| {lo}〜{hi if hi < 99 else ''}人気・スコア{th}以上 | {a.n} | {a.w / a.n:.1%} | {a.t3 / a.n:.1%} | {a.t3 / a.et3:.2f} | {a.ret / a.n:.0f}% |")
    # 各レースで4〜9人気のスコア最上位1頭
    by = collections.defaultdict(list)
    for r in test:
        by[r["race_id"]].append(r)
    for th in (0.15, 0.3):
        a = Acc()
        for rid, rs in by.items():
            c = [(score(m, r), r) for r in rs if 4 <= r["popularity"] <= 9]
            if c:
                s, r = max(c, key=lambda x: x[0])
                if s >= th:
                    a.add(r, exp)
        if a.n:
            L.append(f"| 各レースの4〜9人気でスコア最上位・{th}以上 | {a.n} | {a.w / a.n:.1%} | {a.t3 / a.n:.1%} | {a.t3 / a.et3:.2f} | {a.ret / a.n:.0f}% |")
    L.append("")
    full = learn(rows)
    out = ROOT / "data/knowledge/debut_model.json"
    out.write_text(json.dumps({"exp_top3_by_pop": {str(k): v[0] for k, v in exp.items()},
                               "weights": {f"{k}|{v}": round(w, 4) for (k, v), w in full.items() if abs(w) >= 0.02},
                               "n_races": len(races), "period": [rows[0]["date"], rows[-1]["date"]]},
                              ensure_ascii=False, indent=0), encoding="utf-8")
    (ROOT / "docs/analysis/debut.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("docs/analysis/debut.md", len(races), "races")


if __name__ == "__main__":
    main()
