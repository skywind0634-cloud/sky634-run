"""多角的な総当たり（2026-11-08 ユーザー「多角的に分析しろ」「あらゆる分析しろよ」）.
誰（父・母父・父系・母父系・調教師・騎手・騎手×調教師・父×母父系・全体）× 切り口（keiba/multi_angles.py: コース×距離・距離帯・根幹/非根幹・大箱/小回り・馬場・頭数・季節・
枠・年齢・性別・馬体重増減・間隔・延長/短縮・大幅な距離変化・芝ダ替わり・前走着順・前走の人気との差・斤量増減・乗り替わり・前走の位置取り・前走の着差・昇級/降級）、
「全体」はレース条件×馬の条件の組み合わせ.
① 選定の確かめ（未来を見ない）: 2021-22 / 2023 / 2024 の3期とも条件を満たした組を、2025-01〜26-09 と 実戦（2026-10〜）で答え合わせ.
② 本番用: 2021-23 / 2024 / 2025-26/9 の3期とも A/E≥1.10（≤0.90）・各期の見込み6以上・条件外より上（下）の組 → data/knowledge/multi_angle_scan.json（keiba/digest.py の材料）.
使い方: python3 tools/multi_angle_scan.py"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.multi_angles import race_conds, horse_conds, region  # noqa: E402

MIN_EXP = 6


def load_rows():
    c = sqlite3.connect(Path(__import__("os").environ.get("ANALYSIS_DB") or (ROOT / "data" / "keiba.db")))
    rcols = [r[1] for r in c.execute("pragma table_info(races)")]
    lay = "r.layout" if "layout" in rcols else "''"
    rows = c.execute(f"""select r.date,r.race_id,r.course,r.surface,r.distance,r.going,{lay},r.grade,
        (select count(*) from results y where y.race_id=r.race_id),x.horse_id,x.gate,x.age,x.sex,x.popularity,x.finish,x.trainer,x.jockey,
        x.weight_carried,x.passing,x.time_sec,x.body_weight_diff,h.sire,h.damsire,h.sire_line,h.damsire_line
        from results x join races r on r.race_id=x.race_id left join horses h on h.horse_id=x.horse_id
        where x.finish>0 and r.surface in ('芝','ダ') order by r.date, r.race_id""").fetchall()
    win = {}
    for r in rows:
        if r[14] == 1 and r[19]:
            win[r[1]] = r[19]
    return rows, win


def build(rows, win, periods, pfun):
    """periods: 期の数, pfun(date)->期の番号 or None（使わない）"""
    base = defaultdict(lambda: [0, 0])
    for r in rows:
        if r[13]:
            k = (r[3], min(r[13], 16)); base[k][0] += 1; base[k][1] += r[14] <= 3
    e = {k: v[1] / v[0] for k, v in base.items()}
    last = {}
    agg = defaultdict(lambda: [[0, 0.0] for _ in range(periods)])
    tot = defaultdict(lambda: [[0, 0.0] for _ in range(periods)])
    for (d, rid, co, su, dist, go, ly, gr, n, hid, gate, age, sex, p, f, tr, jk, wc, pas, ts, bwd, sire, ds, sl, dsl) in rows:
        prev = last.get(hid)
        last[hid] = dict(date=d, distance=dist, surface=su, finish=f, popularity=p, weight_carried=wc, jockey=jk, passing=pas, n_runners=n,
                         behind=(ts - win[rid]) if ts and rid in win else None, grade=gr)
        pi = pfun(d)
        if not p or pi is None:
            continue
        ex = e[(su, min(p, 16))]; ob = f <= 3
        rc = race_conds(co, su, dist, go, ly, n, d)
        hc = horse_conds(su, dist, gate, n, age, sex, d, prev, wc, jk, gr, bwd, region(co))
        cs = rc + hc
        whos = (("父", sire), ("母父", ds), ("父系", sl), ("母父系", dsl), ("調教師", tr), ("騎手", jk),
                ("騎手×調教師", f"{jk}×{tr}" if jk and tr else None), ("父×母父系", f"{sire}×{dsl}" if sire and dsl else None))
        for who, name in whos:
            if not name:
                continue
            t = tot[(who, name, su)][pi]; t[0] += ob; t[1] += ex
            for cnd in cs:
                a = agg[(who, name, cnd)][pi]; a[0] += ob; a[1] += ex
        t = tot[("全体", "", su)][pi]; t[0] += ob; t[1] += ex
        for a_ in rc:
            for b_ in hc:
                a = agg[("全体", "", f"{a_}×{b_.split('・', 1)[-1]}")][pi]; a[0] += ob; a[1] += ex
    return agg, tot


def select(agg, tot, periods):
    out = []
    for (who, name, cnd), v in agg.items():
        su = "芝" if "芝" in cnd else "ダ" if "ダ" in cnd else None
        if su is None:
            continue
        t = tot[(who, name, su)]
        ins, rat, ok = [], [], True
        for i in range(periods):
            io, ie = v[i]; oo, oe = t[i][0] - io, t[i][1] - ie
            if ie < MIN_EXP or oe < MIN_EXP:
                ok = False; break
            ins.append(io / ie); rat.append((io / ie) / (oo / oe) if oo else 9)
        if not ok:
            continue
        if all(x >= 1.10 for x in ins) and all(x >= 1.03 for x in rat):
            out.append(dict(who=who, name=name, cond=cnd, dir="+", ae=[round(x, 2) for x in ins], ratio=[round(x, 2) for x in rat]))
        elif all(x <= 0.90 for x in ins) and all(x <= 0.97 for x in rat):
            out.append(dict(who=who, name=name, cond=cnd, dir="-", ae=[round(x, 2) for x in ins], ratio=[round(x, 2) for x in rat]))
    return out


def main():
    rows, win = load_rows()
    # ① 未来を見ない確かめ
    tr_p = lambda d: 0 if "2021" <= d < "2023" else 1 if d < "2024" else 2 if d < "2025" else None
    agg, tot = build(rows, win, 3, tr_p)
    picked = select(agg, tot, 3)
    (ROOT / "data" / "cache" / "multi_angle_train.json").write_text(json.dumps({"items": picked}, ensure_ascii=False), encoding="utf-8")
    te_p = lambda d: 0 if "2025" <= d < "2026-10" else 1 if d >= "2026-10" else None
    tagg, _ = build(rows, win, 2, te_p)
    chk = defaultdict(lambda: [[0, 0.0], [0, 0.0], 0])
    for x in picked:
        v = tagg.get((x["who"], x["name"], x["cond"]))
        k = (x["dir"], x["who"])
        chk[k][2] += 1
        if v:
            for i in range(2):
                chk[k][i][0] += v[i][0]; chk[k][i][1] += v[i][1]
    # ② 本番用
    pr_p = lambda d: 0 if "2021" <= d < "2024" else 1 if d < "2025" else 2 if d < "2026-10" else None
    agg, tot = build(rows, win, 3, pr_p)
    out = select(agg, tot, 3)
    # 未来を見ない確かめで、確認期間に逆向き（プラスなのに A/E<1.0、マイナスなのに>1.0）だった「誰」の種類は本番でも使わない
    bad = {k for k, v in chk.items() if v[0][1] and ((k[0] == "+" and v[0][0] / v[0][1] < 1.0) or (k[0] == "-" and v[0][0] / v[0][1] > 1.0))}
    out = [x for x in out if (x["dir"], x["who"]) not in bad]
    out.sort(key=lambda x: (x["dir"], -min(x["ae"]) if x["dir"] == "+" else max(x["ae"])))
    (ROOT / "data" / "knowledge" / "multi_angle_scan.json").write_text(json.dumps(
        {"_meta": "多角的な総当たり（tools/multi_angle_scan.py）。誰×切り口で3期とも A/E≥1.10（≤0.90）・見込み6以上・条件外より上（下）。未来を見ない確かめで逆向きだった種類は除く",
         "excluded_kinds": sorted(f"{a}{b}" for a, b in bad), "items": out}, ensure_ascii=False, indent=0), encoding="utf-8")
    cnt = defaultdict(lambda: [0, 0])
    for x in out:
        cnt[x["who"]][0 if x["dir"] == "+" else 1] += 1
    L = ["# 多角的な総当たり（tools/multi_angle_scan.py, 2026-11-08）", "",
         "誰（父・母父・父系・母父系・調教師・騎手・騎手×調教師・父×母父系・全体＝レース条件×馬の条件）× 切り口（コース×距離・距離帯・根幹/非根幹・大箱/小回り・馬場・頭数・季節・枠・年齢・性別・"
         "馬体重増減・間隔・延長/短縮・大幅な距離変化・芝ダ替わり・前走着順・前走の人気との差・斤量増減・乗り替わり・前走の位置取り・前走の着差・昇級/降級）。", "",
         "## ① 未来を見ない確かめ（2021-22 / 2023 / 2024 で選び、2025-01〜26-09 と実戦10月〜で答え合わせ）", "",
         "| 向き | 誰 | 選んだ組 | 確認 2025-26/9 の A/E | 実戦10月〜 の A/E |", "|---|---|---|---|---|"]
    for k in sorted(chk):
        v = chk[k]
        f = lambda a: f"{a[0] / a[1]:.2f}" if a[1] else "-"
        L.append(f"| {'○' if k[0] == '+' else '▽'} | {k[1]} | {v[2]} | {f(v[0])} | {f(v[1])} |")
    L += ["", f"確認期間で逆向きだった種類（本番で使わない）: {'、'.join(f'{a}{b}' for a, b in sorted(bad)) or 'なし'}", "",
          "## ② 本番用（2021-23 / 2024 / 2025-26/9 の3期とも）", "",
          f"プラス {sum(x['dir'] == '+' for x in out)} 組・マイナス {sum(x['dir'] == '-' for x in out)} 組（" + "、".join(f"{k} +{v[0]}/−{v[1]}" for k, v in cnt.items()) + "）", "",
          "| 向き | 誰 | 名前 | 切り口 | A/E（3期） | 条件外との比（3期） |", "|---|---|---|---|---|---|"]
    L += [f"| {'○' if x['dir'] == '+' else '▽'} | {x['who']} | {x['name']} | {x['cond']} | {'/'.join(map(str, x['ae']))} | {'/'.join(map(str, x['ratio']))} |" for x in out]
    (ROOT / "docs" / "analysis" / "multi_angle_scan.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:L.index("## ② 本番用（2021-23 / 2024 / 2025-26/9 の3期とも）") + 4]))


if __name__ == "__main__":
    main()
