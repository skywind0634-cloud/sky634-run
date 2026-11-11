"""各出走馬のレース前に分かる特徴を DB から作って保存（消去法の検証用）."""
import json, sqlite3, datetime as dt, pickle, sys
from collections import defaultdict
c = sqlite3.connect("data/keiba.db")
GR = {"1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4, "G3": 5, "G2": 6, "G1": 7}
races = {}
for rid, date, co, su, dist, n, grade, going, pay, pt in c.execute("select race_id,date,course,surface,distance,n_runners,grade,going,payouts,pace_type from races where surface in ('芝','ダ')"):
    races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, n=n or 0, g=GR.get(grade or "", 4), pay=json.loads(pay) if pay else None, pt=pt)
rows = defaultdict(list)
for rid, hid, fin, num, t, pop, pas, l3, bwd, age, jk, wc in c.execute("select race_id,horse_id,finish,number,time_sec,popularity,passing,last3f,body_weight_diff,age,jockey,weight_carried from results"):
    if rid in races: rows[rid].append(dict(hid=hid, fin=fin, num=num, t=t, pop=pop, pas=pas, l3=l3, bwd=bwd, age=age, jk=jk))
hist = defaultdict(list); out = []
for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
    R = races[rid]; rs = rows[rid]
    wt = min((x["t"] for x in rs if x["fin"] == 1 and x["t"]), default=None)
    l3s = sorted(x["l3"] for x in rs if x["l3"])
    recs = []
    for x in rs:
        h = hist[x["hid"]][-5:][::-1]
        f = {"pop": x["pop"], "fin": x["fin"], "num": x["num"], "n_hist": len(h)}
        if h:
            p = h[0]
            bs = [q["b"] for q in h[:3] if q["b"] is not None]
            f["b_min3"] = min(bs) if bs else None; f["b_last"] = p["b"]; f["nb3"] = len(bs)
            f["fin_last"] = p["fin"]; f["fins3"] = [q["fin"] for q in h[:3]]
            f["l3r_last"] = p["l3r"]; f["pos_last"] = p["pos"]
            f["days"] = (dt.date.fromisoformat(R["date"]) - dt.date.fromisoformat(p["date"])).days
            f["gchg"] = R["g"] - p["g"]; f["dchg"] = R["dist"] - p["dist"]; f["sw"] = p["su"] != R["su"]
            f["same_su_b"] = min([q["b"] for q in h if q["su"] == R["su"] and q["b"] is not None], default=None)
            f["jchg"] = p["jk"] != x["jk"]
        f["bwd"] = x["bwd"]; f["age"] = x["age"]
        recs.append(f)
    out.append(dict(rid=rid, date=R["date"], co=R["co"], su=R["su"], dist=R["dist"], n=len(rs), pay=R["pay"], horses=recs))
    for x in rs:
        try: pos = int(str(x["pas"]).split("-")[0]) / max(len(rs), 1)
        except Exception: pos = None
        hist[x["hid"]].append(dict(date=R["date"], b=(x["t"] - wt) if (x["t"] and wt and x["fin"]) else None, fin=x["fin"], su=R["su"], dist=R["dist"], g=R["g"], jk=x["jk"],
                                   l3r=(l3s.index(x["l3"]) + 1) if x["l3"] else None, pos=pos))
pickle.dump(out, open(sys.argv[1], "wb")); print(len(out))
