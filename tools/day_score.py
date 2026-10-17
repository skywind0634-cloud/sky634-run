"""レース別シート（predictions/<日>/レース別シート.md）を当日の速報結果（sky634-run day-results ブランチの results/<日>.json, race.netkeiba.com 形式）で採点する.
使い方: python3 tools/day_score.py <レース別シート.md> <results.json>"""
import json, re, sys
from collections import defaultdict
RES = sys.argv[2]
res={r['race_id']:r for r in json.load(open(RES))}
PFX={'新潟':'2026040401','東京':'2026050406','京都':'2026080406'}
def pays(r):
    out=defaultdict(dict)
    for row in r['payouts']:
        if len(row)<3: continue
        k=row[0]; nums=row[1].split(); ys=[int(y.replace(',','').replace('円','')) for y in row[2].split()]
        size={'単勝':1,'複勝':1,'枠連':2,'馬連':2,'ワイド':2,'馬単':2,'3連複':3,'3連単':3}.get(k,1)
        combos=[nums[i:i+size] for i in range(0,len(nums),size)]
        for c,y in zip(combos,ys):
            key='-'.join(c) if k in('馬単','3連単') else '-'.join(sorted(c,key=int))
            out[k][key]=y
    return out
txt=open(sys.argv[1],encoding='utf-8').read()
blocks=re.split(r'\n(?=■)',txt)
tot_bet=tot_ret=0; kinds=defaultdict(lambda:[0,0,0]); tag=defaultdict(lambda:[0,0,[]])
report=[]
for b in blocks:
    m=re.match(r'■ \S+ (\S\S)(\d+)R (\S+)',b.strip())
    if not m: continue
    co,rn,nm=m.groups(); rid=PFX[co]+f'{int(rn):02d}'; r=res.get(rid)
    if not r: report.append(f'{co}{rn}R 結果なし'); continue
    fin={int(x[2]):(int(x[0]) if x[0].isdigit() else 99) for x in r['rows'] if x[2].isdigit()}
    top=sorted([(f,n) for n,f in fin.items()])[:3]
    namemap={int(x[2]):x[3] for x in r['rows'] if x[2].isdigit()}
    popm={int(x[2]):x[9] for x in r['rows'] if x[2].isdigit()}
    P=pays(r)
    buy=re.search(r'【買う】(.*)',b).group(1)
    tickets=[]
    if 'なし' not in buy[:3]:
        for seg in re.split(r'／',buy):
            kindgrp=re.findall(r'(単勝|複勝|ワイド|馬連|3連複|単複) ([\d\-]+)',seg)
            for k,c in kindgrp:
                if k=='単複': tickets+= [('単勝',c),('複勝',c)]
                else: tickets.append((k,c))
            fm=re.search(r'★フラグ点: (\d+)\S+ → 単勝・複勝',seg)
            if fm: tickets+=[('単勝',fm.group(1)),('複勝',fm.group(1))]
    ret=0; hits=[]
    for k,c in tickets:
        key='-'.join(sorted(c.split('-'),key=int))
        y=P.get(k,{}).get(key,0); ret+=y; kinds[k][0]+=1; kinds[k][1]+=y; kinds[k][2]+=y>0
        if y: hits.append(f'{k}{c}={y}')
    tot_bet+=len(tickets)*100; tot_ret+=ret
    # tags
    for line in b.splitlines():
        hm=re.match(r'\s+(\d+) (\S+?)（(\d+)人気',line)
        if not hm: continue
        n=int(hm.group(1)); p=int(hm.group(3)); f=fin.get(n,99)
        tags=line.split('｜')[1] if '｜' in line else ''
        for t in re.split(r'・',tags):
            t=re.sub(r'^根拠:.*','',t).strip()
            if not t: continue
            base=re.sub(r'[◎○▽×▼]+$','',t); mk=t[len(base):]
            key=(base,mk or '')
            a=tag[key]; a[0]+=1; a[1]+=f<=3; a[2].append((p,f))
        if '★買う' in line: pass
    tops=' '.join(f'{f}着{n}{namemap[n]}({popm[n]}人)' for f,n in top)
    report.append(f'{co}{rn}R {nm}: {tops} | 買い{len(tickets)}点 払戻{ret} {" ".join(hits)}')
print('\n'.join(report))
print(f'合計 購入{tot_bet} 払戻{tot_ret} 回収{tot_ret/max(tot_bet,1)*100:.0f}%')
for k,v in kinds.items(): print(k,f'{v[0]}点 的中{v[2]} 払戻{v[1]}')
print('--- 材料別（頭数・3着内）')
for (b,mk),a in sorted(tag.items(),key=lambda x:-x[1][0]):
    exp=sum({1:.62,2:.50,3:.40,4:.33,5:.27,6:.22,7:.17,8:.14,9:.11}.get(p,.07) for p,f in a[2])
    print(f'{b}{mk}: {a[0]}頭 3着内{a[1]} 見込み{exp:.1f}')
