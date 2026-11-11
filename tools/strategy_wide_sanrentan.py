"""資料のワイド（1〜2点・想定5倍以上）と3連単（2着固定）の検証。前半で選び後半で確認。"""
import json,sys,itertools,sqlite3,statistics as st
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from keiba.strategy import payout
races=sorted(json.load(open('data/cache/strategy_backtest.json')),key=lambda r:r['date'])
db=sqlite3.connect('data/keiba.db')
hid={(a,b):c for a,b,c in db.execute("select race_id,number,horse_id from results")}
hist={}
for h,d,f in db.execute("select r.horse_id, ra.date, r.finish from results r join races ra using(race_id) where r.finish is not null order by ra.date"):
    hist.setdefault(h,[]).append((d,f))
ratio=lambda h:h['p']/h['pm'] if h['pm'] else 0
bym=lambda hs:sorted(hs,key=lambda h:-h['p'])
def top3_probs(r):
    """市場の勝率(pm)から Harville で各ペアが両方3着内に入る確率."""
    hs=[h for h in r['horses'] if h['pm']]
    z=sum(h['pm'] for h in hs); p={h['num']:h['pm']/z for h in hs}
    pair={}
    ks=list(p)
    for a in ks:
        for b in ks:
            if b==a: continue
            pab=p[a]*p[b]/(1-p[a])
            for c in ks:
                if c in (a,b): continue
                pr=pab*p[c]/(1-p[a]-p[b])
                for x,y in ((a,b),(a,c),(b,c)):
                    k=tuple(sorted((x,y))); pair[k]=pair.get(k,0)+pr
    return pair
def pay3t(combo,pay):
    for c,y in pay.get('3連単',[]):
        if [int(v) for v in str(c).replace('→','-').split('-')]==list(combo): return y
    return 0
pp=lambda k,t,pay: pay3t(t,pay) if k=='三連単' else payout(k,t,pay)
def ev(fn,half):
    n=cost=back=hit=0;pays=[];streak=mx=0
    for r in races:
        if (half=='前半')!=(r['date']<'2026-04-01'): continue
        T=list(dict.fromkeys(fn(r)))
        if not T: continue
        b=sum(pp(k,t,r['pay']) for k,t in T); n+=1; cost+=100*len(T); back+=b
        if b: hit+=1; pays.append(b); streak=0
        else: streak+=1; mx=max(mx,streak)
    return n,(back/cost if cost else 0),(hit/n if n else 0),(st.median(pays) if pays else 0),mx,(cost/n/100 if n else 0)
AX={
 'A(妙味条件厳格)': lambda r:[h for h in r['horses'] if h['pop']>=4 and h['seg']],
 'V(本線の妙味馬)': lambda r:sorted([h for h in r['horses'] if 4<=h['pop']<=9 and ratio(h)>=1.3 and h['cond']>0],key=lambda h:-ratio(h))[:1],
 '中穴(2〜5人気5倍↑)モデル最上位': lambda r:bym([h for h in r['horses'] if 2<=h['pop']<=5 and (h['odds'] or 0)>=5])[:1],
 'モデル1位': lambda r:bym(r['horses'])[:1],
}
PART={
 '1番人気': lambda r,a:[h for h in r['horses'] if h['pop']==1 and h['num']!=a['num']],
 '1〜2人気': lambda r,a:[h for h in r['horses'] if h['pop']<=2 and h['num']!=a['num']],
 'モデル上位1': lambda r,a:bym([h for h in r['horses'] if h['num']!=a['num']])[:1],
 'モデル上位2': lambda r,a:bym([h for h in r['horses'] if h['num']!=a['num']])[:2],
 '想定5倍以上でモデル上位2': None,
}
print('=== ワイド（1〜2点） ===')
cache={}
def wide(r,axf,pn,minodds=0):
    out=[]
    if minodds:
        if r['race_id'] not in cache: cache[r['race_id']]=top3_probs(r)
        pr=cache[r['race_id']]
    for a in axf(r):
        if pn=='想定5倍以上でモデル上位2':
            c=[h for h in bym([h for h in r['horses'] if h['num']!=a['num']]) if 0.775/max(pr.get(tuple(sorted((a['num'],h['num']))),1e-9),1e-9)>=5][:2]
        else:
            c=PART[pn](r,a)
            if minodds: c=[h for h in c if 0.775/max(pr.get(tuple(sorted((a['num'],h['num']))),1e-9),1e-9)>=minodds]
        out+=[('ワイド',tuple(sorted((a['num'],h['num'])))) for h in c]
    return out
rows=[]
for an,af in AX.items():
    for pn in PART:
        for mo in ((0,5) if pn!='想定5倍以上でモデル上位2' else (5,)):
            fn=lambda r,af=af,pn=pn,mo=mo: wide(r,af,pn,mo)
            a=ev(fn,'前半'); b=ev(fn,'後半')
            rows.append((f"{an} → {pn}{'（想定5倍以上だけ）' if mo and pn!='想定5倍以上でモデル上位2' else ''}",a,b))
for name,a,b in rows:
    print(f"{name:52s} {a[0]+b[0]:4d}R {a[5]:4.1f}点 | 前半 {a[1]:4.0%}/的中{a[2]:3.0%} | 後半 {b[1]:4.0%}/的中{b[2]:3.0%} 払戻中央{b[3]:5.0f} 連敗{max(a[4],b[4])}")
print('=== 3連単 2着固定（資料: 1着3×2着1×3着6=18点、1着6×2着1×3着4=24点） ===')
def career(r,h):
    x=hid.get((r['race_id'],h['num']))
    ps=[f for d,f in hist.get(x,[]) if d<r['date']] if x else []
    return ps
def second_type(r):
    """勝ち切れないが2着に来る型: 過去4走以上・3着内率40%以上・3着内のうち1着が25%以下（4〜9人気）."""
    out=[]
    for h in r['horses']:
        if not 2<=h['pop']<=9: continue
        ps=career(r,h)
        if len(ps)<4: continue
        t3=sum(1 for f in ps if f<=3); w=sum(1 for f in ps if f==1)
        if t3/len(ps)>=0.4 and w<=0.25*t3: out.append(h)
    return sorted(out,key=lambda h:-h['p'])[:1]
SEC={'2着型(勝ち切れない馬)':second_type,'A(妙味条件厳格)':AX['A(妙味条件厳格)'],'V(本線の妙味馬)':AX['V(本線の妙味馬)']}
FIRST={'1〜3人気':lambda r,s:[h for h in r['horses'] if h['pop']<=3 and h['num']!=s['num']],
       'モデル上位3':lambda r,s:bym([h for h in r['horses'] if h['num']!=s['num']])[:3],
       'モデル上位6':lambda r,s:bym([h for h in r['horses'] if h['num']!=s['num']])[:6]}
THIRD={'1〜6人気':lambda r,s:[h for h in r['horses'] if h['pop']<=6 and h['num']!=s['num']],
       'モデル上位4':lambda r,s:bym([h for h in r['horses'] if h['num']!=s['num']])[:4],
       'モデル上位6':lambda r,s:bym([h for h in r['horses'] if h['num']!=s['num']])[:6]}
for sn,sf in SEC.items():
    for fn_,ff in FIRST.items():
        for tn,tf in THIRD.items():
            def T(r,sf=sf,ff=ff,tf=tf):
                out=[]
                for s in sf(r):
                    for x in ff(r,s):
                        for z in tf(r,s):
                            if z['num']!=x['num']: out.append(('三連単',(x['num'],s['num'],z['num'])))
                return out[:30]
            a=ev(T,'前半'); b=ev(T,'後半')
            print(f"2着={sn:14s} 1着={fn_:8s} 3着={tn:8s} {a[0]+b[0]:4d}R {a[5]:4.1f}点 | 前半 {a[1]:4.0%}/的中{a[2]:3.0%} | 後半 {b[1]:4.0%}/的中{b[2]:3.0%} 払戻中央{b[3]:6.0f} 連敗{max(a[4],b[4])}")
