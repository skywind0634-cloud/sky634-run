"""前走『勝ち馬から0.6秒差以内の4着以下』の馬は、次走（同条件・クラス落ち）で3着内に来るか。"""
import sqlite3,collections,sys
db=sqlite3.connect('data/keiba.db')
rows=db.execute("""select r.race_id, ra.date, ra.surface, ra.distance, ra.grade, ra.course, ra.n_runners,
  r.horse_id, r.finish, r.popularity, r.odds, r.time_sec from results r join races ra using(race_id)
  where r.finish is not null and ra.surface in ('芝','ダ') order by ra.date""").fetchall()
win_t={}
for rid,d,sf,dist,g,c,n,h,f,p,o,t in rows:
    if f==1 and t: win_t[rid]=t
G={'1勝':1,'2勝':2,'3勝':3,'OP':4,'L':4,'G3':5,'G2':6,'G1':7}
last={}
recs=[]
for rid,d,sf,dist,g,c,n,h,f,p,o,t in rows:
    pv=last.get(h)
    if pv and p:
        recs.append((d,sf,dist,g,c,f,p,o,pv))
    gap=(t-win_t[rid]) if t and rid in win_t else None
    last[h]=dict(date=d,sf=sf,dist=dist,g=g,c=c,fin=f,gap=gap)
# 人気ごとの3着内率（全期間）
base=collections.defaultdict(lambda:[0,0])
for d,sf,dist,g,c,f,p,o,pv in recs: b=base[min(p,12)]; b[0]+=1; b[1]+=f<=3
exp={k:v[1]/v[0] for k,v in base.items()}
def band(x): return '短距離(〜1400)' if x<=1400 else 'マイル〜中距離(1500〜2000)' if x<=2000 else '長距離(2100〜)'
def acc(filt,label):
    out={}
    for per,(lo,hi) in (('〜2022',('0','2023')),('2023-24',('2023','2025')),('2025〜',('2025','9'))):
        n=t3=w=0; e=0.0; ret=0.0
        for d,sf,dist,g,c,f,p,o,pv in recs:
            if not (lo<=d<hi) or not filt(sf,dist,g,c,pv,p): continue
            n+=1; t3+=f<=3; e+=exp[min(p,12)]; w+=f==1; ret+=(o*100 if f==1 and o else 0)
        out[per]=(n,t3,e,ret)
    tot=[sum(v[i] for v in out.values()) for i in range(4)]
    s=" | ".join(f"{k}: {v[0]}頭 A/E{(v[1]/v[2] if v[2] else 0):.2f} 単{(v[3]/v[0] if v[0] else 0):.0f}%" for k,v in out.items())
    print(f"{label:58s} 計{tot[0]:5d}頭 3着内{tot[1]/max(tot[0],1):.0%} A/E{tot[1]/max(tot[2],1):.2f} 単回収{tot[3]/max(tot[0],1):.0f}% || {s}")
same=lambda sf,dist,pv: pv['sf']==sf and pv['dist']==dist
down=lambda g,pv: G.get(g,0)<G.get(pv['g'],0)
eqcls=lambda g,pv: G.get(g,0)==G.get(pv['g'],0)
close=lambda pv,lo,hi: pv['fin'] and pv['fin']>=4 and pv['gap'] is not None and lo<=pv['gap']<=hi
print('=== 前走4着以下の勝ち馬とのタイム差別（全条件・次走全部） ===')
for lo,hi in ((0,0.2),(0.3,0.4),(0.5,0.6),(0.7,1.0),(1.1,9)):
    acc(lambda sf,dist,g,c,pv,p,lo=lo,hi=hi: close(pv,lo,hi), f'前走4着以下・{lo}〜{hi}秒差')
print('=== 前走0.6秒差以内の4着以下 × 次走の条件 ===')
acc(lambda sf,dist,g,c,pv,p: close(pv,0,0.6), '次走 全部')
acc(lambda sf,dist,g,c,pv,p: close(pv,0,0.6) and same(sf,dist,pv) and eqcls(g,pv), '次走 同じ芝ダ・同距離・同クラス')
acc(lambda sf,dist,g,c,pv,p: close(pv,0,0.6) and same(sf,dist,pv) and down(g,pv), '次走 同じ芝ダ・同距離・クラス落ち')
acc(lambda sf,dist,g,c,pv,p: close(pv,0,0.6) and down(g,pv), '次走 クラス落ち（条件問わず）')
acc(lambda sf,dist,g,c,pv,p: close(pv,0,0.6) and (same(sf,dist,pv) and (eqcls(g,pv) or down(g,pv))), '次走 同条件（同クラス or クラス落ち）')
acc(lambda sf,dist,g,c,pv,p: close(pv,0.7,9) and (same(sf,dist,pv) and (eqcls(g,pv) or down(g,pv))), '（比較）0.7秒差以上 × 同条件')
print('=== 同条件（同クラス or クラス落ち）× 距離帯 × 芝ダ ===')
for sfx in ('芝','ダ'):
    for bd in ('短距離(〜1400)','マイル〜中距離(1500〜2000)','長距離(2100〜)'):
        acc(lambda sf,dist,g,c,pv,p,sfx=sfx,bd=bd: sf==sfx and band(dist)==bd and close(pv,0,0.6) and same(sf,dist,pv) and (eqcls(g,pv) or down(g,pv)), f'{sfx} {bd} 0.6秒差以内')
        acc(lambda sf,dist,g,c,pv,p,sfx=sfx,bd=bd: sf==sfx and band(dist)==bd and close(pv,0.7,9) and same(sf,dist,pv) and (eqcls(g,pv) or down(g,pv)), f'   （比較）{sfx} {bd} 0.7秒差以上')
print('=== 人気帯別（0.6秒差以内・同条件） ===')
for lo,hi in ((1,3),(4,6),(7,9),(10,18)):
    acc(lambda sf,dist,g,c,pv,p,lo=lo,hi=hi: lo<=p<=hi and close(pv,0,0.6) and same(sf,dist,pv) and (eqcls(g,pv) or down(g,pv)), f'{lo}〜{hi}番人気')
print('=== 過去1年（実払戻あり）: 0.6秒差以内の4着以下・同条件（同クラスorクラス落ち）× 人気帯の単勝・複勝回収率 ===')
import json
sys.path.insert(0, '.')
from keiba.strategy import payout
cache=json.load(open('data/cache/strategy_backtest.json'))
num2h={(a,b):c for a,b,c in db.execute("select race_id,number,horse_id from results")}
meta={r[0]:r[1:] for r in db.execute("select race_id,surface,distance,grade,date from races")}
# 各馬の前走（レースごと）
prevs={}
lastp={}
for rid,d,sf,dist,g,c,n,h,f,p,o,t in rows:
    prevs[(rid,h)]=lastp.get(h)
    gap=(t-win_t[rid]) if t and rid in win_t else None
    lastp[h]=dict(sf=sf,dist=dist,g=g,fin=f,gap=gap)
for lo,hi,lab in ((4,6,'4〜6番人気'),(7,9,'7〜9番人気'),(10,18,'10番人気以下'),(4,18,'4番人気以下全部')):
    for half in ('前半','後半'):
        n=w=pl=0
        for r in cache:
            if (half=='前半')!=(r['date']<'2026-04-01'): continue
            m=meta.get(r['race_id'])
            if not m: continue
            sf,dist,g,_=m
            for hh in r['horses']:
                if not lo<=hh['pop']<=hi: continue
                h=num2h.get((r['race_id'],hh['num'])); pv=prevs.get((r['race_id'],h)) if h else None
                if not pv or not close(pv,0,0.6) or not (same(sf,dist,pv) and (eqcls(g,pv) or down(g,pv))): continue
                n+=1; w+=payout('単勝',(hh['num'],),r['pay']); pl+=payout('複勝',(hh['num'],),r['pay'])
        print(f"  {lab} {half}: {n}頭 単勝回収{w/max(n,1):.0f}% 複勝回収{pl/max(n,1):.0f}%")
