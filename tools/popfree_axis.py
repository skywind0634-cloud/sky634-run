import json,sqlite3
from collections import defaultdict
c=sqlite3.connect('data/keiba.db')
info={r[0]:json.loads(r[1]) for r in c.execute("select race_id,payouts from races where payouts is not null")}
pn={(r[0],r[1]):r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
R=defaultdict(list)
for r in json.load(open('data/cache/flag_backtest_rows.json')): R[r['rid']].append(r)
def pays(p,k): return {tuple(sorted(int(x) for x in str(it[0]).replace('-',' ').split())):it[1] for it in p.get(k) or []}
def per(d): return 0 if d<'2024' else 1 if d<'2025' else 2
def sim(pick):
    agg=[[0,0,0,0] for _ in range(3)]
    for rid,hs in R.items():
        if rid not in info: continue
        sc={h['pop']:h['plus']-h['minus'] for h in hs}
        ax=pick(rid,sc)
        if ax is None: continue
        n=lambda q:pn.get((rid,q))
        W,T=pays(info[rid],'ワイド'),pays(info[rid],'3連複')
        tw={tuple(sorted((n(ax),n(q)))) for q in range(1,6) if q!=ax and n(q)}
        tt={tuple(sorted((n(ax),n(x),n(y)))) for x in (1,2) for y in range(1,5) if x!=y and ax not in (x,y) and n(x) and n(y)}
        back=sum(W.get(t,0) for t in tw)+sum(T.get(t,0) for t in tt); a=agg[per(hs[0]['date'])]
        a[0]+=1;a[1]+=100*(len(tw)+len(tt));a[2]+=back;a[3]+=back>0
    return "回収 "+" / ".join(f"{a[2]/a[1]:.0%}" if a[1] else '-' for a in agg)+"  的中 "+" / ".join(f"{a[3]/a[0]:.0%}" if a[0] else '-' for a in agg)+"  レース "+"/".join(str(a[0]) for a in agg)
def best(minpop=1,lo=1,hi=18,th=5):
    def f(rid,sc):
        c_=[q for q in sc if sc[q]>=th and q>=minpop and (rid,q) in pn]
        if not c_: return None
        ax=max(c_,key=lambda q:(sc[q],-q))
        return ax if lo<=ax<=hi else None
    return f
for mp,lab in ((3,'今: 3番人気以下だけ'),(2,'2番人気以下'),(1,'人気を問わない')):
    print(f"フラグ点+5の軸 {lab}: {sim(best(mp))}")
print("--- 人気を問わず選んだ軸が何番人気だったか")
for lo,hi in ((1,1),(2,2),(3,3),(4,5),(6,9),(10,18)):
    print(f"  {lo}-{hi}番人気: {sim(best(1,lo,hi))}")
print("--- フラグ点+4（★フラグ軸と同じ点）")
for mp,lab in ((3,'今: 3番人気以下だけ'),(1,'人気を問わない')):
    print(f"  {lab}: {sim(best(mp,th=4))}")
