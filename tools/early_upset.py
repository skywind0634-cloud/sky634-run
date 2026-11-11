"""7R・8Rの荒れるレースで高配当を取る買い方（2026-10-24, ユーザー「7R・8Rはきわめて大事。荒れたレースほど取れないと意味ない」）.
レースの形（1番人気の単勝オッズ）で分け、フラグ点の高い人気薄を軸にしたワイド・3連複の回収率・的中率・払戻の中央値を、7R・8Rだけで 2021-23 / 2024 / 2025-26 に出す。
フラグは data/cache/flag_backtest_rows.json、払戻は races.payouts（実払戻）。
使い方: python3 tools/early_upset.py → docs/analysis/early_upset.md
"""
import json, sqlite3, statistics
from collections import defaultdict
from itertools import combinations
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pays(p, k):
    o = {}
    for it in p.get(k) or []:
        o[tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split()))] = it[1]
    return o


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    info = {r[0]: (r[1], json.loads(r[2])) for r in c.execute("select race_id,race_no,payouts from races where payouts is not null")}
    num = {(r[0], r[1]): r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
    fo = {r[0]: r[1] or 0 for r in c.execute("select race_id,odds from results where popularity=1")}
    R = defaultdict(list)
    for r in json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json")):
        R[r["rid"]].append(r)
    agg = defaultdict(lambda: [[0, 0, 0, 0, []] for _ in range(3)])  # races, cost, back, hit races, pays
    for rid, hs in R.items():
        if rid not in info or info[rid][0] not in (7, 8):
            continue
        p = info[rid][1]; d = hs[0]["date"]; o = fo.get(rid, 0)
        W, T = pays(p, "ワイド"), pays(p, "3連複")
        sc = {h["pop"]: h["plus"] - h["minus"] for h in hs}
        n = lambda q: num.get((rid, q))
        shapes = [("全部", True), ("1人気2.6倍以上", o > 2.5), ("1人気3.1倍以上", o > 3.0), ("1人気4.1倍以上", o > 4.0)]
        for th in (2, 3, 4):
            for band in ((4, 9), (7, 12), (4, 12)):
                ax = sorted([q for q in sc if band[0] <= q <= band[1] and sc[q] >= th], key=lambda q: -sc[q])[:2]
                if not ax:
                    continue
                forms = {
                    "ワイド 軸→1〜4人気": [("W", tuple(sorted((n(a), n(b))))) for a in ax for b in (1, 2, 3, 4) if n(a) and n(b)],
                    "3連複 軸-1〜3人気-1〜5人気": list({("T", tuple(sorted((n(a), n(x), n(y))))) for a in ax for x in (1, 2, 3) for y in range(1, 6)
                                                    if x < y and n(a) and n(x) and n(y) and len({a, x, y}) == 3}),
                    "3連複 軸-1〜2人気-1〜6人気": list({("T", tuple(sorted((n(a), n(x), n(y))))) for a in ax for x in (1, 2) for y in range(1, 7)
                                                    if x < y and n(a) and n(x) and n(y) and len({a, x, y}) == 3}),
                    "ワイド＋3連複(軸-1〜2人気-1〜5人気)": [("W", tuple(sorted((n(a), n(b))))) for a in ax for b in (1, 2, 3) if n(a) and n(b)]
                    + list({("T", tuple(sorted((n(a), n(x), n(y))))) for a in ax for x in (1, 2) for y in range(1, 6) if x < y and n(a) and n(x) and n(y) and len({a, x, y}) == 3}),
                }
                for fn, T_ in forms.items():
                    if not T_:
                        continue
                    back = sum((W if k == "W" else T).get(t, 0) for k, t in T_); cost = 100 * len(T_)
                    for sn, ok in shapes:
                        if not ok:
                            continue
                        x = agg[(fn, f"{band[0]}-{band[1]}人気・点+{th}以上", sn)][per(d)]
                        x[0] += 1; x[1] += cost; x[2] += back
                        if back:
                            x[3] += 1; x[4].append(back)
    rows = []
    for k, cs in agg.items():
        if min(x[0] for x in cs) < 25:
            continue
        roi = [x[2] / x[1] for x in cs]
        rows.append((min(roi), k, cs, roi))
    L = ["# 7R・8Rの荒れるレースを取る買い方（tools/early_upset.py）", "",
         "軸＝その人気帯でフラグ点が上位の2頭まで。回収率・的中レース率・的中時の払戻中央値を 2021-23 / 2024 / 2025-26 で。3期の最低回収率の高い順。", "",
         "| 買い方 | 軸 | レースの形 | 回収率 | 的中レース率 | 払戻中央値 | 1レース点数 | レース数 |", "|---|---|---|---|---|---|---|---|"]
    for m, (fn, ax, sn), cs, roi in sorted(rows, key=lambda r: -r[0])[:40]:
        L.append(f"| {fn} | {ax} | {sn} | " + " / ".join(f"{v:.0%}" for v in roi) + " | " + " / ".join(f"{x[3] / x[0]:.0%}" for x in cs)
                 + " | " + " / ".join(f"{statistics.median(x[4]) if x[4] else 0:,.0f}" for x in cs) + f" | {sum(x[1] for x in cs) / sum(x[0] for x in cs) / 100:.0f} | {sum(x[0] for x in cs)} |")
    (ROOT / "docs" / "analysis" / "early_upset.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:30]))


if __name__ == "__main__":
    main()
