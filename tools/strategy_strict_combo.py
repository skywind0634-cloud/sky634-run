import json,sys,itertools,statistics as st
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from keiba.strategy import payout
races=json.load(open('data/cache/strategy_backtest.json'))
def ratio(h): return h['p']/h['pm'] if h['pm'] else 0
def A(r): return [h for h in r['horses'] if h['pop']>=4 and h['seg']]
def V(r):
    v=[h for h in r['horses'] if 4<=h['pop']<=9 and ratio(h)>=1.3 and h['cond']>0]
    return sorted(v,key=lambda h:-ratio(h))[:1]
def C(r): return [h for h in r['horses'] if 4<=h['pop']<=9 and h['cond']>=0.4]
def F(r,a=1,b=3): return [h for h in r['horses'] if a<=h['pop']<=b]
def axis_set(kind):
    return {'A':A,'V':V,'AV':lambda r:{h['num']:h for h in A(r)+V(r)}.values()}[kind]
def strat(name, fn):
    res={}
    for half in ('前半','後半'):
        cost=back=0; hits=0; nr=0; pays=[]; streak=mx=0; big=0
        for r in sorted(races,key=lambda r:r['date']):
            if (half=='前半')!=(r['date']<'2026-04-01'): continue
            T=fn(r)
            if not T: continue
            T=list(dict.fromkeys(T))
            c=100*len(T); b=sum(payout(k,h,r['pay']) for k,h in T)
            cost+=c; back+=b; nr+=1
            if b>0: hits+=1; pays.append(b); streak=0; big+=b>=2000
            else: streak+=1; mx=max(mx,streak)
        res[half]=(nr,cost,back,hits,pays,mx,big)
    a,b=res['前半'],res['後半']
    tot=lambda i: a[i]+b[i]
    roi=lambda x: x[2]/x[1] if x[1] else 0
    nr=tot(0); hit=tot(3)/max(nr,1); pays=a[4]+b[4]
    print(f"{name:42s} {nr:4d}R 点{tot(1)/max(nr,1)/100:4.1f} 回収 {roi(a):4.0%}/{roi(b):4.0%} 的中{hit:4.0%} 中央払戻{(st.median(pays) if pays else 0):6.0f} 2000円超的中{(a[6]+b[6])/max(nr,1):4.0%} 最大連敗{max(a[5],b[5])}")
def tk(kind,*hs): return (kind,tuple(sorted(hs)) if kind not in('単勝','複勝') else hs)
for ax in ('A','V','AV'):
    S=axis_set(ax)
    strat(f"[{ax}] 単勝", lambda r:[('単勝',(h['num'],)) for h in S(r)])
    strat(f"[{ax}] 複勝", lambda r:[('複勝',(h['num'],)) for h in S(r)])
    strat(f"[{ax}] ワイド 軸-1〜3人気", lambda r:[('ワイド',tuple(sorted((h['num'],f['num'])))) for h in S(r) for f in F(r)])
    strat(f"[{ax}] 馬連 軸-1〜3人気", lambda r:[('馬連',tuple(sorted((h['num'],f['num'])))) for h in S(r) for f in F(r)])
    strat(f"[{ax}] ワイド 軸-1〜5人気", lambda r:[('ワイド',tuple(sorted((h['num'],f['num'])))) for h in S(r) for f in F(r,1,5) if f['num']!=h['num']])
    strat(f"[{ax}] 3連複 軸-1〜3人気-1〜3人気", lambda r:[('三連複',tuple(sorted((h['num'],x['num'],y['num'])))) for h in S(r) for x,y in itertools.combinations(F(r),2)])
    strat(f"[{ax}] 3連複 軸-1〜3人気-4〜8人気", lambda r:[('三連複',tuple(sorted((h['num'],x['num'],y['num'])))) for h in S(r) for x in F(r) for y in F(r,4,8) if y['num']!=h['num']])
    strat(f"[{ax}] 単複+ワイド軸-1〜3人気", lambda r:[('単勝',(h['num'],)) for h in S(r)]+[('複勝',(h['num'],)) for h in S(r)]+[('ワイド',tuple(sorted((h['num'],f['num'])))) for h in S(r) for f in F(r)])
# 材料同士
def mats(r):
    m={h['num']:h for h in A(r)+V(r)+C(r)}
    return sorted(m.values(),key=lambda h:-ratio(h))[:4]
strat("材料同士 ワイドBOX(上位4頭まで)", lambda r:[('ワイド',tuple(sorted((x['num'],y['num'])))) for x,y in itertools.combinations(mats(r),2)])
strat("材料同士 馬連BOX(上位4頭まで)", lambda r:[('馬連',tuple(sorted((x['num'],y['num'])))) for x,y in itertools.combinations(mats(r),2)])
strat("材料1頭目-1〜3人気 ワイド", lambda r:[('ワイド',tuple(sorted((mats(r)[0]['num'],f['num'])))) for f in F(r)] if mats(r) else [])
print('--- パッケージ ---')
S=A
pk1=lambda r:[('単勝',(h['num'],)) for h in S(r)]+[('ワイド',tuple(sorted((h['num'],f['num'])))) for h in S(r) for f in F(r,1,5) if f['num']!=h['num']]
strat("A: 単勝+ワイド(1〜5人気)", pk1)
pk2=lambda r:pk1(r)+[('馬連',tuple(sorted((h['num'],f['num'])))) for h in S(r) for f in F(r)]
strat("A: 単勝+ワイド(1〜5人気)+馬連(1〜3人気)", pk2)
pk3=lambda r:pk2(r)+[('三連複',tuple(sorted((h['num'],x['num'],y['num'])))) for h in S(r) for x in F(r) for y in F(r,4,8) if y['num']!=h['num']]
strat("A: 上＋3連複(軸-1〜3人気-4〜8人気)", pk3)
strat("A: 複勝+ワイド(1〜5人気)+馬連(1〜3人気)", lambda r:[('複勝',(h['num'],)) for h in S(r)]+pk2(r)[len(S(r)):])
