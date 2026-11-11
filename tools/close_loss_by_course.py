import sys,collections,random
sys.path.insert(0,'tools')
exec(open('tools/close_loss_analysis.py').read().split("print('=== 前走4着以下")[0].replace("'data/keiba.db'","'data/keiba.db'"))
PER=(('〜2022','0','2023'),('2023-24','2023','2025'),('2025〜','2025','9'))
def stat(filt):
    out=[]
    for lab,lo,hi in PER:
        n=t3=0;e=0.0;ret=0
        for d,sf,dist,g,c,f,p,o,pv in recs:
            if lo<=d<hi and filt(sf,dist,g,c,pv,p):
                n+=1;t3+=f<=3;e+=exp[min(p,12)];ret+=(o*100 if f==1 and o else 0)
        out.append((n,t3,e,ret))
    return out
cond=lambda sf,dist,g,pv: close(pv,0,0.6) and same(sf,dist,pv) and (eqcls(g,pv) or down(g,pv))
keys=collections.Counter((c,sf,dist) for d,sf,dist,g,c,f,p,o,pv in recs if cond(sf,dist,g,pv))
print('=== 競馬場×芝ダ（0.6秒差以内の4着以下・同条件） ===')
for c in sorted({k[0] for k in keys}):
    for sfx in ('芝','ダ'):
        s=stat(lambda sf,dist,g,cc,pv,p,c=c,sfx=sfx: cc==c and sf==sfx and cond(sf,dist,g,pv))
        n=sum(x[0] for x in s)
        if n<80: continue
        ae=[x[1]/x[2] if x[2] else 0 for x in s]
        mark='◎' if min(ae)>=1.1 else ''
        print(f"{c}{sfx}: {n:4d}頭 3着内{sum(x[1] for x in s)/n:.0%} A/E 全体{sum(x[1] for x in s)/sum(x[2] for x in s):.2f} 期間別 {' / '.join(f'{a:.2f}' for a in ae)} 単回収{sum(x[3] for x in s)/n:.0f}% {mark}")
print('=== 競馬場×芝ダ×距離（120頭以上、3期間ともA/E1.15以上だけ） ===')
hits=0;tested=0;found=[]
for (c,sf0,dist0),cnt in keys.items():
    if cnt<120: continue
    tested+=1
    s=stat(lambda sf,dist,g,cc,pv,p,c=c,sf0=sf0,dist0=dist0: cc==c and sf==sf0 and dist==dist0 and cond(sf,dist,g,pv))
    ae=[x[1]/x[2] if x[2] else 0 for x in s]
    if min(ae)>=1.15:
        hits+=1; n=sum(x[0] for x in s)
        found.append((c,sf0,dist0,n,ae,sum(x[1] for x in s)/n,sum(x[3] for x in s)/n))
for c,sf0,dist0,n,ae,t3,roi in sorted(found,key=lambda x:-min(x[4])):
    print(f"{c}{sf0}{dist0}m: {n}頭 3着内{t3:.0%} A/E {' / '.join(f'{a:.2f}' for a in ae)} 単回収{roi:.0f}%")
print(f'調べたコース {tested}、3期間とも1.15以上 {hits}')
# 偶然の基準: 同じ頭数の馬をランダムに選んだ集団で、3期間とも1.15以上になる割合
random.seed(0)
pool=[r for r in recs]
cnt=0;T=0
for (c,sf0,dist0),k in keys.items():
    if k<120: continue
    for _ in range(5):
        T+=1
        sample=random.sample(pool,k)
        ok=True
        for lab,lo,hi in PER:
            sub=[x for x in sample if lo<=x[0]<hi]
            e=sum(exp[min(x[6],12)] for x in sub); t=sum(1 for x in sub if x[5]<=3)
            if not e or t/e<1.15: ok=False;break
        cnt+=ok
print(f'偶然の基準: ランダムな同数の馬で3期間とも1.15以上になる割合 {cnt/T:.1%}')
