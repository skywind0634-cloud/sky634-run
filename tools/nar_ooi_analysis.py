"""南関東などの全レース分析（data/nar/<コード>_all_*.jsonl, keiba/nar.py --all が取得）. 使い方: python tools/nar_ooi_analysis.py [コード=20]

1. 概要: 配当・人気別の回収率（クラス・距離・レース番号別）
2. 両期間で100%超の特徴（父・母父・騎手・調教師・前走など）と、ランダムな特徴での偶然の基準
3. 走る条件スコア（JRAの cond_score と同じ考え方）: 前半のデータで「人気帯の平均より3着内に来る条件」を学習し、
   後半で 4〜9番人気 × スコア上位 の単複・馬連の回収率を検証（学習と検証の期間を分けるので漏れなし）
出力: docs/analysis/nar_ooi.md（大井）, nar_<コード>.md（その他）
"""
from __future__ import annotations

import json
import random
import re
import statistics as stt
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nar_final_analysis as A   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPLIT = "2025-04-01"
BABA = sys.argv[1] if len(sys.argv) > 1 else "20"
NAME = {"18": "浦和", "19": "船橋", "20": "大井", "21": "川崎", "31": "高知"}.get(BABA, BABA)


def load():
    rs = []
    for fn in sorted((ROOT / "data/nar").glob(f"{BABA}_all_*.jsonl")):
        rs += A.load(fn)
    seen, out = set(), []
    for r in sorted(rs, key=lambda r: (r["date"], r["race_no"])):
        k = (r["date"], r["race_no"])
        if k not in seen:
            seen.add(k)
            r["half"] = "前半" if r["date"] < SPLIT else "後半"
            out.append(r)
    return out


def cls(r):
    n = r["name"]
    for k in ("重賞", "ＪｐｎＩ", "Jpn", "Ｓ１", "Ｓ２", "Ｓ３"):
        if k in n:
            return "重賞"
    m = re.search(r"([ＡＢＣ])([１２３]|\d)?", n)
    if m:
        return m.group(1).translate(str.maketrans("ＡＢＣ", "ABC"))
    if "２歳" in n or "2歳" in n:
        return "2歳"
    if "３歳" in n or "3歳" in n:
        return "3歳"
    return "その他"


def feats(e, r):
    f = A.feats(e, r)
    f.pop("前走ファイナル", None)
    f["クラス"] = cls(r)
    f["レース番号"] = "1-6R" if r["race_no"] <= 6 else "7-10R" if r["race_no"] <= 10 else "11R以降"
    if e.get("sire"):
        f["父×距離"] = f"{e['sire']}×{'短' if r['distance'] <= 1400 else '中長'}"
        f["父×馬場"] = f"{e['sire']}×{'良' if r.get('going') == '良' else '道悪'}"
    if e.get("jockey") and e.get("trainer"):
        f["騎手×調教師"] = f"{e['jockey']}×{e['trainer']}"
    return f


def band(p):
    return "1-3人気" if p <= 3 else "4-6人気" if p <= 6 else "7-9人気" if p <= 9 else "10人気↓"


def overview(rs, L):
    L += [f"## 概要（{len(rs)}レース, {rs[0]['date']}〜{rs[-1]['date']}, 前半＝{SPLIT}より前）", ""]
    L += ["| 券種 | 中央値 | 上位25% | 上位10% | 1万円以上の割合 |", "|---|--:|--:|--:|--:|"]
    for k, kk in (("単勝", "単勝"), ("馬連", "馬連複"), ("三連複", "三連複"), ("三連単", "三連単")):
        v = [max([y for _, y, _ in r["pay"].get(kk, [])] or [0]) for r in rs if r["pay"].get(kk)]
        L.append(f"| {k} | {stt.median(v):,.0f}円 | {A.pctl(v, .75):,.0f}円 | {A.pctl(v, .9):,.0f}円 | {sum(x >= 10000 for x in v) / len(v):.0%} |")
    L.append("")
    A.section_pop(f"{NAME} 全レース", rs, L)
    for lab, fn in (("クラス", cls), ("距離", lambda r: r["distance"]),
                    ("レース番号", lambda r: "1-6R" if r["race_no"] <= 6 else "7-10R" if r["race_no"] <= 10 else "11R以降")):
        g = defaultdict(list)
        for r in rs:
            g[fn(r)].append(r)
        L += [f"### {lab}別: 1番人気の勝率・馬連と三連単の中央値", "", f"| {lab} | レース | 1番人気勝率 | 馬連 中央値 | 三連単 中央値 | 4-9人気 単回収 | 4-9人気 複回収 |", "|---|--:|--:|--:|--:|--:|--:|"]
        for k, v in sorted(g.items(), key=lambda x: -len(x[1])):
            if len(v) < 30:
                continue
            w1 = sum(1 for r in v for e in r["entries"] if e["pop"] == 1 and e["fin"] == 1) / len(v)
            um = stt.median([max([y for _, y, _ in r["pay"].get("馬連複", [])] or [0]) for r in v])
            t3 = stt.median([max([y for _, y, _ in r["pay"].get("三連単", [])] or [0]) for r in v])
            a = A.Acc()
            for r in v:
                for e in r["entries"]:
                    if 4 <= e["pop"] <= 9:
                        a.add(e, r)
            L.append(f"| {k} | {len(v)} | {w1:.0%} | {um:,.0f}円 | {t3:,.0f}円 | {a.wp / a.n:.0f}% | {a.pp / a.n:.0f}% |")
        L.append("")


def robust(rs, L, min_n=60):
    L += ["## 前半・後半とも回収率100%超の特徴（人気帯別）", ""]
    rows, tested = [], 0
    acc = defaultdict(lambda: {"前半": A.Acc(), "後半": A.Acc()})
    for r in rs:
        for e in r["entries"]:
            b = band(e["pop"])
            for k, v in feats(e, r).items():
                if k != "人気" and v is not None:
                    acc[(b, k, v)][r["half"]].add(e, r)
    for (b, k, v), d in acc.items():
        a, c = d["前半"], d["後半"]
        if a.n < min_n or c.n < min_n * 0.6:
            continue
        for kind, fa, fb in (("単", a.wp / a.n, c.wp / c.n), ("複", a.pp / a.n, c.pp / c.n)):
            tested += 1
            if fa >= 100 and fb >= 100:
                rows.append((b, k, v, kind, a.n, c.n, fa, fb, (a.t3 + c.t3) / (a.n + c.n)))
    # 偶然の基準: 同じ頭数規模のランダムな特徴
    base = []
    for seed in range(10):
        random.seed(seed)
        racc = defaultdict(lambda: {"前半": A.Acc(), "後半": A.Acc()})
        for r in rs:
            for e in r["entries"]:
                for j in range(3):
                    racc[(band(e["pop"]), j, random.randrange(40))][r["half"]].add(e, r)
        t = s = 0
        for d in racc.values():
            a, c = d["前半"], d["後半"]
            if a.n < min_n or c.n < min_n * 0.6:
                continue
            for fa, fb in ((a.wp / a.n, c.wp / c.n), (a.pp / a.n, c.pp / c.n)):
                t += 1
                s += fa >= 100 and fb >= 100
        base.append(s / max(t, 1))
    L.append(f"- 調べた組み合わせ {tested}、両期間100%超 {len(rows)}（{len(rows) / max(tested, 1):.1%}）。"
             f"ランダムな特徴だと {stt.mean(base):.1%} が偶然そうなる（これより大きく多くなければ、全体としては偶然の範囲）。")
    L += ["", "| 人気帯 | 特徴 | 券種 | 頭数 前半/後半 | 回収率 前半/後半 | 3着内率 |", "|---|---|---|--:|--:|--:|"]
    for b, k, v, kind, na, nb, fa, fb, t3 in sorted(rows, key=lambda x: -min(x[6], x[7]) * (x[4] + x[5]) ** .5)[:50]:
        L.append(f"| {b} | {k}＝{v} | {kind} | {na}/{nb} | {fa:.0f}% / {fb:.0f}% | {t3:.0%} |")
    L.append("")


def cond_model(train):
    """前半のデータで: 特徴ごとに 3着内率 − 人気ごとの平均3着内率（頭数で縮める）."""
    base = defaultdict(lambda: [0, 0])
    for r in train:
        for e in r["entries"]:
            b = base[min(e["pop"], 12)]
            b[0] += 1
            b[1] += e["fin"] <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    s = defaultdict(lambda: [0, 0.0])
    for r in train:
        for e in r["entries"]:
            x = (e["fin"] <= 3) - exp[min(e["pop"], 12)]
            for k, v in feats(e, r).items():
                if k in ("人気", "距離", "頭数", "馬場", "季節", "クラス", "レース番号") or v is None:
                    continue
                s[(k, v)][0] += 1
                s[(k, v)][1] += x
    return {kv: (t / n) * n / (n + 40) for kv, (n, t) in s.items() if n >= 15}


def score(m, e, r):
    return sum(m.get((k, v), 0) for k, v in feats(e, r).items())


def cond_test(rs, L):
    train = [r for r in rs if r["half"] == "前半"]
    test = [r for r in rs if r["half"] == "後半"]
    m = cond_model(train)
    L += ["## 走る条件スコア（前半で学習 → 後半で検証）", "",
          "- 特徴（騎手・調教師・父・母父・父×距離・父×馬場・騎手×調教師・前走・間隔・枠・性齢など）ごとに、"
          "前半のデータで「人気ごとの平均より3着内に来た割合」を出し、その合計をスコアにする（JRAの『走る条件』と同じ考え方）。",
          "- 後半は学習に使っていないので、ここでの回収率がそのまま期待できる値に近い。", ""]
    L += ["| 対象（後半） | 頭数 | 勝率 | 3着内率 | 単回収 | 複回収 |", "|---|--:|--:|--:|--:|--:|"]
    out = {}
    for lo, hi in ((4, 9), (4, 6), (7, 9), (10, 99)):
        for th in (0.0, 0.2, 0.4, 0.6):
            a = A.Acc()
            for r in test:
                for e in r["entries"]:
                    if lo <= e["pop"] <= hi and score(m, e, r) >= th:
                        a.add(e, r)
            if a.n >= 30:
                lab = f"{lo}〜{hi if hi < 99 else ''}人気・スコア{th}以上"
                L.append(f"| {lab} | {a.n} | {a.w / a.n:.1%} | {a.t3 / a.n:.1%} | {a.wp / a.n:.0f}% | {a.pp / a.n:.0f}% |")
                out[(lo, hi, th)] = a
    # レースで最上位の1頭（4〜9人気）
    L += ["", "### 各レースで 4〜9人気のスコア最上位の1頭（後半）", "", "| 条件 | レース | 単回収 | 複回収 | 3着内率 | 1人気-その馬 馬連 回収 | その馬から1〜3人気へワイド 回収 |", "|---|--:|--:|--:|--:|--:|--:|"]
    for th in (0.2, 0.4, 0.6):
        for rn in ("全レース", "7R以降"):
            a = A.Acc()
            uc = ub = wc = wb = 0
            for r in test:
                if rn == "7R以降" and r["race_no"] < 7:
                    continue
                c = [(score(m, e, r), e) for e in r["entries"] if 4 <= e["pop"] <= 9]
                if not c:
                    continue
                s, e = max(c, key=lambda x: x[0])
                if s < th:
                    continue
                a.add(e, r)
                P = {x["pop"]: x["num"] for x in r["entries"]}
                if 1 in P:
                    uc += 100
                    ub += A.pay(r, "馬連", (P[1], e["num"]))
                for p in (1, 2, 3):
                    if p in P:
                        wc += 100
                        wb += A.pay(r, "ワイド", (P[p], e["num"]))
            if a.n >= 30:
                L.append(f"| スコア{th}以上・{rn} | {a.n} | {a.wp / a.n:.0f}% | {a.pp / a.n:.0f}% | {a.t3 / a.n:.0%} | "
                         f"{ub / max(uc, 1):.0%} | {wb / max(wc, 1):.0%} |")
    L.append("")
    # 強い条件の上位
    top = sorted(((v, k) for k, v in m.items()), reverse=True)[:25]
    L += ["### 前半で強かった条件（スコアへの寄与が大きい順）", "", "- " + "、".join(f"{k}＝{v}({s:+.2f})" for s, (k, v) in top), ""]
    return m


def holdout(rs, L, cut="2026-01-01"):
    """最後の確認: 2025年までで学習・候補を決め、2026年（一度も見ていない期間）で試す."""
    tr = [r for r in rs if r["date"] < cut]
    te = [r for r in rs if r["date"] >= cut]
    if not te:
        return
    m = cond_model(tr)
    L += [f"## 最後の確認: {cut}より前で学習 → それ以降（{len(te)}レース）で検証", "",
          "| 対象 | 頭数 | 勝ち | 単回収 | 上位2本を除く単回収 | 複回収 | 3着内率 |", "|---|--:|--:|--:|--:|--:|--:|"]

    def row(lab, pick):
        n = pp = t3 = 0
        wins = []
        for r in te:
            for e in r["entries"]:
                if pick(e, r):
                    n += 1
                    t3 += e["fin"] <= 3
                    pp += A.pay(r, "複勝", (e["num"],))
                    w = A.pay(r, "単勝", (e["num"],))
                    if w:
                        wins.append(w)
        if n:
            wins.sort(reverse=True)
            L.append(f"| {lab} | {n} | {len(wins)} | {sum(wins) / n:.0f}% | {sum(wins[2:]) / n:.0f}% | {pp / n:.0f}% | {t3 / n:.0%} |")
    for th in (0.1, 0.2):
        row(f"4〜9人気・スコア{th}以上", lambda e, r, th=th: 4 <= e["pop"] <= 9 and score(m, e, r) >= th)
    row("4〜6人気・父パイロ", lambda e, r: 4 <= e["pop"] <= 6 and e.get("sire") == "パイロ")
    row("4〜6人気・父シニスターミニスター", lambda e, r: 4 <= e["pop"] <= 6 and e.get("sire") == "シニスターミニスター")
    row("4〜6人気・休み明け（最終レース）", lambda e, r: r.get("final") and 4 <= e["pop"] <= 6 and A.feats(e, r).get("間隔") == "休み明け")
    c = b = hit = n = 0
    for r in te:
        if not r.get("final"):
            continue
        P = {e["pop"]: e["num"] for e in r["entries"]}
        if 1 not in P:
            continue
        T = [(P[1], P[i]) for i in range(4, 10) if i in P]
        c += 100 * len(T)
        bb = sum(A.pay(r, "馬連", t) for t in T)
        b += bb
        hit += bb > 0
        n += 1
    if n:
        L.append(f"\n- 最終レースの 馬連 1人気-4〜9人気: {n}レース・回収率 {b / c:.0%}・的中率 {hit / n:.0%}")
    L.append("")


def pop_strats(rs, L):
    L += ["## 人気順で組む買い方（全レース・7R以降）", "", "| 買い方 | 対象 | 前半 | 後半 | 的中率 |", "|---|---|--:|--:|--:|"]
    sel = lambda P, a, b: [P[i] for i in range(a, b + 1) if i in P]   # noqa: E731
    S = {"馬連 1人気-4〜9人気": lambda P: [("馬連", (P[1], x)) for x in sel(P, 4, 9)] if 1 in P else [],
         "馬連 1人気-2〜6人気": lambda P: [("馬連", (P[1], x)) for x in sel(P, 2, 6)] if 1 in P else [],
         "三連複 1人気-4〜9人気": lambda P: [("三連複", (P[1], *c)) for c in combinations(sel(P, 4, 9), 2)] if 1 in P else [],
         "ワイド 1人気-4〜9人気": lambda P: [("ワイド", (P[1], x)) for x in sel(P, 4, 9)] if 1 in P else []}
    for name, f in S.items():
        for tgt in ("全レース", "7R以降", "12頭以上"):
            res, hit, n = {}, 0, 0
            for h in ("前半", "後半"):
                c = b = 0
                for r in rs:
                    if r["half"] != h or (tgt == "7R以降" and r["race_no"] < 7) or (tgt == "12頭以上" and r["n_runners"] < 12):
                        continue
                    T = f({e["pop"]: e["num"] for e in r["entries"]})
                    if not T:
                        continue
                    c += 100 * len(T)
                    bb = sum(A.pay(r, k, x) for k, x in T)
                    b += bb
                    hit += bb > 0
                    n += 1
                res[h] = b / c if c else 0
            L.append(f"| {name} | {tgt} | {res['前半']:.0%} | {res['後半']:.0%} | {hit / max(n, 1):.0%} |")
    L.append("")


def main():
    rs = load()
    L = [f"# {NAME} 全レースの分析（自動生成, tools/nar_ooi_analysis.py {BABA}）", "",
         "- データ: keiba.go.jp の成績表・出馬表（`keiba/nar.py --all`）。払戻はすべて実際の値、人気は確定人気。", ""]
    overview(rs, L)
    pop_strats(rs, L)
    robust(rs, L)
    cond_test(rs, L)
    holdout(rs, L)
    out = ROOT / "docs/analysis" / ("nar_ooi.md" if BABA == "20" else f"nar_{BABA}.md")
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out, len(rs))


if __name__ == "__main__":
    main()
