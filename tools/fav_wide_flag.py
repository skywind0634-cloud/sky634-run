"""1〜2番人気を軸に、フラグ点の高い穴馬へワイド・3連複を流すと当たって儲かるか（2026-10-24, ユーザー「当たらないと意味ない」）.
フラグは data/cache/flag_backtest_rows.json（tools/flag_backtest.py）。払戻は races.payouts（実払戻）。
使い方: python3 tools/fav_wide_flag.py
"""
import json, sqlite3, sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pays(p, kind):
    out = {}
    for it in p.get(kind) or []:
        out[tuple(sorted(int(x) for x in str(it[0]).replace("-", " ").split()))] = it[1]
    return out


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    pay = {r[0]: json.loads(r[1]) for r in c.execute("select race_id,payouts from races where payouts is not null")}
    num = {(r[0], r[1]): r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
    fo = {r[0]: r[1] for r in c.execute("select race_id,odds from results where popularity=1")}
    races = defaultdict(list)
    for r in json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json")):
        races[r["rid"]].append(r)
    res = defaultdict(lambda: [[0, 0, 0, 0, 0] for _ in range(3)])  # bets, hits, ret, races_hit
    for rid, hs in races.items():
        if rid not in pay:
            continue
        p = per(hs[0]["date"])
        w, t = pays(pay[rid], "ワイド"), pays(pay[rid], "3連複")
        bypop = {h["pop"]: h for h in hs}
        for th in (2, 3):
            for band in ((4, 9), (4, 12), (7, 12)):
                part = [h for h in hs if band[0] <= h["pop"] <= band[1] and h["plus"] - h["minus"] >= th]
                if not part:
                    continue
                for axn, axes in (("1人気", [1]), ("1-2人気", [1, 2])):
                    for fav_cond in ("全", "1人気2.5倍以下", "1人気2.6倍以上"):
                        o = fo.get(rid) or 0
                        if fav_cond == "1人気2.5倍以下" and not (0 < o <= 2.5):
                            continue
                        if fav_cond == "1人気2.6倍以上" and not (o > 2.5):
                            continue
                        key = f"ワイド {axn}→{band[0]}-{band[1]}人気でフラグ点+{th}以上 [{fav_cond}]"
                        cell = res[key][p]; hit = 0
                        for a in axes:
                            for h in part[:3]:
                                na, nh = num.get((rid, a)), num.get((rid, h["pop"]))
                                if not na or not nh:
                                    continue
                                cell[0] += 1
                                v = w.get(tuple(sorted((na, nh))))
                                if v:
                                    cell[1] += 1; cell[2] += v; hit = 1
                        cell[3] += hit; cell[4] += 1
                        # 3連複 1人気-2人気-穴
                        key3 = f"3連複 1人気-2人気-{band[0]}-{band[1]}人気でフラグ点+{th}以上 [{fav_cond}]"
                        cell = res[key3][p]; hit = 0
                        n1, n2 = num.get((rid, 1)), num.get((rid, 2))
                        for h in part[:3]:
                            nh = num.get((rid, h["pop"]))
                            if not (n1 and n2 and nh):
                                continue
                            cell[0] += 1
                            v = t.get(tuple(sorted((n1, n2, nh))))
                            if v:
                                cell[1] += 1; cell[2] += v; hit = 1
                        cell[3] += hit; cell[4] += 1
    nraces = defaultdict(int)
    out = ["# 人気馬を軸にフラグ点の穴馬へ（ワイド・3連複）", "", "回収率・的中率（買ったレースのうち1点でも当たった割合）を 2021-23 / 2024 / 2025-26 で。", "",
           "| 買い方 | 回収率 | 的中レース率 | 点数 |", "|---|---|---|---|"]
    rows = []
    for k, cs in res.items():
        if min(x[0] for x in cs) < 100:
            continue
        roi = [x[2] / x[0] for x in cs]
        rows.append((min(roi), k, roi, cs))
    for m, k, roi, cs in sorted(rows, reverse=True):
        out.append(f"| {k} | " + " / ".join(f"{v:.0f}%" for v in roi) + " | " + " / ".join(f"{x[3] / x[4]:.0%}" for x in cs) + " | " + "/".join(str(x[0]) for x in cs) + f"（{sum(x[4] for x in cs)}レース） |")
    (ROOT / "docs" / "analysis" / "fav_wide_flag.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:40]))


if __name__ == "__main__":
    main()
