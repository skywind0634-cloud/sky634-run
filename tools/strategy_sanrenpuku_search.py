"""3連複フォーメーションの探索: 前半（〜2026-03）で選び、後半（2026-04〜）で確かめる。"""
import json,sys,itertools,statistics as st
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from keiba.strategy import payout
races=sorted(json.load(open('data/cache/strategy_backtest.json')),key=lambda r:r['date'])
ratio=lambda h:h['p']/h['pm'] if h['pm'] else 0
bym=lambda hs:sorted(hs,key=lambda h:-h['p'])
def pops(r,a,b): return [h['num'] for h in r['horses'] if a<=h['pop']<=b]
COL1={
 'A(妙味条件厳格・4人気↓)': lambda r:[h['num'] for h in r['horses'] if h['pop']>=4 and h['seg']],
 'V(本線の妙味馬)': lambda r:[h['num'] for h in sorted([h for h in r['horses'] if 4<=h['pop']<=9 and ratio(h)>=1.3 and h['cond']>0],key=lambda h:-ratio(h))[:1]],
 'A∪V': lambda r:list(dict.fromkeys([h['num'] for h in r['horses'] if h['pop']>=4 and h['seg']]+[h['num'] for h in sorted([h for h in r['horses'] if 4<=h['pop']<=9 and ratio(h)>=1.3 and h['cond']>0],key=lambda h:-ratio(h))[:1]])),
 'モデル1位': lambda r:[bym(r['horses'])[0]['num']],
 '1番人気': lambda r:pops(r,1,1),
 '走る条件0.4↑(4〜9人気)上位1': lambda r:[h['num'] for h in sorted([h for h in r['horses'] if 4<=h['pop']<=9 and h['cond']>=0.4],key=lambda h:-ratio(h))[:1]],
}
COL2={
 '1〜2人気': lambda r,c1:pops(r,1,2), '1〜3人気': lambda r,c1:pops(r,1,3), '1〜4人気': lambda r,c1:pops(r,1,4),
 'モデル上位3': lambda r,c1:[h['num'] for h in bym([h for h in r['horses'] if h['num'] not in c1])[:3]],
 'モデル上位4': lambda r,c1:[h['num'] for h in bym([h for h in r['horses'] if h['num'] not in c1])[:4]],
}
def mats(r,c1):
    return [h['num'] for h in sorted([h for h in r['horses'] if h['pop']>=4 and (h['cond']>=0.4 or h['seg'] or ratio(h)>=1.3) and h['num'] not in c1],key=lambda h:-ratio(h))]
COL3={
 '1〜5人気': lambda r,c1,c2:pops(r,1,5), '1〜7人気': lambda r,c1,c2:pops(r,1,7), '4〜9人気': lambda r,c1,c2:pops(r,4,9),
 'モデル上位5': lambda r,c1,c2:[h['num'] for h in bym([h for h in r['horses'] if h['num'] not in c1])[:5]],
 'モデル上位7': lambda r,c1,c2:[h['num'] for h in bym([h for h in r['horses'] if h['num'] not in c1])[:7]],
 '2列目＋材料馬2頭': lambda r,c1,c2:c2+mats(r,c1)[:2],
 '2列目＋材料馬3頭': lambda r,c1,c2:c2+mats(r,c1)[:3],
}
def tickets(r,f1,f2,f3):
    c1=f1(r)
    if not c1: return []
    c2=f2(r,c1); c3=f3(r,c1,c2)
    out=set()
    for a in c1:
        for b in c2:
            for c in c3:
                if len({a,b,c})==3: out.add(tuple(sorted((a,b,c))))
    return [('三連複',t) for t in out]
def ev(fn,half):
    n=cost=back=hit=0; pays=[]; streak=mx=0
    for r in races:
        if (half=='前半')!=(r['date']<'2026-04-01'): continue
        T=fn(r)
        if not T or len(T)>20: continue
        b=sum(payout(k,t,r['pay']) for k,t in T); n+=1; cost+=100*len(T); back+=b
        if b: hit+=1; pays.append(b); streak=0
        else: streak+=1; mx=max(mx,streak)
    return n,(back/cost if cost else 0),(hit/n if n else 0),(st.median(pays) if pays else 0),mx,(cost/n/100 if n else 0)
rows=[]
for n1,f1 in COL1.items():
    for n2,f2 in COL2.items():
        for n3,f3 in COL3.items():
            fn=lambda r,f1=f1,f2=f2,f3=f3:tickets(r,f1,f2,f3)
            a=ev(fn,'前半')
            if a[0]<40: continue
            rows.append((n1,n2,n3,a,fn))
print('試した組み方', len(rows))
sel=[x for x in rows if x[3][1]>=1.2]
print('前半で回収率120%以上:', len(sel))
print(f"{'1列目':22s}{'2列目':10s}{'3列目':16s} {'R':>4} {'点':>5} | 前半 回収/的中 | 後半 回収/的中/払戻中央/連敗")
res=[]
for n1,n2,n3,a,fn in sel:
    b=ev(fn,'後半'); res.append((n1,n2,n3,a,b))
for n1,n2,n3,a,b in sorted(res,key=lambda x:-x[4][1]):
    print(f"{n1:22s}{n2:10s}{n3:16s} {a[0]+b[0]:4d} {a[5]:5.1f} | {a[1]:4.0%}/{a[2]:3.0%} | {b[1]:4.0%}/{b[2]:3.0%}/{b[3]:6.0f}/{b[4]}")
ok=[x for x in res if x[4][1]>=1.0]
print('後半も100%以上:', len(ok), '/', len(res))
# 偶然の基準: 1列目をランダムな4番人気以下1頭にした同型
import random
random.seed(1)
rnd=lambda r:[random.choice([h['num'] for h in r['horses'] if h['pop']>=4])] if any(h['pop']>=4 for h in r['horses']) else []
cnt=0;tot=0
for n2,f2 in COL2.items():
    for n3,f3 in COL3.items():
        fn=lambda r,f2=f2,f3=f3:tickets(r,rnd,f2,f3)
        a=ev(fn,'前半'); tot+=1; cnt+=a[1]>=1.2
print('参考: 1列目をランダムな4人気↓にした場合、前半120%以上になる組み方', cnt,'/',tot)
print('--- 採用候補を今の買い方に足した場合 ---')
A_=COL1['A(妙味条件厳格・4人気↓)']
def base(r):
    out=[]; fav={h['pop']:h['num'] for h in r['horses']}
    for a in A_(r):
        out.append(('単勝',(a,)))
        out+=[('ワイド',tuple(sorted((a,fav[p])))) for p in range(1,6) if p in fav and fav[p]!=a]
        out+=[('馬連',tuple(sorted((a,fav[p])))) for p in range(1,4) if p in fav and fav[p]!=a]
    return out
s1=lambda r:tickets(r,A_,COL2['1〜2人気'],COL3['モデル上位5'])
s2=lambda r:tickets(r,A_,COL2['1〜3人気'],COL3['モデル上位5'])
def ev2(fn):
    for half in ('前半','後半'):
        n=cost=back=hit=0;pays=[];streak=mx=0
        for r in races:
            if (half=='前半')!=(r['date']<'2026-04-01'): continue
            T=list(dict.fromkeys(fn(r)))
            if not T: continue
            b=sum(payout(k,t,r['pay']) for k,t in T); n+=1; cost+=100*len(T); back+=b
            if b: hit+=1; pays.append(b); streak=0
            else: streak+=1; mx=max(mx,streak)
        print(f"   {half}: {n}R 平均{cost/n/100:.1f}点 回収{back/cost:.0%} 的中{hit/n:.0%} 払戻中央{st.median(pays):.0f} 最大連敗{mx}")
print('今の買い方（単勝+ワイド+馬連）'); ev2(base)
print('＋3連複 A-1〜2人気-モデル上位5'); ev2(lambda r:base(r)+s1(r))
print('＋3連複 A-1〜3人気-モデル上位5'); ev2(lambda r:base(r)+s2(r))
