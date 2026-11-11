"""拾った馬（フラグ点の上位）の中で「軸を置かずボックス」で買うと、1頭軸の流しより儲かるか（2026-11-01, ユーザー「馬は拾えているのに当たらない」）.
11/1 天皇賞(秋)で候補5頭のうち3頭で決まった（3連複42,010円）のに、7を軸に固定して外した反省。

各レースで、フラグ点が th 以上の馬をフラグ点の高い順に最大 K 頭（人気の条件は付けない／付ける場合あり）選び、
3連複ボックス・ワイドボックスの回収率と的中率を 2021-23 / 2024 / 2025-26 で出す（data/cache/flag_backtest_rows.json, 実際の払戻）。
比較: 今の ◎フラグ点+5（軸1頭 → ワイド1〜5番人気＋3連複 軸−1〜2−1〜4）。
使い方: python3 tools/box_check.py → docs/analysis/box_check.md
"""
import json
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pays(p, k):
    return {tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split())): it[1] for it in p.get(k) or []}


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    info = {r[0]: (r[1], json.loads(r[2])) for r in c.execute("select race_id,race_no,payouts from races where payouts is not null")}
    pn = {(r[0], r[1]): r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
    R = defaultdict(list)
    for r in json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json")):
        R[r["rid"]].append(r)
    # (名前, 最低フラグ点, 頭数K, 人気の下限, 人気の上限, 券種) — 候補が K 頭そろうレースだけ買う
    PLANS = []
    for th in (2, 3, 4):
        for K in (4, 5):
            for lo, hi, lab in ((1, 18, "人気を問わず"), (1, 8, "1〜8番人気"), (2, 18, "1番人気を除く")):
                PLANS.append((f"フラグ点+{th}以上の上位{K}頭・{lab}", th, K, lo, hi))
    agg = defaultdict(lambda: [[0, 0, 0, 0] for _ in range(3)])  # races, cost, back, hit
    days = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for rid, hs in R.items():
        if rid not in info:
            continue
        rno, p = info[rid]; d = hs[0]["date"]
        W, T = pays(p, "ワイド"), pays(p, "3連複")
        sc = {h["pop"]: h["plus"] - h["minus"] for h in hs}
        n = lambda q: pn.get((rid, q))
        for name, th, K, lo, hi in PLANS:
            cand = sorted([q for q in sc if sc[q] >= th and lo <= q <= hi and n(q)], key=lambda q: (-sc[q], q))[:K]
            if len(cand) < K:
                continue
            nums = [n(q) for q in cand]
            for kind, Pd, size in (("3連複ボックス", T, 3), ("ワイドボックス", W, 2), ("3連複＋ワイド", None, 0)):
                if kind == "3連複＋ワイド":
                    tk = [(T, tuple(sorted(x))) for x in combinations(nums, 3)] + [(W, tuple(sorted(x))) for x in combinations(nums, 2)]
                else:
                    tk = [(Pd, tuple(sorted(x))) for x in combinations(nums, size)]
                back = sum(P.get(t, 0) for P, t in tk); cost = 100 * len(tk)
                x = agg[(name, kind)][per(d)]
                x[0] += 1; x[1] += cost; x[2] += back; x[3] += back > 0
                if per(d) == 2:
                    y = days[(name, kind)][d]; y[0] += cost; y[1] += back
    L = ["# 拾った馬のボックス買い（tools/box_check.py）", "",
         "フラグ点の上位K頭（候補がK頭そろうレースだけ）を軸なしのボックスで買う。実際の払戻。3期＝2021-23 / 2024 / 2025-26。"
         "日別プラス＝2025-26で買った日のうち、その日のこの買い方だけの収支がプラスの日の割合。", "",
         "| 候補 | 券種 | 1レースの点数 | 回収率（3期） | 的中率（3期） | 日別プラス | レース数（3期） |", "|---|---|---|---|---|---|---|"]
    for name, *_ in PLANS:
        for kind in ("3連複ボックス", "ワイドボックス", "3連複＋ワイド"):
            x = agg[(name, kind)]
            if not sum(v[0] for v in x):
                continue
            pts = sum(v[1] for v in x) / 100 / sum(v[0] for v in x)
            ds = list(days[(name, kind)].values())
            plus = f"{sum(v[1] > v[0] for v in ds) / len(ds):.0%}" if ds else "-"
            L.append(f"| {name} | {kind} | {pts:.0f} | " + " / ".join(f"{v[2] / v[1]:.0%}" if v[1] else "-" for v in x)
                     + " | " + " / ".join(f"{v[3] / v[0]:.0%}" if v[0] else "-" for v in x) + f" | {plus} | " + " / ".join(str(v[0]) for v in x) + " |")
    (ROOT / "docs" / "analysis" / "box_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
