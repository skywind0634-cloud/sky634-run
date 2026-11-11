"""穴同士の組み合わせ（ワイドBOX・3連複BOX）と複勝を、レースの形（1番人気の倍率）で分けて5年分の実払戻で検証（2026-10-18）.
きっかけ: 10/18 新潟8R（3連単1,248,690円）は1着11人気・2着15人気に材料があったが、穴ワイドは穴→1〜4番人気だけで穴同士を買えなかった。
穴＝7〜14番人気でフラグ点 th 以上（data/cache/flag_backtest_rows.json）。上位 k 頭。
使い方: python3 tools/longshot_box.py → docs/analysis/longshot_box.md"""
import itertools, json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from longshot_grid import norm, per  # noqa: E402
from shape_flag import fav_band  # noqa: E402


def main():
    rows = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json"))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    pays, nums, odds = {}, {}, {}
    for rid, pay in c.execute("select race_id, payouts from races where date >= '2021-01-01'"):
        p = json.loads(pay) if pay else {}
        pays[rid] = {k: {norm(str(a).replace("－", "-").split("-")): y for a, y in v} for k, v in p.items()}
    for rid, num, pop, o in c.execute("select race_id, number, popularity, odds from results where popularity is not null"):
        nums[(rid, pop)] = num; odds[(rid, pop)] = o
    by = defaultdict(list)
    for r in rows:
        r["sc"] = r["plus"] - r["minus"]; r["num"] = nums.get((r["rid"], r["pop"]))
        by[r["rid"]].append(r)
    agg = defaultdict(lambda: [[0, 0, 0, 0, 0] for _ in range(3)])
    for rid, hs in by.items():
        if rid not in pays or not all(h["num"] for h in hs) or not odds.get((rid, 1)):
            continue
        shape = fav_band(odds[(rid, 1)]); pr = per(hs[0]["date"]); P = pays[rid]
        pop = {h["pop"]: h["num"] for h in hs}
        for th in (1, 2, 3):
            for k in (2, 3, 4):
                L = sorted([h for h in hs if 7 <= h["pop"] <= 14 and h["sc"] >= th], key=lambda h: (-h["sc"], h["pop"]))[:k]
                if len(L) < 2:
                    continue
                ns = [h["num"] for h in L]
                bets = {
                    "ワイドBOX": {("ワイド", norm(cmb)) for cmb in itertools.combinations(ns, 2)},
                    "複勝": {("複勝", norm([n])) for n in ns},
                    "3連複 穴2頭-1〜3人気": {("3連複", norm([a, b, pop[x]])) for a, b in itertools.combinations(ns, 2) for x in (1, 2, 3) if x in pop},
                    "3連複 穴BOX": {("3連複", norm(cmb)) for cmb in itertools.combinations(ns, 3)} if len(ns) >= 3 else set(),
                }
                for name, bs in bets.items():
                    if not bs:
                        continue
                    rets = [P.get(t, {}).get(cc, 0) for t, cc in bs]
                    for sh in (shape, "全レース"):
                        a = agg[(f"点+{th}以上・上位{k}頭", name, sh)][pr]
                        a[0] += 1; a[1] += len(bs); a[2] += sum(rets) > 0; a[3] += sum(rets); a[4] += any(y >= 10000 for y in rets)
    L = ["# 穴同士の組み合わせ × レースの形（自動生成 tools/longshot_box.py, 5年の実払戻）", "", "- 穴＝7〜14番人気でフラグ点が基準以上。3期間（2021-23/2024/2025-26）とも100%超を太字。", "",
         "| 穴の選び方 | 買い方 | 形 | レース数 | 点数/R | 的中率 | 回収率 | 万馬券 |", "|---|---|---|---|---|---|---|---|"]
    for key in sorted(agg):
        A = agg[key]
        if min(x[0] for x in A) < 20:
            continue
        roi = [x[3] / max(x[1] * 100, 1) * 100 for x in A]
        b = "**" if min(roi) > 100 else ""
        L.append(f"| {key[0]} | {b}{key[1]}{b} | {key[2]} | " + "/".join(str(x[0]) for x in A) + f" | {sum(x[1] for x in A) / sum(x[0] for x in A):.1f} | "
                 + "/".join(f"{x[2] / x[0] * 100:.0f}%" for x in A) + " | " + "/".join(f"{r:.0f}%" for r in roi) + " | " + "/".join(str(x[4]) for x in A) + " |")
    (ROOT / "docs" / "analysis" / "longshot_box.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
