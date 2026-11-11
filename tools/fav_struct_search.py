"""人気の組合せ（人気馬を含む買い方）× レース条件 の回収率を、発見2021-23 / 確認2024 / テスト2025-26 で探す."""
import json, sqlite3, sys, itertools
from collections import defaultdict
sys.path.insert(0, ".")
from keiba.strategy import payout
from keiba.trend import meet_stage
c = sqlite3.connect("data/keiba.db")
races = {}
for rid, date, co, su, dist, n, grade, going, pay, rno in c.execute("select race_id,date,course,surface,distance,n_runners,grade,going,payouts,race_no from races where payouts is not null and surface in ('芝','ダ')"):
    races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, n=n or 0, grade=grade or "?", going=going or "良", pay=json.loads(pay), rno=rno)
pops = defaultdict(dict)
for rid, num, pop in c.execute("select race_id, number, popularity from results where popularity is not null"):
    if rid in races: pops[rid][pop] = num
def band(d): return "短" if d <= 1400 else "マ" if d <= 1800 else "中" if d <= 2200 else "長"
S = {
 "ワイド1-2": [("ワイド",(1,2))], "ワイド1-3": [("ワイド",(1,3))], "ワイド2-3": [("ワイド",(2,3))],
 "ワイド1→2-5": [("ワイド",(1,k)) for k in (2,3,4,5)], "ワイド1→4-6": [("ワイド",(1,k)) for k in (4,5,6)],
 "ワイド2→3-6": [("ワイド",(2,k)) for k in (3,4,5,6)],
 "馬連1-2": [("馬連",(1,2))], "馬連1→2-4": [("馬連",(1,k)) for k in (2,3,4)], "馬連2-3": [("馬連",(2,3))],
 "馬連1→4-6": [("馬連",(1,k)) for k in (4,5,6)],
 "3複1-2-3": [("三連複",(1,2,3))], "3複1-2→3-6": [("三連複",(1,2,k)) for k in (3,4,5,6)],
 "3複1軸2-5BOX": [("三連複",(1,a,b)) for a,b in itertools.combinations((2,3,4,5),2)],
 "3複2-3→4-7": [("三連複",(2,3,k)) for k in (4,5,6,7)], "3複1-3→4-7": [("三連複",(1,3,k)) for k in (4,5,6,7)],
 "3複2-3-4": [("三連複",(2,3,4))], "3複1軸4-7BOX": [("三連複",(1,a,b)) for a,b in itertools.combinations((4,5,6,7),2)],
 "複勝1": [("複勝",(1,))], "複勝2": [("複勝",(2,))], "複勝3": [("複勝",(3,))], "単勝1": [("単勝",(1,))], "単勝2": [("単勝",(2,))],
}
def per(d): return "発見" if d < "2024-01-01" else "確認" if d < "2025-01-01" else "テスト"
agg = defaultdict(lambda: [0,0,0,0])  # races, bet, ret, hits
for rid, R in races.items():
    P = pops[rid]
    if len(P) < 7: continue
    nb = "〜10頭" if R["n"] <= 10 else "11-14頭" if R["n"] <= 14 else "15頭〜"
    gd = "良" if R["going"].startswith("良") else "道悪"
    conds = [("全体",), ("場面", R["co"], R["su"]), ("芝ダ距離", R["su"], band(R["dist"])), ("場面距離", R["co"], R["su"], band(R["dist"])),
             ("クラス", R["grade"]), ("頭数", R["su"], nb), ("開催", R["su"], meet_stage(rid) or "?"), ("馬場", R["su"], gd),
             ("芝ダ距離頭数", R["su"], band(R["dist"]), nb), ("クラス芝ダ", R["grade"], R["su"]), ("R", R["su"], "11R" if R["rno"]==11 else "12R" if R["rno"]==12 else "7-10R"),
             ("月", R["date"][5:7]), ("場面開催", R["co"], R["su"], meet_stage(rid) or "?")]
    pr = per(R["date"])
    for sname, T in S.items():
        tk = [(k, tuple(P[x] for x in h)) for k, h in T if all(x in P for x in h)]
        if len(tk) != len(T): continue
        y = sum(payout(k, h, R["pay"]) for k, h in tk)
        for cd in conds:
            a = agg[(sname, cd, pr)]; a[0] += 1; a[1] += 100*len(tk); a[2] += y; a[3] += y > 0
out = []
keys = {(s, cd) for s, cd, _ in agg}
for s, cd in keys:
    A = [agg.get((s, cd, p)) for p in ("発見","確認","テスト")]
    if any(a is None or a[0] < 60 for a in A): continue
    roi = [a[2]/a[1]*100 for a in A]; hit = [a[3]/a[0]*100 for a in A]
    out.append((s, cd, roi, hit, [a[0] for a in A], A))
print("条件セル数", len(out))
for s, cd, roi, hit, n, A in sorted(out, key=lambda x: -min(x[2])):
    if min(roi) < 100: break
    print(f"{s:12s} {'/'.join(cd):24s} 回収 {roi[0]:.0f}/{roi[1]:.0f}/{roi[2]:.0f}% 的中 {hit[0]:.0f}/{hit[1]:.0f}/{hit[2]:.0f}% R {n}")
# 全体の基準
for s in S:
    A = [agg[(s, ("全体",), p)] for p in ("発見","確認","テスト")]
    print("基準", s, [round(a[2]/a[1]*100) for a in A], [round(a[3]/a[0]*100) for a in A])
