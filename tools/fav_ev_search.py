import json, sys, itertools, random, statistics
sys.path.insert(0, ".")
from keiba.strategy import payout, ticket_prob
D = json.load(open("data/cache/strategy_backtest.json"))
# 各レースの候補券（モデル上位7頭の組合せで、1〜3番人気を1頭以上含む）を前計算
pre = []
for r in D:
    hs = r["horses"]
    if any(h["pop"] is None for h in hs) or len(hs) < 8: continue
    p = {h["num"]: h["p"] for h in hs}; pm = {h["num"]: h["pm"] for h in hs}
    sp, sm = sum(p.values()), sum(pm.values()); p = {k: v/sp for k, v in p.items()}; pm = {k: v/sm for k, v in pm.items()}
    pop = {h["num"]: h["pop"] for h in hs}
    top = [h["num"] for h in sorted(hs, key=lambda h: -h["p"])[:7]]
    T = []
    for kind, k in (("ワイド", 2), ("馬連", 2), ("三連複", 3)):
        for c in itertools.combinations(sorted(top), k):
            if min(pop[x] for x in c) > 3: continue
            a, b = ticket_prob(kind, c, p), ticket_prob(kind, c, pm)
            T.append((kind, c, a, a / b, max(pop[x] for x in c), payout(kind, c, r["pay"])))
    pre.append((r["date"], len(hs), T))
print("races", len(pre))
def run(rows, kind, th, mp, maxn, maxpop):
    B = Y = H = R = 0; hits = []
    for date, n, T in rows:
        sel = sorted([t for t in T if t[0] == kind and t[3] >= th and t[2] >= mp and t[4] >= maxpop], key=lambda t: -t[3])[:maxn]
        if not sel: continue
        y = sum(t[5] for t in sel); B += 100*len(sel); Y += y; R += 1; H += y > 0
        if y: hits.append(y)
    return (Y/B*100 if B else 0, R, H/R*100 if R else 0, B/max(R,1)/100, statistics.median(hits) if hits else 0)
h1 = [x for x in pre if x[0] < "2026-04-01"]; h2 = [x for x in pre if x[0] >= "2026-04-01"]
res = []
for kind in ("ワイド", "馬連", "三連複"):
    for th in (1.0, 1.1, 1.2, 1.3, 1.5, 1.8):
        for mp in (0.0, 0.02, 0.05, 0.1, 0.2):
            for maxn in (1, 2, 3, 5):
                for maxpop in (1, 4, 6):   # 組合せの中に maxpop番人気以下の馬を含む（=人気薄も絡める）
                    a = run(h1, kind, th, mp, maxn, maxpop)
                    if a[1] >= 60: res.append((a[0], kind, th, mp, maxn, maxpop, a))
res.sort(reverse=True)
print("前半で上位の設定 → 後半（未使用）")
for roi, kind, th, mp, maxn, maxpop, a in res[:25]:
    b = run(h2, kind, th, mp, maxn, maxpop)
    print(f"{kind} 比≥{th} 確率≥{mp} 最大{maxn}点 相手{maxpop}人気以下含む | 前半 回収{a[0]:.0f}% R{a[1]} 的中{a[2]:.0f}% | 後半 回収{b[0]:.0f}% R{b[1]} 的中{b[2]:.0f}% 点/R{b[3]:.1f} 中央{b[4]:,.0f}円")
