import json
from keiba import strategy as S
data = json.loads(S.CACHE.read_text())
h1 = [r for r in data if r["date"] < "2026-04-01"]; h2 = [r for r in data if r["date"] >= "2026-04-01"]
def stat(d, sel):
    n = w = t = tr = fr = 0
    for r in d:
        for h in r["horses"]:
            if not sel(h, r): continue
            n += 1; w += h["fin"] == 1; t += (h["fin"] or 99) <= 3
            tr += S.payout("単勝", (h["num"],), r["pay"]); fr += S.payout("複勝", (h["num"],), r["pay"])
    return n, w, t, tr, fr
def best(h, r, th=1.3):
    v = [x for x in r["horses"] if 4 <= (x["pop"] or 0) <= 9 and S.ratio(x) >= th and not S.danger(x)]
    return bool(v) and h is max(v, key=S.ratio)
P49 = lambda h: 4 <= (h["pop"] or 0) <= 9
cases = {
 "4-9番人気 全馬（DBなし＝人気だけ）": lambda h, r: P49(h),
 "妙味馬（DBの総合評価）": best,
 " ＋血統要素プラス(up>0)": lambda h, r: best(h, r) and h["up"] > 0,
 " ＋血統要素 0.5以上": lambda h, r: best(h, r) and h["up"] >= 0.5,
 " ＋人気帯内で走る条件(cond>0)": lambda h, r: best(h, r) and h["cond"] > 0,
 " ＋走る条件 0.3以上": lambda h, r: best(h, r) and h["cond"] >= 0.3,
 " ＋妙味条件(edge>0)": lambda h, r: best(h, r) and h["edge"] > 0,
 " ＋血統plus かつ 走る条件plus": lambda h, r: best(h, r) and h["up"] > 0 and h["cond"] > 0,
 "4-9番人気で 血統要素0.5以上のみ": lambda h, r: P49(h) and h["up"] >= 0.5,
 "4-9番人気で 走る条件0.3以上のみ": lambda h, r: P49(h) and h["cond"] >= 0.3,
 "4-9番人気で 妙味条件あり(edge>0)のみ": lambda h, r: P49(h) and h["edge"] > 0,
}
for nm, f in cases.items():
    row = []
    for d in (h1, h2):
        n, w, t, tr, fr = stat(d, f)
        row.append(f"{n:5d}頭 複{t/n:4.0%} 単{tr/n:4.0f}% 複{fr/n:4.0f}% 単複{(tr+fr)/2/n:4.0f}%")
    print(f"{nm:30s} | 前半 {row[0]} | 後半 {row[1]}")
