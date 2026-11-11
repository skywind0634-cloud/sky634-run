"""「適性だけ」（人気・オッズを見ないフラグ点＝前日のオッズ前と同じ条件）と「人気も見る」フラグ点で、
選んだ馬の3着内率と買い目の成績を比べる（2026-11-07, ユーザー指示）.
入力: data/cache/flag_backtest_rows.json（人気も見る）と flag_backtest_rows_blind.json（BLIND=1 python3 tools/flag_backtest.py）.
軸＝各レースでフラグ点が閾値以上の最上位1頭（人気は問わない）。買い目＝ワイド→1〜5番人気＋3連複 軸−1〜2番人気−1〜4番人気（紐は当日の人気）。
使い方: python3 tools/blind_vs_pop.py → docs/analysis/blind_vs_pop.md
"""
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pays(p, k):
    return {tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split())): it[1] for it in p.get(k) or []}


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    info = {r[0]: json.loads(r[1]) for r in c.execute("select race_id,payouts from races where payouts is not null")}
    pn = {(r[0], r[1]): r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
    base = defaultdict(lambda: [0, 0])
    for p, f in c.execute("select popularity,finish from results where finish>0 and popularity>0"):
        b = base[min(p, 14)]; b[0] += 1; b[1] += f <= 3
    exp = {k: v[1] / v[0] for k, v in base.items()}
    sets = {}
    for name, f in (("人気も見る", "flag_backtest_rows.json"), ("適性だけ", "flag_backtest_rows_blind.json")):
        R = defaultdict(list)
        for r in json.load(open(ROOT / "data" / "cache" / f)):
            R[r["rid"]].append(r)
        sets[name] = R
    L = ["# 適性だけ（前日・オッズ前）と人気も見る（当日）の比較（tools/blind_vs_pop.py）", "",
         "軸＝フラグ点が閾値以上の最上位1頭（人気は問わない）。3期＝2021-23 / 2024 / 2025-26。実払戻。", "",
         "| フラグ点 | 版 | 軸の3着内率 | 軸のA/E | 買い目の的中率 | 買い目の回収率 | レース数 |", "|---|---|---|---|---|---|---|"]
    for th in (3, 4, 5):
        for name, R in sets.items():
            agg = [[0, 0, 0.0, 0, 0, 0] for _ in range(3)]   # races, axis top3, exp, cost, back, hit
            for rid, hs in R.items():
                if rid not in info:
                    continue
                sc = {h["pop"]: (h["plus"] - h["minus"], h["fin"]) for h in hs}
                cand = [q for q in sc if sc[q][0] >= th and (rid, q) in pn]
                if not cand:
                    continue
                ax = max(cand, key=lambda q: (sc[q][0], -q))
                n = lambda q: pn.get((rid, q))
                W, T = pays(info[rid], "ワイド"), pays(info[rid], "3連複")
                tw = {tuple(sorted((n(ax), n(q)))) for q in range(1, 6) if q != ax and n(q)}
                tt = {tuple(sorted((n(ax), n(x), n(y)))) for x in (1, 2) for y in range(1, 5) if x != y and ax not in (x, y) and n(x) and n(y)}
                back = sum(W.get(t, 0) for t in tw) + sum(T.get(t, 0) for t in tt)
                a = agg[per(hs[0]["date"])]
                a[0] += 1; a[1] += sc[ax][1] <= 3; a[2] += exp[min(ax, 14)]; a[3] += 100 * (len(tw) + len(tt)); a[4] += back; a[5] += back > 0
            L.append(f"| +{th}以上 | {name} | " + " / ".join(f"{a[1] / a[0]:.0%}" for a in agg) + " | " + " / ".join(f"{a[1] / a[2]:.2f}" for a in agg)
                     + " | " + " / ".join(f"{a[5] / a[0]:.0%}" for a in agg) + " | " + " / ".join(f"{a[4] / a[3]:.0%}" for a in agg) + " | " + " / ".join(str(a[0]) for a in agg) + " |")
    (ROOT / "docs" / "analysis" / "blind_vs_pop.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
