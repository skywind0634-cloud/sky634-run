"""妙味度（利益度）の総当たり（2026-11-08 ユーザーが紹介した 卍『中央競馬 妙味度名鑑 2026』の考え方をこちらのDBで作り直す）.
騎手・調教師 × 条件（芝/ダ・距離帯・競馬場・左右回り・道悪・クラス・年齢・休み明け何走目）で、単勝と複勝の回収率の平均（100＝全体の平均回収率）を「妙味度」とし、
3期（2021-23 / 2024 / 2025-26/9）とも妙味度105以上（各期20走以上）の組を data/knowledge/myomi_scan.json に入れる → keiba/digest.py が ○ の材料にする.
未来を見ない確かめ: 2021-22 / 2023 / 2024 で同じ基準で選んだ組の、2025-01〜26-09 の単勝・複勝回収率を出す.
使い方: python3 tools/myomi_scan.py"""
import datetime as dt, json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLS = {"新馬": "新馬", "1勝": "1〜3勝C", "2勝": "1〜3勝C", "3勝": "1〜3勝C", "OP": "OP", "L": "OP", "G3": "重賞", "G2": "重賞", "G1": "重賞"}
MIN_N = 20


def conds(co, su, dist, go, dirn, gr, age, rest_seq):
    out = [su, f"{co}"]
    if dist:
        out.append(f"{su}・" + ("短距離" if dist <= 1400 else "中距離" if dist <= 2000 else "長距離"))
    if dirn in ("右", "左"):
        out.append(f"{dirn}回り")
    if (go or "良")[0] in "稍重不":
        out.append(f"{su}・道悪")
    if gr in CLS:
        out.append(CLS[gr])
    if age:
        out.append("2歳" if age == 2 else "3歳" if age == 3 else "4歳" if age == 4 else "5歳以上")
    if rest_seq:
        out.append(rest_seq)
    return out


def rest_label(hist, d):
    """hist: その馬の過去の出走日（古い順）。中9週以上あけた後の 1走目/2走目/3走目, 中1週以内は連闘扱い."""
    if not hist:
        return None
    try:
        dd = dt.date.fromisoformat(d[:10])
        gaps = []
        prev = dd
        for x in reversed(hist[-3:]):
            xd = dt.date.fromisoformat(x[:10]); gaps.append((prev - xd).days); prev = xd
    except ValueError:
        return None
    if gaps[0] <= 8:
        return "連闘"
    if gaps[0] >= 63:
        return "休明初戦"
    if len(gaps) >= 2 and gaps[1] >= 63:
        return "休明2走"
    if len(gaps) >= 3 and gaps[2] >= 63:
        return "休明3走"
    return None


def per(d, mode):
    if mode == "train":
        return 0 if "2021" <= d < "2023" else 1 if d < "2024" else 2 if d < "2025" else None
    if mode == "test":
        return 0 if "2025" <= d < "2026-10" else None
    return 0 if "2021" <= d < "2024" else 1 if d < "2025" else 2 if d < "2026-10" else None


def main():
    c = sqlite3.connect(Path(__import__("os").environ.get("ANALYSIS_DB") or (ROOT / "data" / "keiba.db")))
    rows = c.execute("""select r.date,r.race_id,r.course,r.surface,r.distance,r.going,r.direction,r.grade,x.horse_id,x.number,x.age,x.finish,x.trainer,x.jockey,r.payouts
        from results x join races r on r.race_id=x.race_id where x.finish>0 and r.surface in ('芝','ダ') order by r.date""").fetchall()
    hist = defaultdict(list)
    recs = []
    paycache = {}
    for d, rid, co, su, dist, go, dirn, gr, hid, num, age, f, tr, jk, pj in rows:
        rs = rest_label(hist[hid], d)
        hist[hid].append(d)
        if rid not in paycache:
            p = json.loads(pj or "{}")
            paycache[rid] = ({a: y for a, y in p.get("単勝", [])}, {a: y for a, y in p.get("複勝", [])})
        tn, fk = paycache[rid]
        recs.append((d, conds(co, su, dist, go, dirn, gr, age, rs), tr, jk, tn.get(str(num), 0), fk.get(str(num), 0)))

    def scan(mode, nper):
        allt = [[0, 0, 0] for _ in range(nper)]
        agg = defaultdict(lambda: [[0, 0, 0] for _ in range(nper)])
        for d, cs, tr, jk, tn, fk in recs:
            pi = per(d, mode)
            if pi is None:
                continue
            allt[pi][0] += 1; allt[pi][1] += tn; allt[pi][2] += fk
            for who, name in (("騎手", jk), ("調教師", tr)):
                if not name:
                    continue
                for cnd in cs:
                    a = agg[(who, name, cnd)][pi]; a[0] += 1; a[1] += tn; a[2] += fk
        base = [((t[1] + t[2]) / 2 / t[0]) if t[0] else 1 for t in allt]
        return agg, base

    def pick(agg, base, nper):
        out = []
        for k, v in agg.items():
            if any(x[0] < MIN_N for x in v):
                continue
            my = [100 * ((x[1] + x[2]) / 2 / x[0]) / base[i] for i, x in enumerate(v)]
            if all(m >= 105 for m in my):
                out.append((k, [round(m) for m in my], [x[0] for x in v]))
        return out

    agg, base = scan("train", 3)
    tr_pick = pick(agg, base, 3)
    (ROOT / "data" / "cache" / "myomi_train.json").write_text(json.dumps({"items": [dict(who=k[0], name=k[1], cond=k[2], myomi=m, n=n) for k, m, n in sorted(tr_pick, key=lambda x: -min(x[1]))]}, ensure_ascii=False), encoding="utf-8")
    tagg, tbase = scan("test", 1)
    tot = [0, 0, 0]
    for k, _, _ in tr_pick:
        v = tagg.get(k)
        if v:
            tot[0] += v[0][0]; tot[1] += v[0][1]; tot[2] += v[0][2]
    test_tan, test_fuku = (tot[1] / tot[0] if tot[0] else 0), (tot[2] / tot[0] if tot[0] else 0)
    agg, base = scan("prod", 3)
    prod = pick(agg, base, 3)
    items = [dict(who=k[0], name=k[1], cond=k[2], myomi=m, n=n) for k, m, n in sorted(prod, key=lambda x: -min(x[1]))]
    (ROOT / "data" / "knowledge" / "myomi_scan.json").write_text(json.dumps(
        {"_meta": "妙味度（単勝・複勝の回収率の平均を全体の平均で割った値×100）の総当たり（tools/myomi_scan.py）。3期とも105以上・各期20走以上",
         "test": {"picked_train": len(tr_pick), "runs": tot[0], "tan": round(test_tan), "fuku": round(test_fuku)}, "items": items},
        ensure_ascii=False, indent=0), encoding="utf-8")
    L = ["# 妙味度の総当たり（tools/myomi_scan.py, 2026-11-08。卍『中央競馬 妙味度名鑑 2026』の考え方をこちらのDBで作り直し）", "",
         "妙味度＝その条件での単勝・複勝の回収率の平均 ÷ 全体の平均回収率 ×100（100が平均）。騎手・調教師 × 芝/ダ・競馬場・距離帯・左右回り・道悪・クラス・年齢・休み明け何走目。", "",
         f"## 未来を見ない確かめ: 2021-22 / 2023 / 2024 で3期とも105以上だった {len(tr_pick)} 組 → 2025-01〜26-09 で {tot[0]} 走・単勝回収 {test_tan:.0f}%・複勝回収 {test_fuku:.0f}%", "",
         f"## 本番用: 2021-23 / 2024 / 2025-26/9 で3期とも105以上 {len(items)} 組", "",
         "| 誰 | 名前 | 条件 | 妙味度（3期） | 走数（3期） |", "|---|---|---|---|---|"]
    L += [f"| {x['who']} | {x['name']} | {x['cond']} | {'/'.join(map(str, x['myomi']))} | {'/'.join(map(str, x['n']))} |" for x in items]
    (ROOT / "docs" / "analysis" / "myomi_scan.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:7]))


if __name__ == "__main__":
    main()
