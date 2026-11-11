"""条件×父・母父の総当たり（2026-11-08 ユーザー「後から見つけましたじゃ意味ない」。AR杯1着 6ファミリータイム＝非根幹×父リアルスティールを事前に材料にしていなかった反省）.
レース前に分かる条件（keiba/digest.py の race_trait_conds と同じ区分: コース×芝ダ・道悪・大箱/小回り・距離帯・根幹/非根幹・ダート）× 父・母父 で、
条件内のA/E（3着内の実数÷人気からの見込み）が3期（2021-23 / 2024 / 2025-26）とも1.05以上かつ条件外の1.03倍以上（マイナスは0.95以下かつ0.97倍以下）の組を全部拾う.
出力: data/knowledge/cond_sire_scan.json（keiba/digest.py が「条件×父/母父」の○▽として材料にする）, docs/analysis/cond_sire_scan.md
使い方: python3 tools/cond_sire_scan.py"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def conds(course, surf, dist, going, layout):
    s = {f"{course}{surf}"}
    if (going or "良")[0] in "稍重不":
        s.add("道悪")
    if course == "東京" or (course in ("新潟", "京都", "阪神") and "外" in (layout or "")):
        s.add("大箱")
    elif course in ("中山", "福島", "小倉", "札幌", "函館") or "内" in (layout or ""):
        s.add("小回り")
    if dist:
        s.add("短距離" if dist <= 1400 else "マイル" if dist <= 1800 else "長距離" if dist >= 2200 else "中距離")
        s.add("根幹" if dist in (1200, 1600, 2000, 2400) else "非根幹")
    return {f"{surf}・{c}" if not c.startswith(course) else c for c in s}


def per(d):
    return 0 if d < "2024" else 1 if d < "2025" else 2


def main():
    c = sqlite3.connect(Path(__import__("os").environ.get("ANALYSIS_DB") or (ROOT / "data" / "keiba.db")))
    cols = [r[1] for r in c.execute("pragma table_info(races)")]
    lay = "layout" if "layout" in cols else "''"
    rows = c.execute(f"""select r.date,r.course,r.surface,r.distance,r.going,{lay},x.popularity,x.finish,h.sire,h.damsire
        from results x join races r on r.race_id=x.race_id left join horses h on h.horse_id=x.horse_id
        where x.popularity>0 and x.finish>0 and r.surface in ('芝','ダ') and r.date < '2026-10-01'""").fetchall()
    base = defaultdict(lambda: [0, 0])
    for r in rows:
        k = (r[2], min(r[6], 16)); base[k][0] += 1; base[k][1] += r[7] <= 3
    e = {k: v[1] / v[0] for k, v in base.items()}
    # agg[(who, name, cond)] = [[obs,exp] in-cond x3, [obs,exp] out-cond x3]
    agg = defaultdict(lambda: [[0, 0.0] for _ in range(6)])
    surf_tot = defaultdict(lambda: [[0, 0.0] for _ in range(3)])
    for d, co, su, dist, go, ly, p, f, sire, dsire in rows:
        cs = conds(co, su, dist, go, ly)
        ex = e[(su, min(p, 16))]; ob = f <= 3; pi = per(d)
        for who, name in (("父", sire), ("母父", dsire)):
            if not name:
                continue
            t = surf_tot[(who, name, su)][pi]; t[0] += ob; t[1] += ex
            for cnd in cs:
                a = agg[(who, name, cnd)][pi]; a[0] += ob; a[1] += ex
    out = []
    for (who, name, cnd), v in agg.items():
        su = cnd.split("・")[0] if "・" in cnd else cnd[-1]
        tot = surf_tot[(who, name, su)]
        ins, outs = [], []
        ok = True
        for i in range(3):
            io, ie = v[i]; oo, oe = tot[i][0] - io, tot[i][1] - ie
            if ie < 8 or oe < 8:
                ok = False; break
            ins.append(io / ie); outs.append(oo / oe)
        if not ok:
            continue
        rat = [ins[i] / outs[i] if outs[i] else 9 for i in range(3)]
        if all(x >= 1.05 for x in ins) and all(x >= 1.03 for x in rat):
            out.append(dict(who=who, name=name, cond=cnd, dir="+", ae=[round(x, 2) for x in ins], ratio=[round(x, 2) for x in rat]))
        elif all(x <= 0.95 for x in ins) and all(x <= 0.97 for x in rat):
            out.append(dict(who=who, name=name, cond=cnd, dir="-", ae=[round(x, 2) for x in ins], ratio=[round(x, 2) for x in rat]))
    out.sort(key=lambda x: (x["dir"], -min(x["ratio"]) if x["dir"] == "+" else max(x["ratio"])))
    (ROOT / "data" / "knowledge" / "cond_sire_scan.json").write_text(json.dumps(
        {"_meta": "条件×父・母父の総当たり（tools/cond_sire_scan.py）。3期（2021-23/2024/2025-26/9）とも条件内A/E≥1.05かつ条件外の1.03倍以上（マイナスは≤0.95かつ≤0.97倍）",
         "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# 条件×父・母父の総当たり（tools/cond_sire_scan.py, 2026-11-08）", "",
         "3期（2021-23 / 2024 / 2025-26/9）とも条件内のA/E≥1.05かつ条件外の1.03倍以上（マイナスは≤0.95かつ≤0.97倍）。各期の見込み8以上。", "",
         f"プラス {sum(x['dir'] == '+' for x in out)} 組・マイナス {sum(x['dir'] == '-' for x in out)} 組", "",
         "| 向き | 父/母父 | 名前 | 条件 | 条件内A/E（3期） | 条件外との比（3期） |", "|---|---|---|---|---|---|"]
    for x in out:
        L.append(f"| {'○' if x['dir'] == '+' else '▽'} | {x['who']} | {x['name']} | {x['cond']} | {'/'.join(map(str, x['ae']))} | {'/'.join(map(str, x['ratio']))} |")
    (ROOT / "docs" / "analysis" / "cond_sire_scan.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:5]))


if __name__ == "__main__":
    main()
