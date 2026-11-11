import pickle, sys, itertools
from collections import defaultdict
D = pickle.load(open(sys.argv[1], "rb"))
def g(f, k, d=None):
    v = f.get(k); return d if v is None else v
R = {
 "近3走すべて1.5秒以上負け": lambda f: g(f,"nb3",0) >= 2 and g(f,"b_min3",0) >= 1.5,
 "近3走すべて1.0秒以上負け": lambda f: g(f,"nb3",0) >= 2 and g(f,"b_min3",0) >= 1.0,
 "前走2.0秒以上負け": lambda f: g(f,"b_last",0) >= 2.0,
 "前走1.0秒以上負け": lambda f: g(f,"b_last",0) >= 1.0,
 "近3走すべて6着以下": lambda f: len(g(f,"fins3",[])) >= 2 and all((x or 99) >= 6 for x in f["fins3"]),
 "近3走すべて10着以下": lambda f: len(g(f,"fins3",[])) >= 2 and all((x or 99) >= 10 for x in f["fins3"]),
 "前走上がり9位以下": lambda f: g(f,"l3r_last",0) >= 9,
 "前走後方(後ろ4割)": lambda f: g(f,"pos_last",0) >= 0.6,
 "昇級": lambda f: g(f,"gchg",0) > 0,
 "休み明け(半年以上)": lambda f: g(f,"days",0) >= 180,
 "距離400m以上変更": lambda f: abs(g(f,"dchg",0)) >= 400,
 "芝ダ替わり": lambda f: g(f,"sw",False),
 "同じ芝ダで1.0秒未満の走りなし": lambda f: f.get("n_hist",0) >= 3 and (f.get("same_su_b") is None or f["same_su_b"] >= 1.0),
 "馬体重±14以上": lambda f: abs(g(f,"bwd",0)) >= 14,
 "7歳以上": lambda f: g(f,"age",0) >= 7,
}
def per(d): return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2
base = defaultdict(lambda: [0,0])
for r in D:
    for f in r["horses"]:
        if f["pop"] and f["fin"]: b = base[min(f["pop"],14)]; b[0]+=1; b[1]+= f["fin"]<=3
exp = {p: v[1]/v[0] for p,v in base.items()}
agg = defaultdict(lambda: [[0,0,0.0] for _ in range(3)])
names = list(R)
for r in D:
    pr = per(r["date"])
    for f in r["horses"]:
        if not f["pop"] or not f["fin"]: continue
        hits = [k for k in names if R[k](f)]
        band = "1-3人気" if f["pop"] <= 3 else "4-6人気" if f["pop"] <= 6 else "7人気以下"
        keys = [(k,) for k in hits] + [tuple(sorted(p)) for p in itertools.combinations(hits, 2)]
        for k in keys:
            for b in ("全", band):
                a = agg[(k, b)][pr]; a[0]+=1; a[1]+= f["fin"]<=3; a[2]+= exp[min(f["pop"],14)]
res = []
for (k, b), A in agg.items():
    if min(a[0] for a in A) < 40: continue
    rate = [a[1]/a[0]*100 for a in A]; ae = [a[1]/a[2] for a in A]
    res.append((max(ae), k, b, rate, ae, [a[0] for a in A]))
print("人気馬（1-6人気）でも来ない条件: A/E が3期間とも0.6以下")
for m, k, b, rate, ae, n in sorted(res):
    if b in ("1-3人気","4-6人気") and m <= 0.6:
        print(f"  {b} {' & '.join(k):40s} 3着内 {rate[0]:.0f}/{rate[1]:.0f}/{rate[2]:.0f}% A/E {ae[0]:.2f}/{ae[1]:.2f}/{ae[2]:.2f} n {n}")
print("全体: 3着内率が3期間とも5%以下")
for m, k, b, rate, ae, n in sorted(res, key=lambda x: max(x[3])):
    if b == "全" and max(rate) <= 5 and min(n) >= 200:
        print(f"  {' & '.join(k):40s} 3着内 {rate[0]:.1f}/{rate[1]:.1f}/{rate[2]:.1f}% A/E {ae[0]:.2f}/{ae[1]:.2f}/{ae[2]:.2f} n {n}")
