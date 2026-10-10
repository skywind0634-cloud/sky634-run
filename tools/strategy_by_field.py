exec(open("tools/strategy_compare.py").read().split("S1 = {")[0])
import sqlite3
c = sqlite3.connect("data/keiba.db")
info = {r[0]: r[1:] for r in c.execute("select race_id, race_no, grade, surface, distance, course from races")}
def tp(scope, n=1):
    def f(r):
        rn, gr, sf, dist, crs = info[r["race_id"]]
        N = len(r["horses"])
        ok = {"全": True, "15頭以上": N >= 15, "11-14頭": 11 <= N <= 14, "10頭以下": N <= 10,
              "荒れ条件(15頭↑/芝1200以下/11R/G3/3勝)": N >= 15 or (sf == "芝" and dist <= 1200) or rn == 11 or gr in ("G3", "3勝")}[scope]
        if not ok: return [], None
        v = sorted((h for h in r["horses"] if 4 <= (h["pop"] or 0) <= 9 and S.ratio(h) >= 1.3 and not S.danger(h) and h["cond"] > 0), key=lambda h: -S.ratio(h))[:n]
        T = [(k, (h["num"],)) for h in v for k in ("単勝", "複勝")]
        return (T, 1) if T else ([], None)
    return f
h1 = [r for r in data if r["date"] < "2026-04-01"]; h2 = [r for r in data if r["date"] >= "2026-04-01"]
for sc in ("全", "15頭以上", "11-14頭", "10頭以下", "荒れ条件(15頭↑/芝1200以下/11R/G3/3勝)"):
    row = []
    for d in (h1, h2):
        m = metrics(d, tp(sc)); row.append(f"{m['n']:3d}R 回収{m['roi']:4.0%} 的中{m['hit']:4.0%}")
    m = metrics(data, tp(sc))
    print(f"単複 妙味馬+走る条件 {sc:30s} | 前半 {row[0]} | 後半 {row[1]} | 通年 {m['roi']:4.0%} 最大連敗{m['streak']}")
