"""7番人気以下の「材料の重なり」（走る条件0.4以上・妙味条件・★血統穴の数＋フラグ点）の検証と、穴ワイドの組み方（2026-10-17）.
データ: data/cache/strategy_backtest.json（2025-10〜2026-09・実払戻。前半/後半＝2026-04）＋ data/cache/flag_backtest_rows.json。
注意: 市場評価は人気順の擬似オッズ時代のキャッシュ。実オッズの補完後に作り直して再確認する。
使い方: python3 tools/longshot_stack.py"""
import json
from collections import defaultdict
sb=json.load(open('data/cache/strategy_backtest.json'))
fl=json.load(open('data/cache/flag_backtest_rows.json'))
F={(r['rid'],r['pop']):(r['plus'],r['minus']) for r in fl}
agg=defaultdict(lambda:[[0,0,0,0,0] for _ in range(2)])
for R in sb:
    hf=R['date']>='2026-04-01'
    tk={a:y for a,y in R['pay'].get('単勝',[])}; fk={a:y for a,y in R['pay'].get('複勝',[])}
    hs=[h for h in R['horses'] if h['fin'] is not None and h['pop']]
    longs=sorted([h for h in hs if h['pop']>=8],key=lambda h:-h['up'])
    star={h['num'] for h in longs[:3] if h['up']>=0.3 and h['up']>=0.6*longs[0]['up']}
    for h in hs:
        if h['pop']<7: continue
        pl,mi=F.get((R['race_id'],h['pop']),(0,0))
        pos=(h['cond']>=0.4)+(h['seg'] or h['edge']>0.15)+(h['num'] in star)
        net=pos+pl-mi
        for key in (('net',min(max(net,-1),6)),('pos材料',pos)):
            a=agg[key][hf];a[0]+=1;a[1]+=h['fin']<=3;a[2]+=h['fin']==1;a[3]+=tk.get(str(h['num']),0);a[4]+=fk.get(str(h['num']),0)
for k in sorted(agg):
    print(k,' | '.join(f"{a[0]}頭 3着内{a[1]/a[0]*100:.1f}% 勝{a[2]} 単回{a[3]/a[0]:.0f} 複回{a[4]/a[0]:.0f}" for a in agg[k]))

print("=== 穴ワイド・3連複")
import itertools
from collections import defaultdict
sb=json.load(open('data/cache/strategy_backtest.json'))
fl=json.load(open('data/cache/flag_backtest_rows.json'))
F={(r['rid'],r['pop']):(r['plus'],r['minus']) for r in fl}
def norm(c): return '-'.join(sorted([str(x) for x in c if str(x).isdigit()],key=int))
def P(R):
    return {k:{norm(a.replace('－','-').split('-')):y for a,y in v} for k,v in R['pay'].items()}
strat={}
def S(n):
    def d(f): strat[n]=f; return f
    return d
def prep(R,th):
    hs=[h for h in R['horses'] if h['fin'] is not None and h['pop']]
    longs=sorted([h for h in hs if h['pop']>=8],key=lambda h:-h['up'])
    star={h['num'] for h in longs[:3] if longs and h['up']>=0.3 and h['up']>=0.6*longs[0]['up']}
    L=[]
    for h in hs:
        if h['pop']<7: continue
        pl,mi=F.get((R['race_id'],h['pop']),(0,0))
        net=(h['cond']>=0.4)+(h['seg'] or h['edge']>0.15)+(h['num'] in star)+pl-mi
        if net>=th: L.append((net,h))
    L=[h for _,h in sorted(L,key=lambda x:(-x[0],x[1]['pop']))][:2]
    pop={h['pop']:h['num'] for h in hs}
    return L,pop
for th in (3,4):
    @S(f'複勝 穴(net≥{th})')
    def a(R,th=th):
        L,pop=prep(R,th); return [('複勝',norm([h['num']])) for h in L]
    @S(f'ワイド 1人気-穴(net≥{th})')
    def b(R,th=th):
        L,pop=prep(R,th); return [('ワイド',norm([pop[1],h['num']])) for h in L if 1 in pop]
    @S(f'ワイド 1〜3人気-穴(net≥{th})')
    def c(R,th=th):
        L,pop=prep(R,th); return [('ワイド',norm([pop[p],h['num']])) for h in L for p in (1,2,3) if p in pop]
    @S(f'3連複 1〜3人気2頭-穴(net≥{th})')
    def d(R,th=th):
        L,pop=prep(R,th); return [('3連複',norm([pop[x],pop[y],h['num']])) for h in L for x,y in ((1,2),(1,3),(2,3)) if x in pop and y in pop]
    @S(f'3連複 穴-1〜2人気-1〜6人気(net≥{th})')
    def e(R,th=th):
        L,pop=prep(R,th); out=set()
        for h in L:
            for x in (1,2):
                for y in range(1,7):
                    if x!=y and x in pop and y in pop: out.add(('3連複',norm([pop[x],pop[y],h['num']])))
        return list(out)
agg=defaultdict(lambda:[[0,0,0,0,[]] for _ in range(2)])
for R in sb:
    hf=R['date']>='2026-04-01'; pp=P(R)
    for n,f in strat.items():
        bs=f(R)
        if not bs: continue
        ret=sum(pp.get(k,{}).get(c,0) for k,c in bs)
        a=agg[n][hf];a[0]+=1;a[1]+=len(bs);a[2]+=ret>0;a[3]+=ret
        if ret: a[4].append(ret)
for n in strat:
    A=agg[n]
    print(f"{n}: "+' | '.join(f"{a[0]}R {a[1]}点 的中{a[2]/max(a[0],1)*100:.0f}% 回収{a[3]/max(a[1]*100,1)*100:.0f}% 中央払戻{sorted(a[4])[len(a[4])//2] if a[4] else 0}" for a in A))
