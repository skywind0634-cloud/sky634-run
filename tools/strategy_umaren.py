exec(open("tools/strategy_compare.py").read().split("S1 = {")[0])
def um(maxN=99, minN=0, partner="axis", th=1.3):
    def f(r):
        N = len(r["horses"])
        if not (minN <= N <= maxN): return [], None
        v = sorted((h for h in r["horses"] if 4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= th and not S.danger(h) and h["cond"] > 0), key=lambda h: -S.ratio(h))[:1]
        if not v: return [], None
        v = v[0]
        hs = sorted(r["horses"], key=lambda h: -h["p"])
        others = [h for h in hs if h is not v and not S.danger(h)]
        if partner == "axis": P = others[:1]
        elif partner == "top2": P = others[:2]
        else: P = others[:3]
        T = [("馬連", (v["num"], x["num"])) for x in P]
        return T, 1
    return f
h1 = [r for r in data if r["date"] < "2026-04-01"]; h2 = [r for r in data if r["date"] >= "2026-04-01"]
for nm, f in {"馬連 妙味馬-◎ 全": um(), "馬連 妙味馬-上位2頭 全": um(partner="top2"), "馬連 妙味馬-上位3頭 全": um(partner="top3"),
              "馬連 妙味馬-◎ 14頭以下": um(14), "馬連 妙味馬-上位2頭 14頭以下": um(14, partner="top2"), "馬連 妙味馬-上位3頭 14頭以下": um(14, partner="top3"),
              "馬連 妙味馬-上位3頭 15頭以上": um(minN=15, partner="top3")}.items():
    row = []
    for d in (h1, h2):
        m = metrics(d, f); row.append(f"{m['n']:3d}R 回収{m['roi']:4.0%} 的中{m['hit']:4.0%}")
    m = metrics(data, f)
    print(f"{nm:24s} | 前半 {row[0]} | 後半 {row[1]} | 通年 {m['roi']:4.0%} 最大連敗{m['streak']}")
