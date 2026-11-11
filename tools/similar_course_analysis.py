"""『似た特性のコース』での好走歴（コース間の関係を特性で一般化）: 同じ芝ダ・距離帯で、直線の長さ区分・坂・回り（大回り/小回り）が同じ別コースで3着内 or 0.3秒差以内。
期間別に、人気帯ごとの3着内率（ありvsなし）と A/E を見る。"""
import sqlite3,collections,sys
sys.path.insert(0,'.')
from keiba import knowledge as K
db=sqlite3.connect('data/keiba.db')
rows=db.execute("""select r.race_id, ra.date, ra.course, ra.surface, ra.distance, r.horse_id, r.finish, r.popularity, r.odds, r.time_sec, r.number
 from results r join races ra using(race_id) where r.finish is not null and ra.surface in ('芝','da','ダ') order by ra.date, ra.race_id""").fetchall()
win_t={rid:t for rid,d,c,sf,dist,h,f,p,o,t,n in rows if f==1 and t}
attr_cache={}
def sig(c,sf,dist):
    k=(c,sf,dist)
    if k not in attr_cache:
        a=K.course_attrs(c,sf,dist) or {}
        band='短' if dist<=1400 else '中' if dist<=2000 else '長'
        attr_cache[k]=(sf,band,a.get('straight_cat'),a.get('slope'),a.get('turn'))
    return attr_cache[k]
past=collections.defaultdict(list)
recs=[]
for rid,d,c,sf,dist,h,f,p,o,t,n in rows:
    s=sig(c,sf,dist)
    if p:
        good=[(cc,ss) for cc,ss,g in past[h] if g]
        sim=any(ss==s and cc!=c for cc,ss in good)
        samec=any(cc==c and ss==s for cc,ss in good)
        anyg=bool(good)
        recs.append((d,p,f,o,sim,samec,anyg))
    gap=(t-win_t[rid]) if t and rid in win_t else None
    past[h].append((c,s,f<=3 or (gap is not None and gap<=0.3)))
base=collections.defaultdict(lambda:[0,0])
for d,p,f,o,*_ in recs: b=base[min(p,12)]; b[0]+=1; b[1]+=f<=3
exp={k:v[1]/v[0] for k,v in base.items()}
PER=(('〜2022','0','2023'),('2023-24','2023','2025'),('2025〜','2025','9'))
def show(label,sel):
    parts=[]
    for lab,lo,hi in PER:
        n=t3=0;e=0.0;ret=0.0
        for d,p,f,o,sim,samec,anyg in recs:
            if lo<=d<hi and sel(p,sim,samec,anyg):
                n+=1;t3+=f<=3;e+=exp[min(p,12)];ret+=(o*100 if f==1 and o else 0)
        parts.append(f"{lab}: {n}頭 3着内{t3/max(n,1):.1%} A/E{t3/e if e else 0:.2f} 単{ret/max(n,1):.0f}%")
    print(f"{label:44s} "+" | ".join(parts))
for lo,hi in ((1,3),(4,6),(7,9),(10,18)):
    print(f'--- {lo}〜{hi}番人気 ---')
    show('似た特性の別コースで好走歴あり', lambda p,sim,samec,anyg,lo=lo,hi=hi: lo<=p<=hi and sim)
    show('  同じコースで好走歴あり', lambda p,sim,samec,anyg,lo=lo,hi=hi: lo<=p<=hi and samec)
    show('  似た特性・同コースの好走歴なし（他では好走あり）', lambda p,sim,samec,anyg,lo=lo,hi=hi: lo<=p<=hi and anyg and not sim and not samec)
    show('  好走歴なし', lambda p,sim,samec,anyg,lo=lo,hi=hi: lo<=p<=hi and not anyg)
