import json, glob, sys, sqlite3, collections
sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from keiba import db, analysis
from keiba.cli import load_params
import keiba.model as M
from keiba.model import evaluate_race
from keiba.digest import reasons
M.PARAMS.update(load_params())
conn = db.connect(); st = analysis.build_stats(conn)
c2 = sqlite3.connect('data/keiba.db')
# 2歳戦での父の成績（人気からの期待との比）
rows = c2.execute("""select h.sire, ra.surface, r.finish, r.popularity from results r join races ra using(race_id) join horses h using(horse_id)
 where r.age=2 and r.finish is not null and r.popularity is not null""").fetchall()
base = collections.defaultdict(lambda: [0, 0])
for s, sf, f, p in rows:
    b = base[min(p, 12)]; b[0] += 1; b[1] += f <= 3
exp = {k: v[1] / v[0] for k, v in base.items()}
def sire2(s, sf):
    n = t = e = 0
    for x in rows:
        if x[0] == s and x[1] == sf:
            n += 1; t += x[2] <= 3; e += exp[min(x[3], 12)]
    return n, t, e
def sib(dam, hid):
    r = c2.execute("""select count(*), sum(r.finish<=3) from results r join horses h using(horse_id) where h.dam=? and h.horse_id!=?""", (dam, hid)).fetchone()
    return r
for f in sorted(glob.glob(sys.argv[1] + '/*.json')):
    c = json.load(open(f))
    ev = evaluate_race(c, st, conn, n_sims=0)
    ent = {e['number']: e for e in c['entries']}
    print(f"### {c['course']}{c['race_no']}R {c['name']} {c['surface']}{c['distance']}m {len(c['entries'])}頭 発走{c.get('post_time','')}")
    for h in sorted(ev, key=lambda h: -h.p_win):
        e = ent.get(h.number, {})
        n, t, ex = sire2(h.sire, c['surface'])
        sn, st3 = sib(e.get('dam'), e.get('horse_id')) if e.get('dam') else (0, 0)
        ratio = h.p_win / h.p_market if h.p_market else 0
        comp = {k: round(v, 2) for k, v in h.components.items() if abs(v) >= 0.1}
        print(f"  {h.number:>2} {h.name} 人気{e.get('popularity')} {e.get('odds')}倍 勝{h.p_win:.0%} 比{ratio:.2f} 父{h.sire}×{h.damsire} {h.jockey} | 父の2歳{c['surface']} {t}/{n}(期待{ex:.1f}) 兄姉3着内{st3 or 0}/{sn} | blood{h.blood_upside:+.2f} {comp}")
