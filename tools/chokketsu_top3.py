"""直結コースを『3着内に入る確率』で選び、『3着内率』で確かめる。
発見期間（〜2023）: 今回コースTの出走馬のうち、過去にコースK（T以外）で好走した馬の3着内率が、
  同じTの『過去に好走歴はあるがKではない馬』より大きく高い組（差+8ポイント以上・30頭以上）を直結とする。
確認（2024）・テスト（2025〜）で、直結の好走歴がある馬とない馬の3着内率を人気帯ごとに比べる。"""
import sqlite3,collections
db=sqlite3.connect('data/keiba.db')
rows=db.execute("""select r.race_id, ra.date, ra.course, ra.surface, ra.distance, r.horse_id, r.finish, r.popularity, r.time_sec
 from results r join races ra using(race_id) where r.finish is not null and ra.surface in ('芝','ダ') order by ra.date, ra.race_id""").fetchall()
win_t={rid:t for rid,d,c,sf,dist,h,f,p,t in rows if f==1 and t}
key=lambda c,sf,dist:f"{c}{sf}{dist}"
past=collections.defaultdict(list); recs=[]
for rid,d,c,sf,dist,h,f,p,t in rows:
    T=key(c,sf,dist)
    if p:
        ks={k for k,g in past[h] if g}
        recs.append((d,T,f<=3,p,ks,bool(past[h])))
    gap=(t-win_t[rid]) if t and rid in win_t else None
    past[h].append((T,f<=3 or (gap is not None and gap<=0.3)))
disc=[r for r in recs if r[0]<'2024' and r[5]]
byT=collections.defaultdict(list)
for r in disc: byT[r[1]].append(r)
chok=collections.defaultdict(set)
for T,rs in byT.items():
    cnt=collections.Counter(k for r in rs for k in r[4] if k!=T)
    for K,n in cnt.items():
        if n<30: continue
        a=[r[2] for r in rs if K in r[4]]; b=[r[2] for r in rs if K not in r[4] and r[4]]
        if b and sum(a)/len(a)-sum(b)/len(b)>=0.08: chok[T].add(K)
print('発見期間で選んだ直結の組:',sum(len(v) for v in chok.values()),'組 /',len(chok),'コース')
def tab(lab,lo,hi):
    print(f'--- {lab} ---')
    for per,(a,b) in (('発見(〜2023)',('0','2024')),('確認(2024)',('2024','2025')),('テスト(2025〜)',('2025','9'))):
        g={'直結コースで好走歴あり':[0,0],'好走歴はあるが直結コースではない':[0,0],'好走歴なし':[0,0]}
        for d,T,top3,p,ks,hp in recs:
            if not (a<=d<b and lo<=p<=hi and T in chok): continue
            k='直結コースで好走歴あり' if chok[T]&ks else ('好走歴はあるが直結コースではない' if ks else '好走歴なし')
            g[k][0]+=1; g[k][1]+=top3
        print(f'  {per}: '+' | '.join(f'{k} {v[1]/max(v[0],1):.1%}（{v[0]}頭）' for k,v in g.items()))
tab('全人気',1,18)
for lo,hi in ((1,3),(4,6),(7,9),(10,18)): tab(f'{lo}〜{hi}番人気',lo,hi)
import json
json.dump({T:sorted(v) for T,v in chok.items()},open('data/knowledge/chokketsu_map_top3.json','w'),ensure_ascii=False,indent=0)
