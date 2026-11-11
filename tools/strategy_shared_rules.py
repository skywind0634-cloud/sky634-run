import json,sys,itertools,sqlite3,statistics as st
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from keiba.strategy import payout
races=json.load(open('data/cache/strategy_backtest.json'))
db=sqlite3.connect('data/keiba.db')
meta={r[0]:r[1:] for r in db.execute("select race_id,surface,distance,grade,name,n_runners from races")}
# 前走（人気・着順）
hid={(a,b):c for a,b,c in db.execute("select race_id,number,horse_id from results")}
hist={}
for h,d,p,f in db.execute("select r.horse_id, ra.date, r.popularity, r.finish from results r join races ra using(race_id) order by ra.date"):
    hist.setdefault(h,[]).append((d,p,f))
def prev(r,h):
    x=hid.get((r['race_id'],h['num']))
    if not x: return None
    ps=[t for t in hist.get(x,[]) if t[0]<r['date']]
    return ps[-1] if ps else None
def pay3t(combo,pay):
    for c,y in pay.get('3連単',[]):
        if [int(v) for v in str(c).replace('→','-').split('-')]==list(combo): return y
    return 0
def pp(kind,t,pay): return pay3t(t,pay) if kind=='三連単' else payout(kind,t,pay)
def run(name,fn,filt=lambda r:True):
    res={}
    for half in ('前半','後半'):
        n=cost=back=hit=0; pays=[]; streak=mx=0
        for r in sorted(races,key=lambda r:r['date']):
            if (half=='前半')!=(r['date']<'2026-04-01') or not filt(r): continue
            T=fn(r)
            if not T: continue
            T=list(dict.fromkeys(T))
            b=sum(pp(k,t,r['pay']) for k,t in T); n+=1; cost+=100*len(T); back+=b
            if b: hit+=1; pays.append(b); streak=0
            else: streak+=1; mx=max(mx,streak)
        res[half]=(n,cost,back,hit,pays,mx)
    a,b=res['前半'],res['後半']; n=a[0]+b[0]; pays=a[4]+b[4]
    print(f"{name:52s} {n:4d}R {(a[1]+b[1])/max(n,1)/100:5.1f}点 回収 {a[2]/max(a[1],1):4.0%}/{b[2]/max(b[1],1):4.0%} 的中{(a[3]+b[3])/max(n,1):4.0%} 払戻中央{(st.median(pays) if pays else 0):6.0f} 連敗{max(a[5],b[5])}")
P=lambda r,a,b:[h for h in r['horses'] if a<=h['pop']<=b]
bym=lambda hs:sorted(hs,key=lambda h:-h['p'])
def axis(r):  # 中穴軸: 2〜5番人気・単勝5倍以上でモデル勝率最上位
    c=[h for h in r['horses'] if 2<=h['pop']<=5 and (h['odds'] or 0)>=5]
    return bym(c)[:1]
def A(r): return [h for h in r['horses'] if h['pop']>=4 and h['seg']]
def f135(axes,r):
    out=[]
    for a in axes:
        o=bym([h for h in r['horses'] if h['num']!=a['num']])
        g2=o[:3]; g3=o[:3]+[h for h in o if h['pop']>=6][:2]
        for x in g2:
            for y in g3:
                if x['num']!=y['num']: out.append(tri(a['num'],x['num'],y['num']))
    return out
def tri(*x): return ('三連複',tuple(sorted(x)))
filtA=lambda r: meta.get(r['race_id'],(0,0,''))[2] in ('3勝','OP','L','G3','G2','G1')
filtB=lambda r: (lambda m: m and m[0]=='芝' and 1800<=m[1]<=2200)(meta.get(r['race_id']))
filtC=lambda r: filtA(r) and filtB(r)
print('== 単勝 ==')
run('単勝 10.0〜19.9倍 全部', lambda r:[('単勝',(h['num'],)) for h in r['horses'] if h['odds'] and 10<=h['odds']<20])
run('単勝 10〜19.9倍 × 前走1〜2人気で4着以下', lambda r:[('単勝',(h['num'],)) for h in r['horses'] if h['odds'] and 10<=h['odds']<20 and (lambda p:p and p[1] and p[1]<=2 and p[2] and p[2]>=4)(prev(r,h))])
run('単勝 10〜19.9倍 × モデル人気比1.3以上', lambda r:[('単勝',(h['num'],)) for h in r['horses'] if h['odds'] and 10<=h['odds']<20 and h['pm'] and h['p']/h['pm']>=1.3])
run('単勝 10〜19.9倍 × 妙味条件(厳格)', lambda r:[('単勝',(h['num'],)) for h in A(r) if h['odds'] and 10<=h['odds']<20])
print('== 中穴軸（2〜5人気・5倍以上・モデル最上位） ==')
for lab,f in (('全レース',lambda r:True),('3勝以上',filtA),('芝1800-2200',filtB),('3勝以上×芝1800-2200',filtC)):
    run(f'[{lab}] ワイド 軸→モデル上位2頭(2点)', lambda r:[('ワイド',tuple(sorted((a['num'],o['num'])))) for a in axis(r) for o in bym([h for h in r['horses'] if h['num']!=a['num']])[:2]], f)
    run(f'[{lab}] 3連複 軸1頭→モデル上位5頭流し(10点)', lambda r:[tri(a['num'],x['num'],y['num']) for a in axis(r) for x,y in itertools.combinations(bym([h for h in r['horses'] if h['num']!=a['num']])[:5],2)], f)
    run(f'[{lab}] 3連複 1-3-5（軸/上位3/上位3＋穴2）', lambda r:f135(axis(r),r), f)
print('== 376 フォーメーション（1〜3人気/1〜7人気/4〜9人気） ==')
for lab,f in (('全レース',lambda r:True),('3勝以上',filtA),('芝1800-2200',filtB)):
    run(f'[{lab}] 3連複 376', lambda r:list({tri(a['num'],b['num'],c['num']) for a in P(r,1,3) for b in P(r,1,7) for c in P(r,4,9) if len({a['num'],b['num'],c['num']})==3}), f)
print('== 妙味条件(厳格)A を軸にした同じ形 ==')
run('A軸 ワイド→モデル上位2頭', lambda r:[('ワイド',tuple(sorted((a['num'],o['num'])))) for a in A(r) for o in bym([h for h in r['horses'] if h['num']!=a['num']])[:2]])
run('A軸 3連複→モデル上位5頭流し', lambda r:[tri(a['num'],x['num'],y['num']) for a in A(r) for x,y in itertools.combinations(bym([h for h in r['horses'] if h['num']!=a['num']])[:5],2)])
run('A軸 3連複 1-3-5', lambda r:f135(A(r),r))
print('== 3連単 2着固定（2着型＝モデル複勝寄り: 勝率は低いが3着内率が高い馬） ==')
def second(r):
    c=[h for h in r['horses'] if 2<=h['pop']<=6]
    return sorted(c,key=lambda h:-(h['p']/max(h['pm'],1e-6)))[:1]
run('3連単 1着モデル上位3×2着固定×3着上位6(18点)', lambda r:[('三連単',(x['num'],s['num'],z['num'])) for s in second(r) for x in bym([h for h in r['horses'] if h['num']!=s['num']])[:3] for z in bym([h for h in r['horses'] if h['num']!=s['num']])[:7] if x['num']!=z['num']])
run('3連単 2着にA固定×1着1〜3人気×3着1〜6人気', lambda r:[('三連単',(x['num'],a['num'],z['num'])) for a in A(r) for x in P(r,1,3) for z in P(r,1,6) if len({x['num'],a['num'],z['num']})==3])
print('== 採用パッケージ（A軸: 単勝＋ワイド1〜5人気＋馬連1〜3人気）をレース条件・オッズ帯で分ける ==')
def pkg(r,oddsf=lambda h:True):
    out=[]
    fav={h['pop']:h['num'] for h in r['horses']}
    for a in A(r):
        if not oddsf(a): continue
        out.append(('単勝',(a['num'],)))
        out+=[('ワイド',tuple(sorted((a['num'],fav[p])))) for p in range(1,6) if p in fav and fav[p]!=a['num']]
        out+=[('馬連',tuple(sorted((a['num'],fav[p])))) for p in range(1,4) if p in fav and fav[p]!=a['num']]
    return out
run('パッケージ 全部', pkg)
run('パッケージ 1勝・2勝クラス', pkg, lambda r: not filtA(r))
run('パッケージ 3勝以上', pkg, filtA)
run('パッケージ 軸の単勝 5〜9.9倍', lambda r:pkg(r,lambda h:h['odds'] and 5<=h['odds']<10))
run('パッケージ 軸の単勝 10〜19.9倍', lambda r:pkg(r,lambda h:h['odds'] and 10<=h['odds']<20))
run('パッケージ 軸の単勝 20倍以上', lambda r:pkg(r,lambda h:h['odds'] and h['odds']>=20))
