import pickle, sys, json, sqlite3
from collections import defaultdict, Counter
sys.path.insert(0, ".")
from keiba.strategy import payout
D = pickle.load(open(sys.argv[1], "rb"))
c = sqlite3.connect("data/keiba.db"); PT = dict(c.execute("select race_id, pace_type from races"))
base = defaultdict(lambda: [0,0])
for r in D:
    for f in r["horses"]:
        if f["pop"] and f["fin"]: b = base[min(f["pop"],14)]; b[0]+=1; b[1]+= f["fin"]<=3
exp = {p: v[1]/v[0] for p,v in base.items()}
def per(d): return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2
cm = Counter(); agg = defaultdict(lambda: [[0,0,0.0,0,0] for _ in range(3)])
for r in D:
    hs = [f for f in r["horses"] if f["pop"] and f["fin"]]
    known = [f for f in hs if f.get("pos_last") is not None]
    if len(hs) < 8 or len(known) < len(hs) * 0.7: continue
    nfront = sum(1 for f in known if f["pos_last"] <= 0.15)
    fp = "前に行く馬少(0-1)" if nfront <= 1 else "普通(2-3)" if nfront <= 3 else "多(4+)"
    cm[(fp, PT.get(r["rid"]))] += 1
    pr = per(r["date"]); fk = {cc: y for cc, y in (r["pay"] or {}).get("複勝", [])}; tk = {cc: y for cc, y in (r["pay"] or {}).get("単勝", [])}
    for f in known:
        st = "前(前走前15%)" if f["pos_last"] <= 0.15 else "後(前走後ろ40%)" if f["pos_last"] >= 0.6 else "中"
        for key in ((r["su"], fp, st), ("全", fp, st)):
            a = agg[key][pr]; a[0]+=1; a[1]+= f["fin"]<=3; a[2]+= exp[min(f["pop"],14)]; a[3]+= fk.get(str(f["num"]),0); a[4]+= tk.get(str(f["num"]),0)
print("前に行く馬の数 × 実際のペース型（件数）")
for fp in ("前に行く馬少(0-1)","普通(2-3)","多(4+)"):
    row = {t: cm[(fp,t)] for t in ("瞬発","持続","平均","消耗")}; s = sum(row.values())
    print(" ", fp, {k: f"{v/s*100:.0f}%" for k,v in row.items()}, s)
print("\n芝ダ | 前に行く馬 | 脚質 | 走数 | A/E 発見/確認/テスト | 複勝回収 | 単勝回収")
for key in sorted(agg):
    A = agg[key]
    print(" | ".join(key) + " | " + "/".join(str(a[0]) for a in A) + " | " + "/".join(f"{a[1]/a[2]:.2f}" for a in A) + " | " + "/".join(f"{a[3]/a[0]:.0f}" for a in A) + "% | " + "/".join(f"{a[4]/a[0]:.0f}" for a in A) + "%")
