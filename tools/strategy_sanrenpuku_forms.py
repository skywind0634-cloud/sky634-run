import json,sys,itertools,statistics as st
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from keiba.strategy import payout
races=json.load(open('data/cache/strategy_backtest.json'))
def P(r,a,b): return [h['num'] for h in r['horses'] if a<=h['pop']<=b]
def pop(r,k): return next((h['num'] for h in r['horses'] if h['pop']==k),None)
def A(r): return [h['num'] for h in r['horses'] if h['pop']>=4 and h['seg']]
def tri(x): return ('三連複',tuple(sorted(x)))
def form(r,g1,g2,g3):
    out=set()
    for a in g1:
        for b in g2:
            for c in g3:
                if len({a,b,c})==3: out.add(tuple(sorted((a,b,c))))
    return [('三連複',t) for t in out]
def run(name,fn,filt=lambda r:True):
    res={}
    for half in ('前半','後半'):
        n=cost=back=hit=0; pays=[]; streak=mx=0
        for r in sorted(races,key=lambda r:r['date']):
            if (half=='前半')!=(r['date']<'2026-04-01') or not filt(r): continue
            T=fn(r)
            if not T: continue
            b=sum(payout(k,t,r['pay']) for k,t in T); n+=1; cost+=100*len(T); back+=b
            if b: hit+=1; pays.append(b); streak=0
            else: streak+=1; mx=max(mx,streak)
        res[half]=(n,cost,back,hit,pays,mx)
    a,b=res['前半'],res['後半']; n=a[0]+b[0]; pays=a[4]+b[4]
    print(f"{name:44s} {n:4d}R 平均{(a[1]+b[1])/max(n,1)/100:5.1f}点 回収 {a[2]/max(a[1],1):4.0%}/{b[2]/max(b[1],1):4.0%} 的中{(a[3]+b[3])/max(n,1):4.0%} 払戻中央{(st.median(pays) if pays else 0):6.0f} 最大連敗{max(a[5],b[5])}")
run("3連複 1人気軸-2〜6人気-2〜6人気(10点)", lambda r:form(r,[pop(r,1)],P(r,2,6),P(r,2,6)))
run("3連複 1〜2人気-1〜4人気-1〜8人気", lambda r:form(r,P(r,1,2),P(r,1,4),P(r,1,8)))
run("3連複 1・2人気2頭軸-3〜10人気(8点)", lambda r:form(r,[pop(r,1)],[pop(r,2)],P(r,3,10)))
run("3連複 BOX 1〜5人気(10点)", lambda r:form(r,P(r,1,5),P(r,1,5),P(r,1,5)))
run("3連複 1〜3人気-1〜6人気-1〜10人気", lambda r:form(r,P(r,1,3),P(r,1,6),P(r,1,10)))
run("3連複 1人気軸-2〜10人気総流し(36点)", lambda r:form(r,[pop(r,1)],P(r,2,10),P(r,2,10)))
print('--- 妙味条件(厳格)の馬を絡める ---')
run("3連複 A軸-1〜3人気-1〜6人気", lambda r:form(r,A(r),P(r,1,3),P(r,1,6)) if A(r) else [])
run("3連複 A＋1人気の2頭軸-2〜8人気", lambda r:form(r,A(r),[pop(r,1)],P(r,2,8)) if A(r) else [])
run("3連複 A軸-1〜4人気-1〜4人気(6点)", lambda r:form(r,A(r),P(r,1,4),P(r,1,4)) if A(r) else [])
run("3連複 1〜2人気-1〜4人気-A,1〜8人気", lambda r:form(r,P(r,1,2),P(r,1,4),P(r,1,8)+A(r)) if A(r) else [])
