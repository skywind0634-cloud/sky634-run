"""直結コースの好走歴を『ヒモ（相手・3列目）』に使うと、的中率と回収率はどう変わるか（過去1年・実払戻）。
直結コースの組は 2023年までのデータで選んだもの（data/knowledge/chokketsu_map.json）で、検証期間とは重ならない。"""
import json,sys,itertools,statistics as st,random,sqlite3,collections
sys.path.insert(0,'.')
from keiba.strategy import payout
exec(open('tools/chokketsu_analysis.py').read().split("# 発見期間で (T,K) の A/E")[0].replace("'data/keiba.db'","'data/keiba.db'"))
chok={k:set(v) for k,v in json.load(open('data/knowledge/chokketsu_map.json')).items()}
idx={(r[0],r[1]):r for r in recs}
races=sorted(json.load(open('data/cache/strategy_backtest.json')),key=lambda r:r['date'])
def is_ck(r,h):
    x=idx.get((r['race_id'],h['num'])); return bool(x and chok.get(x[3],set())&x[7])
P=lambda r,a,b:[h['num'] for h in r['horses'] if a<=h['pop']<=b]
A=lambda r:[h['num'] for h in r['horses'] if h['pop']>=4 and h['seg']]
ck_long=lambda r,lo=5:[h['num'] for h in r['horses'] if h['pop']>=lo and is_ck(r,h)]
rnd_long=lambda r,k,lo=5:random.sample([h['num'] for h in r['horses'] if h['pop']>=lo and not is_ck(r,h)],min(k,len([1 for h in r['horses'] if h['pop']>=lo and not is_ck(r,h)])))
def form(c1,c2,c3,kind='三連複'):
    out=set()
    for a in c1:
        for b in c2:
            for c in c3:
                if len({a,b,c})==3: out.add(tuple(sorted((a,b,c))))
    return [(kind,t) for t in out]
def ev(name,fn,cond=lambda r:True):
    res=[]
    for half in ('前半','後半'):
        n=cost=back=hit=0;pays=[]
        for r in races:
            if (half=='前半')!=(r['date']<'2026-04-01') or not cond(r): continue
            T=list(dict.fromkeys(fn(r)))
            if not T: continue
            b=sum(payout(k,t,r['pay']) for k,t in T); n+=1;cost+=100*len(T);back+=b;hit+=b>0
            if b: pays.append(b)
        res.append((n,back/max(cost,1),hit/max(n,1),(st.median(pays) if pays else 0),cost/max(n,1)/100))
    a,b=res
    print(f"{name:58s} {a[0]+b[0]:4d}R {a[4]:4.1f}点 | 回収 {a[1]:4.0%}/{b[1]:4.0%} 的中 {a[2]:3.0%}/{b[2]:3.0%} 払戻中央 {a[3]:5.0f}/{b[3]:5.0f}")
random.seed(3)
has_ck=lambda r: bool(ck_long(r))
print('== 3着内率: 直結好走歴あり vs なし（同じ人気帯, 過去1年） ==')
for lo,hi in ((4,6),(7,9),(10,18)):
    a=[0,0];b=[0,0]
    for r in races:
        for h in r['horses']:
            if lo<=h['pop']<=hi:
                x=a if is_ck(r,h) else b; x[0]+=1; x[1]+=h['fin'] is not None and h['fin']<=3
    print(f"  {lo}〜{hi}番人気: 直結あり {a[1]}/{a[0]}={a[1]/max(a[0],1):.1%}  なし {b[1]}/{b[0]}={b[1]/max(b[0],1):.1%}")
print('== 人気サイドの軸＋ヒモに直結の人気薄（5番人気以下）を入れる ==')
ev('3連複 1〜2人気 - 1〜4人気 - 1〜4人気（比較・ヒモなし）', lambda r:form(P(r,1,2),P(r,1,4),P(r,1,4)), has_ck)
ev('3連複 1〜2人気 - 1〜4人気 - 直結の人気薄', lambda r:form(P(r,1,2),P(r,1,4),ck_long(r)), has_ck)
ev('  （比較）同じ数のランダムな人気薄', lambda r:form(P(r,1,2),P(r,1,4),rnd_long(r,len(ck_long(r)))), has_ck)
ev('3連複 1人気 - 2〜4人気 - 直結の人気薄', lambda r:form(P(r,1,1),P(r,2,4),ck_long(r)), has_ck)
ev('  （比較）同じ数のランダムな人気薄', lambda r:form(P(r,1,1),P(r,2,4),rnd_long(r,len(ck_long(r)))), has_ck)
ev('ワイド 1〜2人気 - 直結の人気薄', lambda r:[('ワイド',tuple(sorted((a,c)))) for a in P(r,1,2) for c in ck_long(r)], has_ck)
ev('  （比較）同じ数のランダムな人気薄', lambda r:[('ワイド',tuple(sorted((a,c)))) for a in P(r,1,2) for c in rnd_long(r,len(ck_long(r)))], has_ck)
print('== 妙味条件(厳格)軸の3連複の3列目に直結の人気薄を足す ==')
ev('3連複 A - 1〜2人気 - モデル上位5（今の買い方）', lambda r:form(A(r),P(r,1,2),[h['num'] for h in sorted(r['horses'],key=lambda h:-h['p']) if h['num'] not in A(r)][:5]))
ev('3連複 A - 1〜2人気 - モデル上位5＋直結の人気薄', lambda r:form(A(r),P(r,1,2),[h['num'] for h in sorted(r['horses'],key=lambda h:-h['p']) if h['num'] not in A(r)][:5]+ck_long(r)))
ev('ワイド A - 直結の人気薄', lambda r:[('ワイド',tuple(sorted((a,c)))) for a in A(r) for c in ck_long(r) if c!=a])
