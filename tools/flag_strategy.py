"""フラグ点を使った買い方の検証（tools/flag_backtest.py の結果 data/cache/flag_backtest_rows.json を使う, 2026-10-15）.
軸と相手をフラグ点と人気で選び、ワイド・馬連・3連複・複勝・単勝の的中率と回収率を 2021-23 / 2024 / 2025-26 で比べる。
使い方: python3 tools/flag_strategy.py → docs/analysis/flag_strategy.md
"""
import itertools, json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def norm(s):
    return "-".join(sorted(str(s).replace("－", "-").replace("→", "-").split("-"), key=lambda x: int(x) if x.isdigit() else 0))


def main():
    rows = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json"))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    pays = {}
    nums = {}
    for rid, pay in c.execute("select race_id, payouts from races where date >= '2021-01-01'"):
        p = json.loads(pay) if pay else {}
        pays[rid] = {k: {norm(a): y for a, y in v} for k, v in p.items()}
    for rid, num, pop in c.execute("select race_id, number, popularity from results where popularity is not null"):
        nums[(rid, pop)] = num
    by = defaultdict(list)
    for r in rows:
        r["sc"] = r["plus"] - r["minus"]
        by[r["rid"]].append(r)
    for rid, hs in by.items():
        for h in hs:
            h["num"] = nums.get((rid, h["pop"]))
    strategies = {}

    def S(name):
        def deco(f):
            strategies[name] = f
            return f
        return deco

    def bet(kind, combo):
        return (kind, norm("-".join(str(x) for x in combo)))

    @S("A 軸=1-3人気でフラグ点最大(+2以上)→ワイド 相手=4-9人気で+1以上(最大4)")
    def a(hs):
        top = [h for h in hs if h["pop"] <= 3 and h["sc"] >= 2]
        if not top:
            return []
        ax = max(top, key=lambda h: (h["sc"], -h["pop"]))
        aite = sorted([h for h in hs if 4 <= h["pop"] <= 9 and h["sc"] >= 1], key=lambda h: (-h["sc"], h["pop"]))[:4]
        return [bet("ワイド", (ax["num"], x["num"])) for x in aite]

    @S("B 同じ軸→馬連 相手=4-9人気で+1以上(最大4)")
    def b(hs):
        return [("馬連", k) for _, k in a(hs)]

    @S("C 軸=1-3人気でフラグ点最大(+2以上)→3連複 軸-他の1-3人気(0以上)-4-9人気で+1以上（最大6点）")
    def cc(hs):
        top = [h for h in hs if h["pop"] <= 3 and h["sc"] >= 2]
        if not top:
            return []
        ax = max(top, key=lambda h: (h["sc"], -h["pop"]))
        f2 = [h for h in hs if h["pop"] <= 3 and h is not ax and h["sc"] >= 0]
        f3 = sorted([h for h in hs if 4 <= h["pop"] <= 9 and h["sc"] >= 1], key=lambda h: (-h["sc"], h["pop"]))[:4]
        out = set()
        for x in f2:
            for y in f3:
                out.add(bet("3連複", (ax["num"], x["num"], y["num"])))
        for x, y in itertools.combinations(f3, 2):
            if len(out) < 6:
                out.add(bet("3連複", (ax["num"], x["num"], y["num"])))
        return list(out)[:6]

    @S("D 1-3人気で+2以上を複勝")
    def d(hs):
        return [bet("複勝", (h["num"],)) for h in hs if h["pop"] <= 3 and h["sc"] >= 2]

    @S("E 4-6人気で+2以上を複勝")
    def e(hs):
        return [bet("複勝", (h["num"],)) for h in hs if 4 <= h["pop"] <= 6 and h["sc"] >= 2]

    @S("F 4-6人気で+3以上を単勝")
    def f(hs):
        return [bet("単勝", (h["num"],)) for h in hs if 4 <= h["pop"] <= 6 and h["sc"] >= 3]

    @S("G 7-12人気で+3以上を複勝")
    def g(hs):
        return [bet("複勝", (h["num"],)) for h in hs if 7 <= h["pop"] <= 12 and h["sc"] >= 3]

    @S("H 1番人気が-2以下のレースだけ: 2-6人気で+2以上を軸にワイド 2-6人気の他の+1以上へ")
    def hh(hs):
        f1 = [h for h in hs if h["pop"] == 1 and h["sc"] <= -2]
        if not f1:
            return []
        cand = sorted([h for h in hs if 2 <= h["pop"] <= 6 and h["sc"] >= 1], key=lambda h: (-h["sc"], h["pop"]))
        if not cand or cand[0]["sc"] < 2:
            return []
        return [bet("ワイド", (cand[0]["num"], x["num"])) for x in cand[1:5]]

    # 頑健性の確認（条件を少しずらす）
    @S("F2 4-6人気で+3以上を複勝")
    def f2(hs):
        return [bet("複勝", (h["num"],)) for h in hs if 4 <= h["pop"] <= 6 and h["sc"] >= 3]

    @S("F3 4-6人気で+2以上を単勝")
    def f3(hs):
        return [bet("単勝", (h["num"],)) for h in hs if 4 <= h["pop"] <= 6 and h["sc"] >= 2]

    @S("F4 4-6人気で+4以上を単勝")
    def f4(hs):
        return [bet("単勝", (h["num"],)) for h in hs if 4 <= h["pop"] <= 6 and h["sc"] >= 4]

    @S("H2 1番人気が-1以下のレースだけ: 同じワイド")
    def h2(hs):
        f1 = [h for h in hs if h["pop"] == 1 and h["sc"] <= -1]
        if not f1:
            return []
        cand = sorted([h for h in hs if 2 <= h["pop"] <= 6 and h["sc"] >= 1], key=lambda h: (-h["sc"], h["pop"]))
        if not cand or cand[0]["sc"] < 2:
            return []
        return [bet("ワイド", (cand[0]["num"], x["num"])) for x in cand[1:5]]

    @S("H3 1番人気が-2以下: 2-6人気で+2以上の単勝")
    def h3(hs):
        if not [h for h in hs if h["pop"] == 1 and h["sc"] <= -2]:
            return []
        return [bet("単勝", (h["num"],)) for h in hs if 2 <= h["pop"] <= 6 and h["sc"] >= 2]

    @S("H4 1番人気が-2以下: 2-6人気で+2以上の複勝")
    def h4(hs):
        if not [h for h in hs if h["pop"] == 1 and h["sc"] <= -2]:
            return []
        return [bet("複勝", (h["num"],)) for h in hs if 2 <= h["pop"] <= 6 and h["sc"] >= 2]

    @S("H5 1番人気が-2以下: 2-6人気の+2以上同士の馬連（ボックス最大6点）")
    def h5(hs):
        if not [h for h in hs if h["pop"] == 1 and h["sc"] <= -2]:
            return []
        c_ = sorted([h for h in hs if 2 <= h["pop"] <= 6 and h["sc"] >= 2], key=lambda h: -h["sc"])[:4]
        return [bet("馬連", (x["num"], y["num"])) for x, y in itertools.combinations(c_, 2)]

    agg = defaultdict(lambda: [[0, 0, 0, 0] for _ in range(3)])  # races, bets, hits(race), return
    for rid, hs in by.items():
        if any(h["num"] is None for h in hs):
            continue
        pr = per(hs[0]["date"])
        P = pays.get(rid, {})
        for name, fn in strategies.items():
            bs = fn(hs)
            if not bs:
                continue
            ret = sum(P.get(k, {}).get(cmb, 0) for k, cmb in bs)
            a_ = agg[name][pr]; a_[0] += 1; a_[1] += len(bs); a_[2] += ret > 0; a_[3] += ret
    L = ["# フラグ点を使った買い方の検証（自動生成 tools/flag_strategy.py）", "",
         "- 1点100円。的中率＝払戻のあったレースの割合。回収率＝払戻÷購入額。2021-23 / 2024 / 2025-26。",
         "- フラグは全期間で一貫したものを選んでいるので期間内の確認（未来の検証は今後の週）。", "",
         "| 買い方 | レース数 | 平均点数 | 的中率 | 回収率 |", "|---|---|---|---|---|"]
    for name in strategies:
        A = agg[name]
        L.append(f"| {name} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{x[1]/max(x[0],1):.1f}" for x in A) + " | "
                 + "/".join(f"{x[2]/max(x[0],1)*100:.0f}%" for x in A) + " | " + "/".join(f"{x[3]/max(x[1]*100,1)*100:.0f}%" for x in A) + " |")
    (ROOT / "docs" / "analysis" / "flag_strategy.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
