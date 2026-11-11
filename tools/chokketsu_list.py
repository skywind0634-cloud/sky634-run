"""直結コースの一覧（3着内率で選んだ組の、選んだ期間と その後の期間での3着内率）と、前走コース→今回コースの替わり。"""
import sqlite3,collections,json
db=sqlite3.connect('data/keiba.db')
rows=db.execute("""select r.race_id, ra.date, ra.course, ra.surface, ra.distance, r.horse_id, r.finish, r.popularity, r.time_sec
 from results r join races ra using(race_id) where r.finish is not null and ra.surface in ('芝','ダ') order by ra.date, ra.race_id""").fetchall()
win_t={rid:t for rid,d,c,sf,dist,h,f,p,t in rows if f==1 and t}
key=lambda c,sf,dist:f"{c}{sf}{dist}"
past=collections.defaultdict(list); recs=[]
for rid,d,c,sf,dist,h,f,p,t in rows:
    T=key(c,sf,dist)
    if p:
        good={k for k,g,_ in past[h] if g}
        prevk=past[h][-1][0] if past[h] else None
        prevgood=past[h][-1][1] if past[h] else None
        recs.append((d,T,f<=3,p,good,bool(past[h]),prevk,prevgood))
    gap=(t-win_t[rid]) if t and rid in win_t else None
    past[h].append((T,f<=3 or (gap is not None and gap<=0.3),d))
chok={k:set(v) for k,v in json.load(open('data/knowledge/chokketsu_map_top3.json')).items()}
def rate(rs): return (sum(r[2] for r in rs)/len(rs), len(rs)) if rs else (0,0)
out=[]
for T,Ks in chok.items():
    for K in Ks:
        res=[]
        for lo,hi in (('0','2024'),('2024','9')):
            pool=[r for r in recs if lo<=r[0]<hi and r[1]==T and r[5]]
            a=rate([r for r in pool if K in r[4]]); b=rate([r for r in pool if K not in r[4] and r[4]])
            pl=rate([r for r in pool if K in r[4] and r[3]>=7]); pb=rate([r for r in pool if K not in r[4] and r[3]>=7])
            res.append((a,b,pl,pb))
        out.append((T,K,res))
def fmt(x): return f"{x[0]:.0%}({x[1]})"
held=[o for o in out if o[2][1][0][1]>=20 and o[2][1][0][0]-o[2][1][1][0]>=0.03]
print(f'=== 直結コース 一覧（2023年までで選んだ{len(out)}組のうち、2024年以降も3着内率が+3ポイント以上高かった {len(held)}組）===')
print('今回のコース ← 直結コース | 2024年以降: 直結で好走歴あり / なし（好走歴は別コース） | うち7番人気以下: あり / なし | 2023年まで: あり / なし')
for T,K,res in sorted(held,key=lambda o:o[0]):
    print(f"{T} ← {K} | {fmt(res[1][0])} / {fmt(res[1][1])} | {fmt(res[1][2])} / {fmt(res[1][3])} | {fmt(res[0][0])} / {fmt(res[0][1])}")
print(f'\n=== 2024年以降は差がなかった（偶然だった可能性が高い）{len(out)-len(held)}組 ===')
print(', '.join(f"{T}←{K}" for T,K,res in sorted(out,key=lambda o:o[0]) if (T,K,res) not in held))
print('\n=== 前走コース → 今回コース（コース替わり。前走の着順は問わない）: 2023年までと2024年以降の両方で、同じ今回コースの他の前走より3着内率が+5ポイント以上・各40頭以上 ===')
trans=collections.defaultdict(lambda:{'a':[],'b':[]})
for d,T,top3,p,good,hp,prevk,prevgood in recs:
    if not prevk or prevk==T: continue
    trans[(T,prevk)]['a' if d<'2024' else 'b'].append((top3,p))
byT=collections.defaultdict(lambda:{'a':[],'b':[]})
for (T,K),v in trans.items():
    for s in 'ab': byT[T][s]+=v[s]
rows2=[]
for (T,K),v in trans.items():
    if len(v['a'])<40 or len(v['b'])<40: continue
    ra=sum(x[0] for x in v['a'])/len(v['a']); rb=sum(x[0] for x in v['b'])/len(v['b'])
    oa=[x for x in byT[T]['a']]; ob=[x for x in byT[T]['b']]
    ba=(sum(x[0] for x in oa)-sum(x[0] for x in v['a']))/max(len(oa)-len(v['a']),1)
    bb=(sum(x[0] for x in ob)-sum(x[0] for x in v['b']))/max(len(ob)-len(v['b']),1)
    lp=[x for x in v['a']+v['b'] if x[1]>=7]
    if ra-ba>=0.05 and rb-bb>=0.05:
        rows2.append((T,K,ra,ba,len(v['a']),rb,bb,len(v['b']),sum(x[0] for x in lp)/max(len(lp),1),len(lp)))
print('今回 ← 前走 | 2023年まで: 3着内率 / 他の前走 | 2024年以降: 3着内率 / 他の前走 | 7番人気以下の3着内率')
for T,K,ra,ba,na,rb,bb,nb,lp,nl in sorted(rows2,key=lambda x:-(x[5]-x[6])):
    print(f"{T} ← 前走{K} | {ra:.0%}({na}) / {ba:.0%} | {rb:.0%}({nb}) / {bb:.0%} | {lp:.0%}({nl})")
