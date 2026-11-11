"""直結コースの検証: 発見期間（〜2023）で「過去にコースKで好走（3着内）した馬は今回のコースTで人気以上に走る」組を選び、
確認期間（2024）・テスト期間（2025〜）で通用するかを見る。好走は 3着内 または 勝ち馬から0.3秒差以内。"""
import sqlite3,collections,json,sys,statistics as st
db=sqlite3.connect('data/keiba.db')
rows=db.execute("""select r.race_id, ra.date, ra.course, ra.surface, ra.distance, ra.grade, r.horse_id, r.finish, r.popularity, r.odds, r.time_sec, r.number
 from results r join races ra using(race_id) where r.finish is not null and ra.surface in ('芝','ダ') order by ra.date, ra.race_id""").fetchall()
win_t={}
for rid,d,c,sf,dist,g,h,f,p,o,t,num in rows:
    if f==1 and t: win_t[rid]=t
key=lambda c,sf,dist:f"{c}{sf}{dist}"
past=collections.defaultdict(list)   # horse -> [(date,key,good)]
recs=[]
for rid,d,c,sf,dist,g,h,f,p,o,t,num in rows:
    if p:
        ks={k for dd,k,good in past[h] if good}
        recs.append((rid,num,d,key(c,sf,dist),f,p,o,ks,bool(past[h])))
    gap=(t-win_t[rid]) if t and rid in win_t else None
    past[h].append((d,key(c,sf,dist),f<=3 or (gap is not None and gap<=0.3)))
base=collections.defaultdict(lambda:[0,0])
for r in recs: b=base[min(r[5],12)]; b[0]+=1; b[1]+=r[4]<=3
exp={k:v[1]/v[0] for k,v in base.items()}
PER={'発見(〜2023)':('0','2024'),'確認(2024)':('2024','2025'),'テスト(2025〜)':('2025','9')}
per=lambda d:next(k for k,(lo,hi) in PER.items() if lo<=d<hi)
# 発見期間で (T,K) の A/E
acc=collections.defaultdict(lambda:[0,0,0.0])
for rid,num,d,T,f,p,o,ks,hp in recs:
    if per(d)!='発見(〜2023)': continue
    for K in ks:
        a=acc[(T,K)]; a[0]+=1; a[1]+=f<=3; a[2]+=exp[min(p,12)]
chok=collections.defaultdict(set)
for (T,K),(n,t3,e) in acc.items():
    if T!=K and n>=30 and e and t3/e>=1.25:
        chok[T].add(K)
print('発見期間で選ばれた直結の組（同じコースを除く）:', sum(len(v) for v in chok.values()), '組 /', len(chok), 'コース')
def evaluate(label,sel):
    out={}
    for pk in PER:
        n=t3=w=0;e=0.0;ret=0.0
        for rid,num,d,T,f,p,o,ks,hp in recs:
            if per(d)!=pk or not sel(T,ks,p,hp): continue
            n+=1;t3+=f<=3;e+=exp[min(p,12)];ret+=(o*100 if f==1 and o else 0)
        out[pk]=(n,t3/max(n,1),t3/e if e else 0,ret/max(n,1))
    print(f"{label:48s} "+" | ".join(f"{k}: {v[0]}頭 3着内{v[1]:.0%} A/E{v[2]:.2f} 単{v[3]:.0f}%" for k,v in out.items()))
evaluate('直結コースで好走歴あり（全人気）', lambda T,ks,p,hp: bool(chok.get(T,set())&ks))
evaluate('同じコースで好走歴あり（コース実績）', lambda T,ks,p,hp: T in ks)
evaluate('どこかで好走歴あり（比較）', lambda T,ks,p,hp: bool(ks))
evaluate('直結コースで好走歴あり・同じコースは好走なし', lambda T,ks,p,hp: bool(chok.get(T,set())&ks) and T not in ks)
for lo,hi in ((1,3),(4,6),(7,9),(10,18)):
    evaluate(f'  直結好走歴あり・{lo}〜{hi}番人気', lambda T,ks,p,hp,lo=lo,hi=hi: lo<=p<=hi and bool(chok.get(T,set())&ks))
# 偶然の基準: 発見期間で同じ基準を満たす組の「行き先コース」をランダムに入れ替えたもの
import random
random.seed(0)
allK=list({k for v in chok.values() for k in v})
fake={T:set(random.sample(allK,min(len(v),len(allK)))) for T,v in chok.items()}
evaluate('（偶然の基準）ランダムな直結コースで好走歴あり', lambda T,ks,p,hp: bool(fake.get(T,set())&ks))
json.dump({T:sorted(v) for T,v in chok.items()},open('data/knowledge/chokketsu_map.json','w'),ensure_ascii=False,indent=0)
# 実払戻（過去1年）での単勝・複勝回収率
sys.path.insert(0,'.')
from keiba.strategy import payout
cache=json.load(open('data/cache/strategy_backtest.json'))
idx={(r[0],r[1]):r for r in recs}
for lo,hi,lab in ((4,9,'4〜9番人気'),(10,18,'10番人気以下'),(1,18,'全人気')):
    for half in ('前半','後半'):
        n=w=pl=0
        for r in cache:
            if (half=='前半')!=(r['date']<'2026-04-01'): continue
            for h in r['horses']:
                x=idx.get((r['race_id'],h['num']))
                if not x or not lo<=h['pop']<=hi: continue
                if chok.get(x[3],set())&x[7]:
                    n+=1;w+=payout('単勝',(h['num'],),r['pay']);pl+=payout('複勝',(h['num'],),r['pay'])
        print(f"  過去1年 直結好走歴あり {lab} {half}: {n}頭 単回収{w/max(n,1):.0f}% 複回収{pl/max(n,1):.0f}%")
# 妙味条件(厳格)と重ねる
for half in ('前半','後半'):
    n=w=pl=0
    for r in cache:
        if (half=='前半')!=(r['date']<'2026-04-01'): continue
        for h in r['horses']:
            x=idx.get((r['race_id'],h['num']))
            if not x or not (h['pop']>=4 and h['seg']): continue
            if chok.get(x[3],set())&x[7]:
                n+=1;w+=payout('単勝',(h['num'],),r['pay']);pl+=payout('複勝',(h['num'],),r['pay'])
    print(f"  過去1年 妙味条件(厳格)×直結好走歴 {half}: {n}頭 単回収{w/max(n,1):.0f}% 複回収{pl/max(n,1):.0f}%")
print('例: 直結コースの一覧（一部）')
for T in sorted(chok)[:25]: print(' ',T,'←',', '.join(sorted(chok[T])[:8]))
