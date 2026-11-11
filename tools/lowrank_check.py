"""下位人気の区切り（7〜12番人気・3〜10番人気・1〜8番人気など）を外しても成績が保たれるか（2026-11-07, ユーザー指摘
「3番人気までは来る可能性が高いから分かるが、下位人気の区切りには合理的根拠がない」）.
data/cache/flag_backtest_rows.json（フラグ点）と実払戻。評価は的中率と回収率（3期＝2021-23 / 2024 / 2025-26）。
使い方: python3 tools/lowrank_check.py → docs/analysis/lowrank_check.md
"""
import json
import sqlite3
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pays(p, k):
    return {tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split())): it[1] for it in p.get(k) or []}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    info = {r[0]: (r[1], json.loads(r[2])) for r in c.execute("select race_id,race_no,payouts from races where payouts is not null")}
    pn, odds = {}, {}
    for rid, p, n, o in c.execute("select race_id,popularity,number,odds from results where popularity is not null"):
        pn[(rid, p)] = n; odds[(rid, p)] = o
    R = defaultdict(list)
    for r in json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json")):
        R[r["rid"]].append(r)

    def axis_pkg(lo, hi, th, races=None, chaos=False):
        agg = [[0, 0, 0, 0] for _ in range(3)]
        for rid, hs in R.items():
            if rid not in info:
                continue
            rno, p = info[rid]
            if races and rno not in races:
                continue
            if chaos and (odds.get((rid, 1)) or 0) < 4.1:
                continue
            sc = {h["pop"]: h["plus"] - h["minus"] for h in hs}
            cand = [q for q in sc if sc[q] >= th and lo <= q <= hi and (rid, q) in pn]
            if not cand:
                continue
            ax = max(cand, key=lambda q: (sc[q], -q))
            n = lambda q: pn.get((rid, q))
            W, T = pays(p, "ワイド"), pays(p, "3連複")
            wl, tl = ((1, 2, 3), range(1, 6)) if chaos else ((1, 2, 3, 4, 5), range(1, 5))
            tw = {tuple(sorted((n(ax), n(q)))) for q in wl if q != ax and n(q)}
            tt = {tuple(sorted((n(ax), n(x), n(y)))) for x in (1, 2) for y in tl if x != y and ax not in (x, y) and n(x) and n(y)}
            back = sum(W.get(t, 0) for t in tw) + sum(T.get(t, 0) for t in tt)
            a = agg[per(hs[0]["date"])]
            a[0] += 1; a[1] += 100 * (len(tw) + len(tt)); a[2] += back; a[3] += back > 0
        return agg

    def box(hi, th=3, k=4):
        agg = [[0, 0, 0, 0] for _ in range(3)]
        for rid, hs in R.items():
            if rid not in info:
                continue
            p = info[rid][1]
            sc = {h["pop"]: h["plus"] - h["minus"] for h in hs}
            cand = sorted([q for q in sc if sc[q] >= th and q <= hi and (rid, q) in pn], key=lambda q: (-sc[q], q))[:k]
            if len(cand) < k:
                continue
            nums = [pn[(rid, q)] for q in cand]
            W, T = pays(p, "ワイド"), pays(p, "3連複")
            back = sum(W.get(tuple(sorted(x)), 0) for x in combinations(nums, 2)) + sum(T.get(tuple(sorted(x)), 0) for x in combinations(nums, 3))
            a = agg[per(hs[0]["date"])]
            a[0] += 1; a[1] += 1000; a[2] += back; a[3] += back > 0
        return agg

    fmt = lambda agg: (" / ".join(f"{a[3] / a[0]:.0%}" if a[0] else "-" for a in agg) + " | "
                       + " / ".join(f"{a[2] / a[1]:.0%}" if a[1] else "-" for a in agg) + " | " + " / ".join(str(a[0]) for a in agg))
    L = ["# 下位人気の区切りを外すと（tools/lowrank_check.py）", "",
         "的中率 | 回収率 | レース数（3期＝2021-23 / 2024 / 2025-26）。実払戻。", "",
         "| 買い方 | 人気の条件 | 的中率 | 回収率 | レース数 |", "|---|---|---|---|---|"]
    rows = [
        ("◎7・8R（7R・8R、+4以上の軸）", "今: 3〜10番人気", axis_pkg(3, 10, 4, races=(7, 8))),
        ("◎7・8R", "3番人気以下（上限なし）", axis_pkg(3, 18, 4, races=(7, 8))),
        ("◎7・8R", "人気を問わない", axis_pkg(1, 18, 4, races=(7, 8))),
        ("★混戦穴（1番人気4.1倍以上、+3以上の軸）", "今: 7〜12番人気", axis_pkg(7, 12, 3, chaos=True)),
        ("★混戦穴", "7番人気以下（上限なし）", axis_pkg(7, 18, 3, chaos=True)),
        ("★混戦穴", "4番人気以下", axis_pkg(4, 18, 3, chaos=True)),
        ("★混戦穴", "人気を問わない", axis_pkg(1, 18, 3, chaos=True)),
        ("◎拾った馬ボックス（+3以上の上位4頭）", "今: 1〜8番人気", box(8)),
        ("◎拾った馬ボックス", "人気を問わない", box(18)),
    ]
    for name, cond, agg in rows:
        L.append(f"| {name} | {cond} | {fmt(agg)} |")
    (ROOT / "docs" / "analysis" / "lowrank_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
