"""本線（妙味馬の単複＋馬連）を距離帯・芝ダ・頭数別に分けた成績（過去1年・前半/後半）."""
import sys
sys.argv = ["x", "none"]
exec(open("tools/strategy_combo.py").read())
import sqlite3
c = sqlite3.connect("data/keiba.db")
info = {r[0]: r[1:] for r in c.execute("select race_id, surface, distance, course from races")}


def sub(f, cond):
    def g(r):
        sf, dist, crs = info[r["race_id"]]
        if not cond(sf, dist, crs, len(r["horses"])):
            return [], None
        return f(r)
    return g


plan = both(tanpuku(), gen("馬連", ev=1.2, need_value=True, maxN=14, per_race=5))
for nm, cond in {"全": lambda s, d, c, n: True,
                 "芝1200以下": lambda s, d, c, n: s == "芝" and d <= 1200,
                 "芝1400-1600": lambda s, d, c, n: s == "芝" and 1400 <= d <= 1600,
                 "芝1800以上": lambda s, d, c, n: s == "芝" and d >= 1800,
                 "ダ1400以下": lambda s, d, c, n: s == "ダ" and d <= 1400,
                 "ダ1500以上": lambda s, d, c, n: s == "ダ" and d >= 1500,
                 "短距離(1400以下)15頭以上": lambda s, d, c, n: d <= 1400 and n >= 15,
                 "短距離(1400以下)14頭以下": lambda s, d, c, n: d <= 1400 and n <= 14}.items():
    show(f"単複＋馬連 {nm}", sub(plan, cond))
    show(f"単複のみ {nm}", sub(tanpuku(), cond))
