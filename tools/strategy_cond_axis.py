"""「走る条件」を軸にした単複の検証（1レース1頭, 過去1年・前半/後半）."""
exec(open("tools/strategy_compare.py").read().split("S1 = {")[0])


def axis(cmin, rmin=0.0, pmin=4, pmax=9, key="cond"):
    def f(r):
        c = [h for h in r["horses"] if pmin <= (h["pop"] or 0) <= pmax and h["cond"] >= cmin and S.ratio(h) >= rmin and not S.danger(h)]
        if not c:
            return [], None
        h = max(c, key=(lambda h: h["cond"]) if key == "cond" else (lambda h: S.ratio(h)))
        return [("単勝", (h["num"],)), ("複勝", (h["num"],))], 1
    return f


h1 = [r for r in data if r["date"] < "2026-04-01"]; h2 = [r for r in data if r["date"] >= "2026-04-01"]
for nm, f in {
    "本線（4-9人気・人気比1.3↑・走る条件+）": axis(0.0001, 1.3, key="ratio"),
    "走る条件0.4↑ 最大の馬（4-9人気）": axis(0.4),
    "走る条件0.6↑ 最大の馬（4-9人気）": axis(0.6),
    "走る条件0.8↑ 最大の馬（4-9人気）": axis(0.8),
    "走る条件0.4↑・人気比1.0↑ 最大（4-9）": axis(0.4, 1.0),
    "走る条件0.4↑・人気比1.3↑ 最大（4-9）": axis(0.4, 1.3),
    "走る条件0.4↑ 最大の馬（1-3人気）": axis(0.4, pmin=1, pmax=3),
    "走る条件0.4↑ 最大の馬（4-6人気）": axis(0.4, pmin=4, pmax=6),
    "走る条件0.4↑ 最大の馬（7-9人気）": axis(0.4, pmin=7, pmax=9),
    "走る条件0.6↑ 最大の馬（10-12人気）": axis(0.6, pmin=10, pmax=12),
}.items():
    row = []
    for d in (h1, h2):
        m = metrics(d, f); row.append(f"{m['n']:3d}R 回収{m['roi']:4.0%} 的中{m['hit']:4.0%}")
    m = metrics(data, f)
    print(f"{nm:34s} | 前半 {row[0]} | 後半 {row[1]} | 通年 {m['roi']:4.0%} 最大連敗{m['streak']} 4週+{m['m4']:4.0%}")
