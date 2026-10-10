"""大井・高知 最終レースの補足分析: 偶然の基準（ランダムな特徴で何%が両期間100%超になるか）、三連単10万円以上の条件、人気順フォーメーション.
出力は標準出力（docs/analysis/nar_final.md の「補足」に転記）."""
import sys, random, statistics as st
sys.path.insert(0, __import__('os').path.dirname(__file__)); import nar_final_analysis as A
from collections import defaultdict
from itertools import permutations, combinations
for name, fn in A.FILES.items():
    rs=sorted(A.load(fn), key=lambda r:r['date'])
    # random baseline: how many random 10-way features survive
    surv=[]
    for seed in range(20):
        random.seed(seed); acc=defaultdict(lambda:{"前半":A.Acc(),"後半":A.Acc()}); t=0; s=0
        for r in rs:
            for e in r['entries']:
                b='1-3' if e['pop']<=3 else '4-6' if e['pop']<=6 else '7+'
                for j in range(4): acc[(b,j,random.randrange(12))][r['half']].add(e,r)
        for k,d in acc.items():
            a,bb=d['前半'],d['後半']
            if a.n<40 or bb.n<24: continue
            for fa,fb in ((a.wp/a.n,bb.wp/bb.n),(a.pp/a.n,bb.pp/bb.n)):
                t+=1; s+= fa>=100 and fb>=100
        surv.append(s/t)
    print(name,'random survive rate %.1f%%'%(100*st.mean(surv)))
    # 三連単 big payouts: conditions
    def t3(r): return max([y for _,y,_ in r['pay'].get('三連単',[])] or [0])
    big=lambda r: t3(r)>=100000
    for lab,f in [('頭数',lambda r: r['n_runners']),('距離',lambda r:r['distance']),('馬場',lambda r:r.get('going')),
                  ('1人気の単勝配当帯',lambda r: None),
                  ('1人気の着',lambda r: next((min(e['fin'],4) for e in r['entries'] if e['pop']==1),None)),
                  ('季節',lambda r:r['date'][5:7])]:
        d=defaultdict(lambda:[0,0])
        for r in rs:
            k=f(r)
            if k is None: continue
            d[k][0]+=1; d[k][1]+=big(r)
        if d: print(' ',lab, ', '.join(f"{k}:{v[1]}/{v[0]}" for k,v in sorted(d.items(), key=lambda x:str(x[0]))))
    # formations
    def run(fn_t):
        res={}
        for h in ('前半','後半'):
            c=b=0; hit=0; n=0
            for r in rs:
                if r['half']!=h: continue
                P={e['pop']:e['num'] for e in r['entries']}
                T=fn_t(P)
                if not T: continue
                c+=100*len(T); bb=sum(A.pay(r,k,x) for k,x in T); b+=bb; hit+=bb>0; n+=1
            res[h]=(b/c if c else 0, hit/max(n,1), len(T))
        return res
    sel=lambda P,a,b:[P[i] for i in range(a,b+1) if i in P]
    S={
     '三連単 1人気を2-3着に固定・1着4-8人気・残り2-6人気': lambda P:[('三連単',(a,x,y)) for a in sel(P,4,8) for x,y in permutations(sel(P,1,6),2) if P.get(1) in (x,y) and a not in (x,y)],
     '三連単 1-2人気→3-7人気→3-7人気':lambda P:[('三連単',(a,x,y)) for a in sel(P,1,2) for x,y in permutations(sel(P,3,7),2)],
     '三連複 1人気-4〜9人気(2頭)':lambda P:[('三連複',(P[1],*c)) for c in combinations(sel(P,4,9),2)] if 1 in P else [],
     '三連複 1-2人気-4〜9人気':lambda P:[('三連複',(P[1],P[2],x)) for x in sel(P,4,9)] if 1 in P and 2 in P else [],
     '馬連 1人気-4〜9人気':lambda P:[('馬連',(P[1],x)) for x in sel(P,4,9)] if 1 in P else [],
     'ワイド 4〜9人気BOX':lambda P:[('ワイド',c) for c in combinations(sel(P,4,9),2)],
     '単勝 4〜9人気全部':lambda P:[('単勝',(x,)) for x in sel(P,4,9)],
     '複勝 10人気↓全部':lambda P:[('複勝',(P[i],)) for i in P if i>=10],
    }
    for k,f in S.items():
        r=run(f); print('  %-40s 前半%3.0f%% 後半%3.0f%% 的中%2.0f%% 点数%d'%(k,100*r['前半'][0],100*r['後半'][0],100*r['後半'][1],r['後半'][2]))
