"""紐（相手）の人気の幅を変えると、的中率・回収率はどうなるか（2026-10-27, ユーザー指示「人気馬は3連複・ワイドの紐として拾うべきでは。的中率を調べろ」）.

軸は本番と同じ: ◎フラグ点+5（3番人気以下・フラグ点+5以上の上位1頭）／★フラグ軸（3番人気以下・+4以上）。
紐の取り方を変えて、ワイド・3連複の回収率と的中レース率（1点でも当たったレースの割合）を 2021-23 / 2024 / 2025-26 で比べる。
（data/cache/flag_backtest_rows.json の5年分のフラグ点, 実際の払戻）
使い方: python3 tools/himo_width_check.py → docs/analysis/himo_width_check.md
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


# 紐の取り方: (名前, ワイドの相手の人気, 3連複の組み方)
#   3連複 ("2nd", A, B) = 軸−A（2列目）−B（3列目）, ("box", B) = 軸−B から2頭
PLANS = [
    ("今の形: ワイド1〜3／3連複 軸−1〜2−1〜5", range(1, 4), ("2nd", (1, 2), range(1, 6))),
    ("ワイド1〜5／3連複 軸−1〜2−1〜5", range(1, 6), ("2nd", (1, 2), range(1, 6))),
    ("ワイド1〜3／3連複 軸−1〜3−1〜6", range(1, 4), ("2nd", (1, 2, 3), range(1, 7))),
    ("ワイド1〜3／3連複 軸−1〜2−1〜8", range(1, 4), ("2nd", (1, 2), range(1, 9))),
    ("ワイド1〜3／3連複 軸−1〜5の2頭（10点）", range(1, 4), ("box", range(1, 6))),
    ("ワイド1〜5／3連複 軸−1〜5の2頭（10点）", range(1, 6), ("box", range(1, 6))),
    ("ワイド1〜3／3連複 軸−1〜3−1〜3（3点）", range(1, 4), ("box", range(1, 4))),
    ("ワイド1〜3だけ（3連複なし）", range(1, 4), None),
    ("ワイド1〜4だけ（3連複なし）", range(1, 5), None),
    ("ワイド1〜5だけ（3連複なし）", range(1, 6), None),
    ("ワイド1〜6だけ（3連複なし）", range(1, 7), None),
    ("ワイド1〜5／3連複 軸−1〜2−1〜4（10点以内）", range(1, 6), ("2nd", (1, 2), range(1, 5))),
    ("ワイド1〜4／3連複 軸−1〜2−1〜5（10点以内）", range(1, 5), ("2nd", (1, 2), range(1, 6))),
    ("ワイド1〜6／3連複 軸−1〜2−1〜3（10点以内）", range(1, 7), ("2nd", (1, 2), range(1, 4))),
    ("ワイド1〜5／3連複 軸−1〜3−1〜4（10点以内）", range(1, 6), ("box", range(1, 5))),
]


def tickets(ax, n, wide, trio):
    tk = [("W", tuple(sorted((n(ax), n(x))))) for x in wide if x != ax and n(x)]
    if trio:
        if trio[0] == "2nd":
            pairs = {tuple(sorted((x, y))) for x in trio[1] for y in trio[2] if x != y}
        else:
            pairs = set(combinations(trio[1], 2))
        tk += list({("T", tuple(sorted((n(ax), n(x), n(y))))) for x, y in pairs if ax not in (x, y) and n(x) and n(y)})
    return tk


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    info = {r[0]: (r[1], json.loads(r[2])) for r in c.execute("select race_id,race_no,payouts from races where payouts is not null")}
    pn = {(r[0], r[1]): r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
    fav = {r[0]: r[1] for r in c.execute("select race_id,odds from results where popularity=1")}
    R = defaultdict(list)
    for r in json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json")):
        R[r["rid"]].append(r)
    AXES = {"◎フラグ点+5（3番人気以下）": (5, 18, False), "★フラグ軸（3番人気以下・+4以上）": (4, 18, False),
            "◎7・8R（3〜10番人気・+4以上, 7R・8Rだけ）": (4, 10, True),
            "★混戦穴（1番人気4.1倍以上・7〜12番人気・+3以上）": (3, 12, "chaos")}
    agg = defaultdict(lambda: [[0, 0, 0, 0] for _ in range(3)])   # races, cost, back, hit races
    day = defaultdict(lambda: [0, 0])
    for rid, hs in R.items():
        if rid not in info:
            continue
        rno, p = info[rid]; d = hs[0]["date"]
        W, T = pays(p, "ワイド"), pays(p, "3連複")
        sc = {h["pop"]: h["plus"] - h["minus"] for h in hs}
        n = lambda q, rid=rid: pn.get((rid, q))
        for an, (th, hi, only78) in AXES.items():
            if only78 is True and rno not in (7, 8):
                continue
            if only78 == "chaos" and not (fav.get(rid) or 0) >= 4.1:
                continue
            cand = [q for q in sc if sc[q] >= th and (7 if only78 == "chaos" else 3) <= q <= hi]
            if not cand:
                continue
            ax = sorted(cand, key=lambda q: (-sc[q], q))[0]
            for pl, wide, trio in PLANS:
                tk = tickets(ax, n, wide, trio)
                back = sum((W if k == "W" else T).get(t, 0) for k, t in tk); cost = 100 * len(tk)
                for scope in (("全レース", "7R・8R") if rno in (7, 8) else ("全レース",)):
                    x = agg[(an, scope, pl)][per(d)]
                    x[0] += 1; x[1] += cost; x[2] += back; x[3] += back > 0
                if per(d) == 2:
                    y = day[(an, pl, d)]; y[0] += cost; y[1] += back
    L = ["# 紐（相手）の人気の幅と、的中率・回収率（tools/himo_width_check.py）", "",
         "軸は本番と同じフラグ点の上位1頭（3番人気以下）。実際の払戻。3期＝2021-23 / 2024 / 2025-26。的中＝そのレースで1点でも当たった割合。日別プラス＝2025-26 で軸のあった日のうち、その日の収支がプラスの日の割合。", ""]
    for an in AXES:
        for scope in ("全レース", "7R・8R"):
            L += [f"## {an}・{scope}", "", "| 紐の取り方 | 1レースの点数 | 回収率（3期） | 的中率（3期） | 日別プラス(2025-26) | レース数 |", "|---|---|---|---|---|---|"]
            for pl, _, _ in PLANS:
                x = agg[(an, scope, pl)]
                if not sum(v[0] for v in x):
                    continue
                pts = sum(v[1] for v in x) / 100 / sum(v[0] for v in x)
                roi = " / ".join(f"{v[2] / v[1]:.0%}" if v[1] else "-" for v in x)
                hit = " / ".join(f"{v[3] / v[0]:.0%}" if v[0] else "-" for v in x)
                ds = [v for k, v in day.items() if k[0] == an and k[1] == pl]
                plus = f"{sum(v[1] > v[0] for v in ds) / len(ds):.0%}" if ds and scope == "全レース" else "-"
                L.append(f"| {pl} | {pts:.1f} | {roi} | {hit} | {plus} | {sum(v[0] for v in x)} |")
            L.append("")
    (ROOT / "docs" / "analysis" / "himo_width_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
