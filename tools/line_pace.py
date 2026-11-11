"""父系統・種牡馬・母父系統 × 芝ダ × 予想展開（前に行く馬の数）/ 坂 の A/E と回収率（3期間）."""
import pickle, sys, json, sqlite3
from collections import defaultdict
D = pickle.load(open(sys.argv[1], "rb"))
c = sqlite3.connect("data/keiba.db")
ty = {}
for rid, num, s, sl, dsl in c.execute("select r.race_id, r.number, h.sire, h.sire_line, h.damsire_line from results r join horses h using(horse_id)"):
    ty[(rid, num)] = (s, sl, dsl)
SLOPE = {"中山": "坂", "阪神": "坂", "中京": "坂", "東京": "坂"}
base = defaultdict(lambda: [0,0])
for r in D:
    for f in r["horses"]:
        if f["pop"] and f["fin"]: b = base[min(f["pop"],14)]; b[0]+=1; b[1]+= f["fin"]<=3
exp = {p: v[1]/v[0] for p,v in base.items()}
def per(d): return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2
agg = defaultdict(lambda: [[0,0,0.0,0,0] for _ in range(3)])
for r in D:
    hs = [f for f in r["horses"] if f["pop"] and f["fin"]]
    known = [f for f in hs if f.get("pos_last") is not None]
    if len(known) < len(hs) * 0.7: continue
    nfront = sum(1 for f in known if f["pos_last"] <= 0.15)
    fc = "前少(0-1頭)" if nfront <= 1 else "前多(4頭+)" if nfront >= 4 else "普通(2-3頭)"
    pr = per(r["date"]); pay = r["pay"] or {}
    fk = {cc: y for cc, y in pay.get("複勝", [])}; tk = {cc: y for cc, y in pay.get("単勝", [])}
    sl_ = SLOPE.get(r["co"], "平坦"); su = r["su"]
    bd = "短" if r["dist"] <= 1400 else "マ" if r["dist"] <= 1800 else "中長"
    for f in hs:
        s, sl, dsl = ty.get((r["rid"], f["num"]), (None,)*3)
        keys = []
        for who, v in (("父系統", sl), ("種牡馬", s), ("母父系統", dsl)):
            if v: keys += [(who, v, su, fc), (who, v, su, sl_, fc), (who, v, su, bd, fc)]
        for k in keys:
            a = agg[k][pr]; a[0]+=1; a[1]+= f["fin"]<=3; a[2]+= exp[min(f["pop"],14)]; a[3]+= fk.get(str(f["num"]),0); a[4]+= tk.get(str(f["num"]),0)
res = []
for k, A in agg.items():
    if min(a[0] for a in A) < 80: continue
    ae = [a[1]/a[2] for a in A]; fu = [a[3]/a[0] for a in A]; tu = [a[4]/a[0] for a in A]
    if min(ae) >= 1.1 or max(ae) <= 0.85:
        res.append((k, ae, fu, tu, [a[0] for a in A]))
L = ["# 系統・種牡馬 × 予想展開（前に行く馬の数）× 坂・距離（自動生成, tools/line_pace.py）", "",
     "- 予想展開＝前走で前15%にいた馬の数（前多4頭以上→実際の消耗戦71%、前少0-1頭→瞬発・平均寄り）。発見2021-23/確認2024/テスト2025-26、各期間80走以上。",
     "- ◎＝A/E が3期間とも1.10以上（人気以上に走る）、×＝3期間とも0.85以下。", "",
     "| | 対象 | 名前 | 条件 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|"]
for k, ae, fu, tu, n in sorted(res, key=lambda x: (-min(x[1]) if min(x[1]) >= 1.1 else 9 + max(x[1]))):
    L.append(f"| {'◎' if min(ae) >= 1.1 else '×'} | {k[0]} | {k[1]} | {' / '.join(k[2:])} | " + "/".join(map(str, n)) + " | " + "/".join(f"{x:.2f}" for x in ae) + " | " + "/".join(f"{x:.0f}" for x in fu) + "% | " + "/".join(f"{x:.0f}" for x in tu) + "% |")
open(sys.argv[2], "w").write("\n".join(L) + "\n")
json.dump([{"key": list(k), "ae": [round(x, 2) for x in ae], "fuku": [round(x) for x in fu], "tan": [round(x) for x in tu], "n": n} for k, ae, fu, tu, n in res],
          open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
print("\n".join(L))
