"""7R を「当てにいく」買い方の検証（2026-10-18 ユーザー指示: 7Rはしっかり当てる。当たらないと資金が持たない）.
5年分（2021-23/2024/2025-26）の7Rで、的中率の高い買い方（人気馬中心）にフラグ点（○◎−×▽▼）とレースの形（1番人気の倍率）を組み合わせ、
的中率と回収率を比べる。使い方: python3 tools/r7_hit.py [レース番号...] → docs/analysis/r7_hit.md"""
import itertools, json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from longshot_grid import norm, per  # noqa: E402


def main(rnos=(7,)):
    rows = json.load(open(ROOT / "data" / "cache" / "flag_backtest_rows.json"))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    rno = dict(c.execute("select race_id, race_no from races"))
    pays, nums, odds = {}, {}, {}
    for rid, pay in c.execute("select race_id, payouts from races where date >= '2021-01-01'"):
        p = json.loads(pay) if pay else {}
        pays[rid] = {k: {norm(str(a).replace("－", "-").split("-")): y for a, y in v} for k, v in p.items()}
    for rid, num, pop, o in c.execute("select race_id, number, popularity, odds from results where popularity is not null"):
        nums[(rid, pop)] = num; odds[(rid, pop)] = o
    by = defaultdict(list)
    for r in rows:
        if rno.get(r["rid"]) in rnos:
            r["sc"] = r["plus"] - r["minus"]; r["num"] = nums.get((r["rid"], r["pop"]))
            by[r["rid"]].append(r)
    S = {}

    def s(name):
        def d(f):
            S[name] = f
            return f
        return d

    def top(hs, lo, hi):
        c_ = [h for h in hs if lo <= h["pop"] <= hi]
        return sorted(c_, key=lambda h: (-h["sc"], h["pop"]))

    @s("参考: 1番人気の複勝")
    def a(hs, P):
        return [("複勝", [P[1]])]

    @s("参考: ワイド 1-2人気")
    def b(hs, P):
        return [("ワイド", [P[1], P[2]])]

    @s("1〜3人気でフラグ点最大(+1以上)の複勝")
    def c1(hs, P):
        t = top(hs, 1, 3)
        return [("複勝", [t[0]["num"]])] if t and t[0]["sc"] >= 1 else []

    @s("1〜3人気でフラグ点最大(+2以上)の複勝")
    def c2(hs, P):
        t = top(hs, 1, 3)
        return [("複勝", [t[0]["num"]])] if t and t[0]["sc"] >= 2 else []

    @s("1〜4人気のフラグ点上位2頭(0以上)のワイド1点")
    def d1(hs, P):
        t = [h for h in top(hs, 1, 4) if h["sc"] >= 0][:2]
        return [("ワイド", [x["num"] for x in t])] if len(t) == 2 else []

    @s("1〜4人気のフラグ点上位2頭(+1以上)のワイド1点")
    def d2(hs, P):
        t = [h for h in top(hs, 1, 4) if h["sc"] >= 1][:2]
        return [("ワイド", [x["num"] for x in t])] if len(t) == 2 else []

    @s("軸=1〜3人気でフラグ点最大(+1以上) → ワイド 1〜4人気の他3頭")
    def e1(hs, P):
        t = top(hs, 1, 3)
        if not t or t[0]["sc"] < 1:
            return []
        ax = t[0]["num"]
        return [("ワイド", [ax, P[p]]) for p in (1, 2, 3, 4) if p in P and P[p] != ax][:3]

    @s("軸=1〜3人気でフラグ点最大(+1以上) → 3連複 1〜5人気の2頭（6点）")
    def f1(hs, P):
        t = top(hs, 1, 3)
        if not t or t[0]["sc"] < 1:
            return []
        ax = t[0]["num"]; o = [P[p] for p in (1, 2, 3, 4, 5) if p in P and P[p] != ax]
        return [("3連複", [ax, x, y]) for x, y in itertools.combinations(o, 2)]

    @s("1〜4人気でフラグ点0以上の馬の3連複BOX（最大4頭）")
    def g1(hs, P):
        t = [h["num"] for h in top(hs, 1, 4) if h["sc"] >= 0][:4]
        return [("3連複", list(cmb)) for cmb in itertools.combinations(t, 3)] if len(t) >= 3 else []

    @s("1〜5人気でフラグ点0以上の上位3頭 ワイドBOX（3点）")
    def h1(hs, P):
        t = [h["num"] for h in top(hs, 1, 5) if h["sc"] >= 0][:3]
        return [("ワイド", list(cmb)) for cmb in itertools.combinations(t, 2)] if len(t) == 3 else []

    agg = defaultdict(lambda: [[0, 0, 0, 0] for _ in range(3)])
    for rid, hs in by.items():
        if rid not in pays or not all(h["num"] for h in hs):
            continue
        P = {h["pop"]: h["num"] for h in hs}
        if any(p not in P for p in (1, 2, 3, 4, 5)):
            continue
        o1 = odds.get((rid, 1)) or 0
        shape = "1人気2.0以下" if o1 and o1 <= 2.0 else "1人気2.1〜3.0" if o1 and o1 <= 3.0 else "1人気3.1以上"
        pr = per(hs[0]["date"]); PP = pays[rid]
        for name, f in S.items():
            bs = f(hs, P)
            if not bs:
                continue
            ret = sum(PP.get(k, {}).get(norm(cmb), 0) for k, cmb in bs)
            for key in ((name, "全体"), (name, shape)):
                a_ = agg[key][pr]; a_[0] += 1; a_[1] += len(bs); a_[2] += ret > 0; a_[3] += ret
    L = [f"# {'・'.join(map(str, rnos))}Rを当てにいく買い方（自動生成 tools/r7_hit.py, 5年の実払戻）", "",
         "| 買い方 | 形 | レース数 | 点数/R | 的中率 | 回収率 |", "|---|---|---|---|---|---|"]
    for key in sorted(agg, key=lambda k: (list(S).index(k[0]), k[1])):
        A = agg[key]
        if min(x[0] for x in A) < 20:
            continue
        roi = [x[3] / max(x[1] * 100, 1) * 100 for x in A]
        b = "**" if min(roi) >= 100 else ""
        L.append(f"| {key[0]} | {key[1]} | " + "/".join(str(x[0]) for x in A) + f" | {sum(x[1] for x in A) / sum(x[0] for x in A):.1f} | "
                 + "/".join(f"{x[2] / x[0] * 100:.0f}%" for x in A) + f" | {b}" + "/".join(f"{r:.0f}%" for r in roi) + f"{b} |")
    (ROOT / "docs" / "analysis" / "r7_hit.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(tuple(int(x) for x in sys.argv[1:]) or (7,))
