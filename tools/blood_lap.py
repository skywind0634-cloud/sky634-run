"""血統タイプ（父・母父の 日本/米国/欧州型）× ラップ（実際のペース型・前後半3F差）× 坂 × 芝ダ（2026-10-12, 亀谷理論の検証）."""
import pickle, sys, json, sqlite3
from collections import defaultdict
sys.path.insert(0, ".")
from keiba.knowledge import country_type
D = pickle.load(open(sys.argv[1], "rb"))
c = sqlite3.connect("data/keiba.db")
info = {r[0]: r[1:] for r in c.execute("select race_id, pace_type, first3f, last3f, distance from races")}
ty = {}
for rid, num, sl, dsl in c.execute("select r.race_id, r.number, h.sire_line, h.damsire_line from results r join horses h using(horse_id)"):
    ty[(rid, num)] = (country_type(sl) if sl else None, country_type(dsl) if dsl else None)
SLOPE = {"中山": "坂", "阪神": "坂", "中京": "坂", "東京": "坂", "京都": "平坦", "新潟": "平坦", "福島": "平坦", "小倉": "平坦", "札幌": "平坦", "函館": "平坦"}
base = defaultdict(lambda: [0,0])
for r in D:
    for f in r["horses"]:
        if f["pop"] and f["fin"]: b = base[min(f["pop"],14)]; b[0]+=1; b[1]+= f["fin"]<=3
exp = {p: v[1]/v[0] for p,v in base.items()}
def per(d): return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2
agg = defaultdict(lambda: [[0,0,0.0,0,0] for _ in range(3)])
for r in D:
    pt, f3, l3, dist = info.get(r["rid"], (None,)*4)
    if not pt: continue
    hs = [f for f in r["horses"] if f["pop"] and f["fin"]]
    known = [f for f in hs if f.get("pos_last") is not None]
    nfront = sum(1 for f in known if f["pos_last"] <= 0.15) if len(known) >= len(hs) * 0.7 else None
    fc = None if nfront is None else "予想:前少" if nfront <= 1 else "予想:前多" if nfront >= 4 else "予想:普通"
    pr = per(r["date"]); pay = r["pay"] or {}
    fk = {cc: y for cc, y in pay.get("複勝", [])}; tk = {cc: y for cc, y in pay.get("単勝", [])}
    sl = SLOPE.get(r["co"], "?"); su = r["su"]
    for f in hs:
        st, dt_ = ty.get((r["rid"], f["num"]), (None, None))
        keys = []
        for who, t in (("父", st), ("母父", dt_)):
            if not t: continue
            keys += [(who, su, "実際:" + pt, t), (who, su, sl, "実際:" + pt, t)]
            if fc: keys += [(who, su, fc, t), (who, su, sl, fc, t)]
        if st and dt_:
            keys += [("父×母父", su, "実際:" + pt, f"{st}×{dt_}")]
            if fc: keys += [("父×母父", su, fc, f"{st}×{dt_}")]
        for k in keys:
            a = agg[k][pr]; a[0]+=1; a[1]+= f["fin"]<=3; a[2]+= exp[min(f["pop"],14)]; a[3]+= fk.get(str(f["num"]),0); a[4]+= tk.get(str(f["num"]),0)
L = ["# 血統タイプ × ラップ（展開）× 坂 × 芝ダ（自動生成, tools/blood_lap.py）", "",
     "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、×＝3期間とも0.90以下。",
     "- 「実際:」は確定ラップのペース型（結果, 傾向の理解用）。「予想:」はレース前に分かる前に行く馬の数（前走で前15%）から（前少=0-1頭→瞬発・スロー寄り, 前多=4頭以上→消耗71%）。", "",
     "| 対象 | 条件 | タイプ | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
pick = []
for k in sorted(agg):
    A = agg[k]
    if min(a[0] for a in A) < 150: continue
    ae = [a[1]/a[2] for a in A]
    m = "◎" if min(ae) >= 1.1 else "×" if max(ae) <= 0.9 else ""
    if not m: continue
    fu = [a[3]/a[0] for a in A]; tu = [a[4]/a[0] for a in A]
    L.append(f"| {k[0]} | {' / '.join(k[1:-1])} | {m}{k[-1]} | " + "/".join(str(a[0]) for a in A) + " | " + "/".join(f"{x:.2f}" for x in ae) + " | " + "/".join(f"{x:.0f}" for x in fu) + "% | " + "/".join(f"{x:.0f}" for x in tu) + "% |")
    if any(s.startswith("予想:") for s in k):
        pick.append({"key": list(k), "ae": [round(x, 2) for x in ae], "fuku": [round(x) for x in fu], "tan": [round(x) for x in tu], "n": [a[0] for a in A]})
open(sys.argv[2], "w").write("\n".join(L) + "\n"); json.dump(pick, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
print("\n".join(L))
