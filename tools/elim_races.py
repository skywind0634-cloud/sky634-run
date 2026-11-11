import pickle, sys, itertools, statistics
from collections import defaultdict
sys.path.insert(0, ".")
from keiba.strategy import payout
D = pickle.load(open(sys.argv[1], "rb"))
def g(f, k, d=None):
    v = f.get(k); return d if v is None else v
def excluded(f):
    return (g(f,"nb3",0) >= 2 and g(f,"b_min3",0) >= 1.5) or (g(f,"age",0) >= 7 and g(f,"nb3",0) >= 2 and g(f,"b_min3",0) >= 1.0) \
        or (len(g(f,"fins3",[])) >= 2 and all((x or 99) >= 10 for x in f["fins3"]))
base = defaultdict(lambda: [0,0])
for r in D:
    for f in r["horses"]:
        if f["pop"] and f["fin"]: b = base[min(f["pop"],14)]; b[0]+=1; b[1]+= f["fin"]<=3
exp = {p: v[1]/v[0] for p,v in base.items()}
def per(d): return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2
agg = defaultdict(lambda: [[0,0,0,[]] for _ in range(3)])
for r in D:
    if not r["pay"]: continue
    hs = [f for f in r["horses"] if f["pop"]]
    if len(hs) < 8: continue
    pr = per(r["date"])
    ex = [f for f in hs if excluded(f)]
    mass = sum(exp[min(f["pop"],14)] for f in ex)   # 消した馬の「人気から見込む3着内数」
    nex6 = sum(1 for f in ex if f["pop"] <= 8)
    lab_m = "消し量0" if mass == 0 else "〜0.2" if mass < 0.2 else "0.2-0.4" if mass < 0.4 else "0.4以上"
    keep = sorted([f for f in hs if not excluded(f)], key=lambda f: f["pop"])
    allp = sorted(hs, key=lambda f: f["pop"])
    for N in (4, 5, 6):
        for lab, pool in (("消去後", keep), ("消去なし", allp)):
            box = [f["num"] for f in pool[:N]]
            if len(box) < N: continue
            T = [("三連複", c) for c in itertools.combinations(box, 3)]
            y = sum(payout(k, c, r["pay"]) for k, c in T)
            for m in (lab_m, "全", "8人気内を消した" if nex6 else "8人気内消しなし"):
                a = agg[(f"3複BOX{N}頭", lab, m)][pr]; a[0]+=1; a[1]+=100*len(T); a[2]+=y; 
                if y: a[3].append(y)
            Tw = [("ワイド", c) for c in itertools.combinations(box[:4], 2)]
            yw = sum(payout(k, c, r["pay"]) for k, c in Tw)
            if N == 4:
                for m in (lab_m, "全", "8人気内を消した" if nex6 else "8人気内消しなし"):
                    a = agg[("ワイドBOX4頭", lab, m)][pr]; a[0]+=1; a[1]+=100*len(Tw); a[2]+=yw
                    if yw: a[3].append(yw)
print("買い方 | 選び方 | レース条件 | R数 発見/確認/テスト | 回収率 | 的中率 | 的中時中央")
for key in sorted(agg):
    A = agg[key]
    if min(a[0] for a in A) < 30: continue
    print(f"{key[0]} | {key[1]} | {key[2]} | " + "/".join(str(a[0]) for a in A) + " | " + "/".join(f"{a[2]/a[1]*100:.0f}" for a in A) + "% | " +
          "/".join(f"{len(a[3])/a[0]*100:.0f}" for a in A) + "% | " + "/".join(f"{statistics.median(a[3]) if a[3] else 0:,.0f}" for a in A))
