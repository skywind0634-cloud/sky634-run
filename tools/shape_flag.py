"""★フラグ軸パッケージ・穴ワイド型を、レースの形（1番人気の倍率）で分けて検証（2026-10-17, 全馬の実オッズ）.
使い方: python3 tools/shape_flag.py → docs/analysis/shape_flag.md"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from longshot_grid import norm, per  # noqa: E402


def fav_band(o):
    return "1人気2.0以下" if o <= 2.0 else "1人気2.1〜3.0" if o <= 3.0 else "1人気3.1〜4.0" if o <= 4.0 else "1人気4.1以上"


def main():
    rows = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json"))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    pays, nums, odds = {}, {}, {}
    for rid, pay in c.execute("select race_id, payouts from races where date >= '2021-01-01'"):
        p = json.loads(pay) if pay else {}
        pays[rid] = {k: {norm(str(a).replace("－", "-").split("-")): y for a, y in v} for k, v in p.items()}
    for rid, num, pop, o in c.execute("select race_id, number, popularity, odds from results where popularity is not null"):
        nums[(rid, pop)] = num
        odds[(rid, pop)] = o
    by = defaultdict(list)
    for r in rows:
        r["sc"] = r["plus"] - r["minus"]; r["num"] = nums.get((r["rid"], r["pop"])); r["odds"] = odds.get((r["rid"], r["pop"]))
        by[r["rid"]].append(r)
    S = {}
    for th in (3, 4):
        for lo, hi in ((4, 9), (7, 12), (4, 6), (7, 9), (10, 14)):
            S[(f"軸{lo}-{hi}人気・点+{th}以上", "ワイド→1〜3人気")] = (th, lo, hi, "w3")
            S[(f"軸{lo}-{hi}人気・点+{th}以上", "3連複 軸-1〜2人気-1〜5人気")] = (th, lo, hi, "t")
            S[(f"軸{lo}-{hi}人気・点+{th}以上", "ワイド＋3連複（10点）")] = (th, lo, hi, "wt")
            S[(f"軸{lo}-{hi}人気・点+{th}以上", "3連複 軸-1〜3人気-1〜7人気")] = (th, lo, hi, "t37")
    agg = defaultdict(lambda: [[0, 0, 0, 0, 0] for _ in range(3)])
    for rid, hs in by.items():
        if rid not in pays or not all(h["num"] for h in hs):
            continue
        pop = {h["pop"]: h["num"] for h in hs}
        o1 = odds.get((rid, 1))
        if not o1 or any(p not in pop for p in range(1, 6)):
            continue
        shape = fav_band(o1)
        pr = per(hs[0]["date"]); P = pays[rid]
        for key, (th, lo, hi, kind) in S.items():
            cand = sorted([h for h in hs if lo <= h["pop"] <= hi and h["sc"] >= th], key=lambda h: (-h["sc"], h["pop"]))[:1]
            if not cand:
                continue
            a = cand[0]["num"]
            bs = set()
            if kind in ("w3", "wt"):
                bs |= {("ワイド", norm([a, pop[p]])) for p in (1, 2, 3)}
            if kind in ("t", "wt"):
                bs |= {("3連複", norm([a, pop[x], pop[y]])) for x in (1, 2) for y in range(1, 6) if x != y and pop[y] != a}
            if kind == "t37":
                bs |= {("3連複", norm([a, pop[x], pop[y]])) for x in (1, 2, 3) for y in range(1, 8) if x < y and y in pop and pop[y] != a}
            rets = [P.get(k, {}).get(cc, 0) for k, cc in bs]
            for sh in (shape, "全レース"):
                g = agg[(key[0], key[1], sh)][pr]
                g[0] += 1; g[1] += len(bs); g[2] += sum(rets) > 0; g[3] += sum(rets); g[4] += any(y >= 10000 for y in rets)
    L = ["# ★フラグ軸 × レースの形（自動生成 tools/shape_flag.py, 全馬の実オッズ）", "", "- 期間＝2021-23 / 2024 / 2025-26。3期間とも100%超を太字。", "",
         "| 軸 | 買い方 | 形 | レース数 | 的中率 | 回収率 | 万馬券 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 20:
            continue
        roi = [x[3] / max(x[1] * 100, 1) * 100 for x in A]
        b = "**" if min(roi) > 100 else ""
        L.append(f"| {k[0]} | {b}{k[1]}{b} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{x[2] / x[0] * 100:.0f}%" for x in A)
                 + " | " + "/".join(f"{r:.0f}%" for r in roi) + " | " + "/".join(str(x[4]) for x in A) + " |")
    (ROOT / "docs" / "analysis" / "shape_flag.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
