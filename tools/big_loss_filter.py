"""直近2〜3走すべて勝ち馬から1.5秒以上負けている馬は来るか（2026-10-12, ユーザー指摘「ずっと1.5秒以上差がある馬が推奨に入っている」の検証）.
DB 全期間（第7R以降）で人気帯別の3着内率・複勝/単勝回収率。結果: 3着内6.5%・複勝回収58%・単勝回収52% → keiba/model.py の out_of_form で推奨から外す。
使い方: python3 tools/big_loss_filter.py"""
from collections import defaultdict
c = sqlite3.connect("data/keiba.db")
races = {r[0]: dict(date=r[1], su=r[2], pay=json.loads(r[3]) if r[3] else {}) for r in c.execute("select race_id,date,surface,payouts from races where surface in ('芝','ダ')")}
rows = defaultdict(list)
for rid, hid, fin, num, t, pop in c.execute("select race_id,horse_id,finish,number,time_sec,popularity from results"):
    if rid in races: rows[rid].append((hid, fin, num, t, pop))
hist = defaultdict(list); base = defaultdict(lambda: [0, 0]); agg = defaultdict(lambda: [0, 0, 0.0, 0])
for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
    R = races[rid]; rs = rows[rid]
    wt = min((t for _, f, _, t, _ in rs if f == 1 and t), default=None)
    fk = {cc: y for cc, y in R["pay"].get("複勝", [])}; tk = {cc: y for cc, y in R["pay"].get("単勝", [])}
    for hid, fin, num, t, pop in rs:
        if fin is None or pop is None: continue
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        h = hist[hid][-3:]
        if len(h) >= 2:
            ds = [d for d, su in h if d is not None]
            same = [d for d, su in h if d is not None and su == R["su"]]
            if len(ds) == len(h):
                lab = "直近%d走すべて1.5秒以上負け" % len(h) if min(ds) >= 1.5 else "直近の最小差1.0-1.5秒" if min(ds) >= 1.0 else "直近に1.0秒未満あり"
            else: lab = "差不明"
            band = "1-3人気" if p <= 3 else "4-6人気" if p <= 6 else "7-9人気" if p <= 9 else "10人気以下"
            for k in ((lab, band), (lab, "全体")):
                a = agg[k]; a[0] += 1; a[1] += fin <= 3; a[2] += p; a[3] += fk.get(str(num), 0)
                agg[k + ("単",)] = agg.get(k + ("単",), [0, 0, 0, 0]); agg[k + ("単",)][3] += tk.get(str(num), 0)
    for hid, fin, num, t, pop in rs:
        hist[hid].append(((t - wt) if (t and wt and fin) else None, R["su"]))
exp = {p: v[1] / v[0] for p, v in base.items()}
print("| 直近の負け方 | 人気 | 走数 | 3着内率 | 複勝回収 | 単勝回収 |")
for lab in ("直近2〜3走すべて1.5秒以上負け", "直近の最小差1.0-1.5秒", "直近に1.0秒未満あり"):
    for band in ("全体", "4-6人気", "7-9人気", "10人気以下"):
        ks = [k for k in agg if len(k) == 2 and k[1] == band and (k[0] == lab or (lab.startswith("直近2") and "すべて1.5" in k[0]))]
        n = sum(agg[k][0] for k in ks); top = sum(agg[k][1] for k in ks); f = sum(agg[k][3] for k in ks); w = sum(agg[k + ("単",)][3] for k in ks)
        if n: print(f"| {lab} | {band} | {n} | {top/n*100:.1f}% | {f/n:.0f}% | {w/n:.0f}% |")
