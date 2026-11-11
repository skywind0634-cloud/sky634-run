# 準本線・穴の「走る条件」の単勝/複勝回収率を前半/後半で検証（data/cache/strategy_backtest.json）。使い方: python3 tools/strategy_sub_picks.py data/cache/strategy_backtest.json
import json, sys
d = json.load(open(sys.argv[1]))
def pay(r, kind, n):
    for c, y in r['pay'].get(kind, []):
        if c == str(n): return y
    return 0
rules = {
 '10-12人気 cond1.0': lambda h: 10<=h['pop']<=12 and h['cond']>=1.0,
 '13+人気 cond1.0': lambda h: h['pop']>=13 and h['cond']>=1.0,
 '10+人気 edge0.5': lambda h: h['pop']>=10 and h['edge']>=0.5,
 '7-9 cond1.0': lambda h: 7<=h['pop']<=9 and h['cond']>=1.0,
 '7-9 cond1.0 & 非厳格': lambda h: 7<=h['pop']<=9 and h['cond']>=1.0 and not h['seg'],
 '7-9 cond1.0 or 厳格': lambda h: 7<=h['pop']<=9 and (h['cond']>=1.0 or h['seg']),
 '4-9 厳格 or 7-9 cond1.0': lambda h: (4<=h['pop']<=9 and h['seg']) or (7<=h['pop']<=9 and h['cond']>=1.0),
 '4-6 cond1.0': lambda h: 4<=h['pop']<=6 and h['cond']>=1.0,
 '準本線(4-9 cond0.4)': lambda h: 4<=h['pop']<=9 and h['cond']>=0.4,
}
for name, f in rules.items():
    s={'A':[0,0,0,0,0],'B':[0,0,0,0,0]}
    for r in d:
        half='A' if r['date']<'2026-04-01' else 'B'; hit=False
        for h in r['horses']:
            if h['fin'] is None or h['cond'] is None: continue
            if not f(h): continue
            x=s[half]; x[0]+=1; x[1]+=h['fin']<=3; x[2]+=pay(r,'単勝',h['num']); x[3]+=pay(r,'複勝',h['num'])
    a,b=s['A'],s['B']
    if not a[0] or not b[0]: print(name,'n/a'); continue
    print(f"{name}: n {a[0]}/{b[0]} 3着内 {a[1]/a[0]:.0%}/{b[1]/b[0]:.0%} 単 {a[2]/a[0]:.0f}%/{b[2]/b[0]:.0f}% 複 {a[3]/a[0]:.0f}%/{b[3]/b[0]:.0f}% 1日あたり {(a[0]+b[0])/104:.1f}頭")
