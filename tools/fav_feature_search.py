"""上位人気馬の特徴（レース前に分かるもの）で、人気馬を含む買い方の回収率が変わるか。発見2021-23/確認2024/テスト2025-26."""
import json, sqlite3, sys, itertools, datetime as dt
from collections import defaultdict
sys.path.insert(0, ".")
from keiba.strategy import payout
c = sqlite3.connect("data/keiba.db")
races = {}
for rid, date, co, su, dist, n, grade, going, pay in c.execute("select race_id,date,course,surface,distance,n_runners,grade,going,payouts from races where surface in ('芝','ダ')"):
    races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, n=n or 0, grade=grade or "?", pay=json.loads(pay) if pay else None)
rows = defaultdict(list); hist = defaultdict(list)
for rid, hid, fin, num, gate, age, jockey, t, pop, bwd, l3, wc in c.execute("select race_id,horse_id,finish,number,gate,age,jockey,time_sec,popularity,body_weight_diff,last3f,weight_carried from results"):
    if rid in races: rows[rid].append(dict(hid=hid, fin=fin, num=num, gate=gate, age=age, jk=jockey, t=t, pop=pop, bwd=bwd, l3=l3, wc=wc))
order = sorted(races, key=lambda r: (races[r]["date"], r))
GR = {"1勝":1,"2勝":2,"3勝":3,"OP":4,"L":4,"G3":5,"G2":6,"G1":7}
feat = {}
for rid in order:
    R = races[rid]; rs = rows[rid]
    wt = min((x["t"] for x in rs if x["t"] and x["fin"] == 1), default=None)
    l3s = sorted(x["l3"] for x in rs if x["l3"])
    for x in rs:
        f = {}
        h = hist[x["hid"]]
        if h:
            p = h[-1]
            f["前走着順"] = "1着" if p["fin"] == 1 else "2-3着" if (p["fin"] or 99) <= 3 else "4-5着" if (p["fin"] or 99) <= 5 else "6着以下"
            f["前走差"] = "勝ち" if p["fin"] == 1 else "0.5秒内" if p["diff"] is not None and p["diff"] <= 0.5 else "0.5秒超"
            f["乗替"] = "継続" if p["jk"] == x["jk"] else "乗替"
            dd = R["dist"] - p["dist"]; f["距離"] = "同距離" if abs(dd) < 100 else "延長" if dd > 0 else "短縮"
            f["芝ダ"] = "同" if p["su"] == R["su"] else "替"
            days = (dt.date.fromisoformat(R["date"]) - dt.date.fromisoformat(p["date"])).days
            f["間隔"] = "中3週内" if days <= 28 else "中4-8週" if days <= 63 else "9週以上"
            g0, g1 = GR.get(p["grade"], 4), GR.get(R["grade"], 4)
            f["クラス"] = "昇級" if g1 > g0 else "降級" if g1 < g0 else "同級"
            f["前走人気"] = "前走も上位3人気" if (p["pop"] or 99) <= 3 else "前走4人気以下"
            f["前走上がり"] = "最速" if p["l3r"] == 1 else "2-3位" if (p["l3r"] or 99) <= 3 else "4位以下"
            f["同場"] = "同場" if p["co"] == R["co"] else "別場"
        else:
            f["前走着順"] = "DB外"
        if x["bwd"] is not None: f["体重増減"] = "-10以下" if x["bwd"] <= -10 else "+10以上" if x["bwd"] >= 10 else "±8内"
        if x["age"]: f["年齢"] = "3歳" if x["age"] <= 3 else "4-5歳" if x["age"] <= 5 else "6歳以上"
        if x["gate"]: f["枠"] = "1-2枠" if x["gate"] <= 2 else "7-8枠" if x["gate"] >= 7 else "3-6枠"
        feat[(rid, x["num"])] = f
    for x in rs:
        hist[x["hid"]].append(dict(date=R["date"], fin=x["fin"], jk=x["jk"], dist=R["dist"], su=R["su"], grade=R["grade"], pop=x["pop"], co=R["co"],
                                   diff=(x["t"] - wt) if (x["t"] and wt) else None, l3r=(l3s.index(x["l3"]) + 1) if x["l3"] else None))
S = {"単勝1": [("単勝",(1,))], "複勝1": [("複勝",(1,))], "ワイド1-2": [("ワイド",(1,2))], "ワイド1→2-5": [("ワイド",(1,k)) for k in (2,3,4,5)],
     "馬連1→2-4": [("馬連",(1,k)) for k in (2,3,4)], "3複1-2→3-6": [("三連複",(1,2,k)) for k in (3,4,5,6)],
     "3複1軸2-5BOX": [("三連複",(1,a,b)) for a,b in itertools.combinations((2,3,4,5),2)],
     # 1番人気を外す買い方（1番人気が不安なとき）
     "ワイド2-3": [("ワイド",(2,3))], "ワイド2→3-6": [("ワイド",(2,k)) for k in (3,4,5,6)], "3複2-3→4-7": [("三連複",(2,3,k)) for k in (4,5,6,7)],
     "馬連2→3-5": [("馬連",(2,k)) for k in (3,4,5)]}
def per(d): return "発見" if d < "2024-01-01" else "確認" if d < "2025-01-01" else "テスト"
agg = defaultdict(lambda: [0,0,0,0])
for rid in order:
    R = races[rid]
    if not R["pay"]: continue
    P = {x["pop"]: x["num"] for x in rows[rid] if x["pop"]}
    if len(P) < 8: continue
    f1 = feat.get((rid, P[1]), {}); f2 = feat.get((rid, P[2]), {})
    conds = [("全体",)] + [("1人気", k, v) for k, v in f1.items()] + [("2人気", k, v) for k, v in f2.items()]
    conds += [("1人気", k1 + "×" + k2, v1 + "×" + v2) for (k1, v1), (k2, v2) in itertools.combinations(sorted(f1.items()), 2)]
    conds += [("1人気×芝ダ", k, v + "×" + R["su"]) for k, v in f1.items()]
    pr = per(R["date"])
    for s, T in S.items():
        tk = [(k, tuple(P[i] for i in h)) for k, h in T if all(i in P for i in h)]
        y = sum(payout(k, h, R["pay"]) for k, h in tk)
        for cd in conds:
            a = agg[(s, cd, pr)]; a[0] += 1; a[1] += 100*len(tk); a[2] += y; a[3] += y > 0
out = []
for (s, cd, pr) in list(agg):
    if pr != "発見": continue
    A = [agg.get((s, cd, p)) for p in ("発見","確認","テスト")]
    if any(a is None or a[0] < 80 for a in A): continue
    roi = [a[2]/a[1]*100 for a in A]; hit = [a[3]/a[0]*100 for a in A]
    out.append((min(roi), s, cd, roi, hit, [a[0] for a in A]))
out.sort(key=lambda x: -x[0])
print("セル数", len(out), " 3期間とも100%超:", sum(1 for o in out if o[0] >= 100))
for m, s, cd, roi, hit, n in out[:40]:
    print(f"{s:11s} {'/'.join(cd):40s} 回収 {roi[0]:.0f}/{roi[1]:.0f}/{roi[2]:.0f}% 的中 {hit[0]:.0f}/{hit[1]:.0f}/{hit[2]:.0f}% R {n}")
pass
