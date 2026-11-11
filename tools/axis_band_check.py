"""軸の選び方を「人気の順位」から「単勝オッズの範囲」に替えても成績が保てるか（2026-10-24, ユーザー「6番人気と7番人気の差なんて根拠ない。単なる人気」）.
★フラグ軸と同じ形（フラグ点上位1頭を軸に ワイド→1〜3番人気＋3連複 軸−1〜2番人気−1〜5番人気）で、軸の条件を順位の帯とオッズの帯で比べる。
帯の境目を少しずらしても成績が崩れないかも見る（崩れるなら境目に根拠がない）。全レースと7R・8R。
使い方: python3 tools/axis_band_check.py → docs/analysis/axis_band_check.md
"""
import json, sqlite3, statistics
from collections import defaultdict
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
    pn = {(r[0], r[1]): (r[2], r[3] or 0) for r in c.execute("select race_id,popularity,number,odds from results where popularity is not null")}
    R = defaultdict(list)
    for r in json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json")):
        R[r["rid"]].append(r)
    conds = {f"順位 {a}〜{b}番人気": ("pop", a, b) for a, b in ((4, 9), (3, 9), (5, 9), (4, 8), (4, 10), (5, 10), (3, 10), (3, 18), (4, 18), (7, 18))}
    conds.update({f"オッズ {a}〜{b}倍": ("odds", a, b) for a, b in ((7, 30), (6, 30), (8, 30), (7, 25), (7, 40), (10, 40), (8, 50))})
    agg = defaultdict(lambda: [[0, 0, 0, 0, []] for _ in range(3)])
    for rid, hs in R.items():
        if rid not in info:
            continue
        rno, p = info[rid]; d = hs[0]["date"]
        W, T = pays(p, "ワイド"), pays(p, "3連複")
        num = {h["pop"]: pn.get((rid, h["pop"]), (None, 0)) for h in hs}
        sc = {h["pop"]: h["plus"] - h["minus"] for h in hs}
        for cn, (kind, a, b) in conds.items():
            for th in (3, 4, 5):
                cand = [q for q in sc if sc[q] >= th and (a <= q <= b if kind == "pop" else a <= num[q][1] <= b)]
                if not cand:
                    continue
                ax = sorted(cand, key=lambda q: (-sc[q], q))[0]
                n = lambda q: num.get(q, (None,))[0]
                tk = [("W", tuple(sorted((n(ax), n(x))))) for x in (1, 2, 3) if x != ax and n(x)]
                tk += list({("T", tuple(sorted((n(ax), n(x), n(y))))) for x in (1, 2) for y in range(1, 6) if x < y and ax not in (x, y) and n(x) and n(y)})
                back = sum((W if k == "W" else T).get(t, 0) for k, t in tk); cost = 100 * len(tk)
                for scope in ("全レース", "7R・8R") if rno in (7, 8) else ("全レース",):
                    x = agg[(scope, th, cn)][per(d)]
                    x[0] += 1; x[1] += cost; x[2] += back
                    if back:
                        x[3] += 1; x[4].append(back)
    L = ["# 軸の条件: 人気の順位 と 単勝オッズの範囲（tools/axis_band_check.py）", "",
         "★フラグ軸と同じ形。回収率と的中レース率を 2021-23 / 2024 / 2025-26 で。境目をずらしても大きく崩れなければ、その帯に頼りすぎていない。", ""]
    for scope in ("全レース", "7R・8R"):
        for th in (3, 4, 5):
            L += [f"## {scope}・フラグ点+{th}以上", "", "| 軸の条件 | 回収率 | 的中レース率 | 払戻中央値 | レース数 |", "|---|---|---|---|---|"]
            for cn in conds:
                cs = agg.get((scope, th, cn))
                if not cs or min(x[0] for x in cs) < 20:
                    continue
                L.append(f"| {cn} | " + " / ".join(f"{x[2] / x[1]:.0%}" for x in cs) + " | " + " / ".join(f"{x[3] / x[0]:.0%}" for x in cs)
                         + " | " + " / ".join(f"{statistics.median(x[4]) if x[4] else 0:,.0f}" for x in cs) + f" | {sum(x[0] for x in cs)} |")
            L.append("")
    (ROOT / "docs" / "analysis" / "axis_band_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
