import json, sqlite3
from collections import defaultdict
from itertools import combinations
c=sqlite3.connect('data/keiba.db')
rinfo={r[0]:(r[1],json.loads(r[2])) for r in c.execute("select race_id,race_no,payouts from races where payouts is not null")}
num={(r[0],r[1]):r[2] for r in c.execute("select race_id,popularity,number from results where popularity is not null")}
fo={r[0]:r[1] or 0 for r in c.execute("select race_id,odds from results where popularity=1")}
def pays(p,k):
    o={}
    for it in p.get(k) or []: o[tuple(sorted(int(x) for x in str(it[0]).replace('-',' ').split()))]=it[1]
    return o
def per(d): return 0 if d<'2024' else 1 if d<'2025' else 2
R=defaultdict(list)
for r in json.load(open('data/cache/flag_backtest_rows.json')): R[r['rid']].append(r)
agg=defaultdict(lambda:[[0,0,0,0] for _ in range(3)])
for rid,hs in R.items():
    if rid not in rinfo: continue
    rno,p=rinfo[rid]
    if rno not in (7,8): continue
    sc={h['pop']:h['plus']-h['minus'] for h in hs}
    n=lambda pp:num.get((rid,pp))
    P={k:pays(p,k) for k in ('複勝','ワイド','馬連','3連複','単勝')}
    o=fo.get(rid,0); d=hs[0]['date']
    F={}
    fl=[pp for pp in sorted(sc) if 2<=pp<=9 and sc[pp]>=2]
    fl3=[pp for pp in sorted(sc) if 4<=pp<=12 and sc[pp]>=3]
    s1=sc.get(1,0)
    if n(1) and n(2):
        for nm,cond in (('1人気点+1以上',s1>=1),('1人気点0以上',s1>=0),('全',True)):
            for ob,oc in (('≤2.0',o<=2.0),('≤3.0',o<=3.0),('全',True)):
                if not(cond and oc): continue
                tag=f'[{nm}・1人気{ob}]'
                F['複勝1人気'+tag]=[('複勝',(n(1),))]
                if fl: F['ワイド1人気→点+2の2-9人気(最大3)'+tag]=[('ワイド',tuple(sorted((n(1),n(x))))) for x in fl[:3] if n(x)]
                if fl: F['3連複1-2人気→点+2の3-9人気(最大3)'+tag]=[('3連複',tuple(sorted((n(1),n(2),n(x))))) for x in fl[:3] if x>2 and n(x)]
                if fl3: F['3連複1-2人気→点+3の4-12人気(最大3)'+tag]=[('3連複',tuple(sorted((n(1),n(2),n(x))))) for x in fl3[:3] if n(x)]
                if fl3: F['ワイド1人気→点+3の4-12人気(最大3)'+tag]=[('ワイド',tuple(sorted((n(1),n(x))))) for x in fl3[:3] if n(x)]
                if fl: F['複勝1人気＋ワイド1人気→点+2(最大2)'+tag]=[('複勝',(n(1),))]+[('ワイド',tuple(sorted((n(1),n(x))))) for x in fl[:2] if n(x)]
    for k,T in F.items():
        T=[t for t in T if t]
        if not T: continue
        back=sum(P[a].get(b,0) for a,b in T); cost=100*len(T)
        x=agg[k][per(d)]; x[0]+=1; x[1]+=back>cost; x[2]+=cost; x[3]+=back
rows=[]
for k,cs in agg.items():
    if min(x[0] for x in cs)<40: continue
    rows.append((min(x[3]/x[2] for x in cs),k,cs))
for m,k,cs in sorted(rows,reverse=True)[:25]:
    print(k,'プラス率',' / '.join(f"{x[1]/x[0]:.0%}" for x in cs),'回収',' / '.join(f"{x[3]/x[2]:.0%}" for x in cs),'R',sum(x[0] for x in cs),'点',round(cs[0][2]/cs[0][0]/100,1))
