"""高配当狙い（ワイド・3連複）の組み方を5年分の実払戻で総当たり検証（2026-10-17）.
軸＝人気帯×フラグ点（data/cache/flag_backtest_rows.json, tools/flag_backtest.py）、相手＝人気順。
2021-23 / 2024 / 2025-26 の3期間すべてで回収率100%超の組み方を探す。フラグは同じ期間で選んでいるので期間内の確認（真の検証は今後の週）。
使い方: python3 tools/longshot_grid.py → docs/analysis/longshot_grid.md
"""
import itertools, json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def norm(c):
    return "-".join(sorted([str(x) for x in c if str(x).isdigit()], key=int))


def main():
    rows = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json"))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    pays, nums = {}, {}
    for rid, pay in c.execute("select race_id, payouts from races where date >= '2021-01-01'"):
        p = json.loads(pay) if pay else {}
        pays[rid] = {k: {norm(str(a).replace("－", "-").split("-")): y for a, y in v} for k, v in p.items()}
    for rid, num, pop in c.execute("select race_id, number, popularity from results where popularity is not null"):
        nums[(rid, pop)] = num
    by = defaultdict(list)
    for r in rows:
        r["sc"] = r["plus"] - r["minus"]
        r["num"] = nums.get((r["rid"], r["pop"]))
        by[r["rid"]].append(r)
    races = [(rid, hs) for rid, hs in by.items() if all(h["num"] for h in hs) and rid in pays]

    strategies = {}
    for lo, hi in ((4, 6), (7, 9), (10, 12), (7, 12), (4, 9)):
        for th in (2, 3, 4):
            for k in (1, 2):
                def axes(hs, lo=lo, hi=hi, th=th, k=k):
                    c_ = [h for h in hs if lo <= h["pop"] <= hi and h["sc"] >= th]
                    return sorted(c_, key=lambda h: (-h["sc"], h["pop"]))[:k]
                key = f"軸{lo}-{hi}人気・点+{th}以上・上位{k}頭"
                for n in (3, 4, 5):
                    strategies[f"{key} ワイド→1〜{n}人気"] = (axes, "w", n)
                for n in (4, 5, 6):
                    strategies[f"{key} 3連複 軸-1〜2人気-1〜{n}人気"] = (axes, "t12", n)
                strategies[f"{key} 3連複 軸-1〜3人気の2頭"] = (axes, "t3", 3)
                strategies[f"{key} 3連複 軸-1〜4人気の2頭"] = (axes, "t3", 4)
                strategies[f"{key} 複勝"] = (axes, "f", 0)

    def bets(hs, spec):
        axes, kind, n = spec
        pop = {h["pop"]: h["num"] for h in hs}
        out = set()
        for a in axes(hs):
            if kind == "w":
                out |= {("ワイド", norm([a["num"], pop[p]])) for p in range(1, n + 1) if p in pop}
            elif kind == "t12":
                out |= {("3連複", norm([a["num"], pop[x], pop[y]])) for x in (1, 2) for y in range(1, n + 1)
                        if x != y and x in pop and y in pop}
            elif kind == "t3":
                out |= {("3連複", norm([a["num"], pop[x], pop[y]])) for x, y in itertools.combinations(range(1, n + 1), 2) if x in pop and y in pop}
            elif kind == "f":
                out.add(("複勝", norm([a["num"]])))
        return out

    agg = defaultdict(lambda: [[0, 0, 0, 0, 0] for _ in range(3)])  # races, bets, hit races, return, hits>=10000
    for rid, hs in races:
        pr = per(hs[0]["date"]); P = pays[rid]
        for name, spec in strategies.items():
            bs = bets(hs, spec)
            if not bs:
                continue
            rets = [P.get(k, {}).get(cmb, 0) for k, cmb in bs]
            a = agg[name][pr]; a[0] += 1; a[1] += len(bs); a[2] += sum(rets) > 0; a[3] += sum(rets); a[4] += sum(1 for y in rets if y >= 10000)
    res = []
    for name, A in agg.items():
        if min(a[0] for a in A) < 60:
            continue
        roi = [a[3] / max(a[1] * 100, 1) * 100 for a in A]
        res.append((min(roi), name, A, roi))
    res.sort(reverse=True)
    L = ["# 高配当狙いの組み方（5年分の実払戻, 自動生成 tools/longshot_grid.py）", "",
         "- 1点100円。期間＝2021-23 / 2024 / 2025-26。万馬券＝払戻1万円以上の的中数。", "- フラグ点はこの期間で選んだもの（期間内の確認）。", "",
         "| 組み方 | レース数 | 点数/R | 的中率 | 回収率 | 万馬券 |", "|---|---|---|---|---|---|"]
    for mn, name, A, roi in res[:40]:
        L.append(f"| {name} | " + "/".join(str(a[0]) for a in A) + " | " + f"{sum(a[1] for a in A) / sum(a[0] for a in A):.1f} | "
                 + "/".join(f"{a[2] / a[0] * 100:.0f}%" for a in A) + " | " + "/".join(f"{x:.0f}%" for x in roi) + " | " + "/".join(str(a[4]) for a in A) + " |")
    (ROOT / "docs" / "analysis" / "longshot_grid.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
