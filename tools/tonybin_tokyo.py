"""使い方: python3 tools/tonybin_tokyo.py <ped5_full.json（run/ped-data ブランチ）> docs/analysis/tonybin_tokyo.md
東京芝（長い直線）でトニービン・欧州型の血は生きるか（5代血統表, 3期間）."""
import json, sqlite3, sys
from collections import defaultdict
sys.path.insert(0, ".")
from keiba.knowledge import country_type
P = json.load(open(sys.argv[1])); pos = P["pos"]; H = P["horses"]
c = sqlite3.connect("data/keiba.db")
base = defaultdict(lambda: [0,0])
rows = []
for rid, date, co, su, dist, pt, hid, fin, pop, num, sl, dsl, pay, l3 in c.execute(
        """select ra.race_id, ra.date, ra.course, ra.surface, ra.distance, ra.pace_type, r.horse_id, r.finish, r.popularity, r.number,
                  h.sire_line, h.damsire_line, ra.payouts, r.last3f
           from results r join races ra using(race_id) join horses h using(horse_id)
           where ra.surface='芝' and r.finish is not null and r.popularity is not null"""):
    p = min(pop, 14); b = base[p]; b[0]+=1; b[1]+= fin<=3
    rows.append((rid, date, co, dist, pt, hid, fin, p, num, sl, dsl, pay))
exp = {p: v[1]/v[0] for p,v in base.items()}
def per(d): return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2
paycache = {}
agg = defaultdict(lambda: [[0,0,0.0,0,0] for _ in range(3)])
for rid, date, co, dist, pt, hid, fin, p, num, sl, dsl, pay in rows:
    names = H.get(hid)
    if not names: continue
    a = dict(zip(pos, names))
    tb_gen = min((len(k) for k, v in a.items() if v in ("トニービン", "Tony Bin")), default=None)
    feats = {"トニービン(5代内)": tb_gen is not None, "トニービン(3代内)": tb_gen is not None and tb_gen <= 3,
             "父=欧州型": country_type(sl) == "欧州型" if sl else False, "母父=欧州型": country_type(dsl) == "欧州型" if dsl else False,
             "父=米国型": country_type(sl) == "米国型" if sl else False, "母父=米国型": country_type(dsl) == "米国型" if dsl else False}
    feats["父か母父が欧州型"] = feats["父=欧州型"] or feats["母父=欧州型"]
    if rid not in paycache:
        pj = json.loads(pay) if pay else {}
        paycache[rid] = ({cc: y for cc, y in pj.get("複勝", [])}, {cc: y for cc, y in pj.get("単勝", [])})
    fk, tk = paycache[rid]
    bd = "〜1400" if dist <= 1400 else "1600-1800" if dist <= 1800 else "2000-2400" if dist <= 2400 else "2500〜"
    grp = "東京" if co == "東京" else "新潟" if co == "新潟" else "その他"
    conds = [(grp,), (grp, bd), (grp, "実際:" + (pt or "?"))]
    for f, v in feats.items():
        for cd in conds:
            k = (f, "あり" if v else "なし") + cd
            x = agg[k][per(date)]; x[0]+=1; x[1]+= fin<=3; x[2]+= exp[p]; x[3]+= fk.get(str(num),0); x[4]+= tk.get(str(num),0)
L = ["# 東京芝（長い直線）× トニービン・欧州型（自動生成, tools/tonybin_tokyo.py）", "",
     "- 5代血統表（data/ped5_full.json, 約1.56万頭）のある馬の芝の出走。A/E＝3着内の実数÷人気から見込む数。発見2021-23/確認2024/テスト2025-26。", "",
     "| 血統 | 競馬場 | 条件 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
for k in sorted(agg):
    if k[1] != "あり": continue
    A = agg[k]
    if min(x[0] for x in A) < 60: continue
    ae = [x[1]/x[2] for x in A]
    m = "◎" if min(ae) >= 1.1 else "×" if max(ae) <= 0.9 else ""
    L.append(f"| {k[0]} | {k[2]} | {' '.join(k[3:]) or '全体'} | " + "/".join(str(x[0]) for x in A) + f" | {m}" + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
open(sys.argv[2], "w").write("\n".join(L) + "\n"); print("\n".join(L))
