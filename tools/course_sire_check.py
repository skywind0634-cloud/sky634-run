"""コース別の種牡馬・血統の主張を検証する汎用ツール（コース別種牡馬本の検証用, 2026-10-15）.
指定コース（場×芝ダ×距離, 距離は省略可）について:
 ①種牡馬別（各期間20走以上）×人気帯（1-3 / 4番人気以下） ②父×性別 ③父×年齢（2-3 / 4 / 5歳以上）
 ④母父（各期間20走以上） ⑤5代の祖先フラグ（ped5_flags.json） ⑥開催時期（1-2月 / 3-6月 / 9-12月 / 7-8月）×父の国別タイプ・サドラーズ持ち
 ⑦脚質（前走の最初のコーナー位置）×枠 ⑧当日・前日の同場の時計（高速日 / 平均 / 時計がかかる日）×枠 ⑨クラス（OP以上/条件戦）×父 ④母父系統
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。
使い方: python3 tools/course_sire_check.py <出力名> <場> <芝|ダ> [距離 ...] → docs/analysis/<出力名>.md
"""
import datetime as dt
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(name, course, surface, dists):
    try:
        flags = json.loads((ROOT / "data/knowledge/ped5_flags.json").read_text(encoding="utf-8"))["flags"]
    except (OSError, ValueError, KeyError):
        flags = {}
    # コース改修（data/knowledge/courses.json の renovations）より前のレースは対象コースの集計から除く
    try:
        since = (json.loads((ROOT / "data/knowledge/courses.json").read_text(encoding="utf-8")).get("renovations", {}).get(course) or {}).get("since")
    except (OSError, ValueError):
        since = None
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, n, grade, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,n_runners,grade,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 0, n=n or 16, op=grade in ("OP", "L", "G3", "G2", "G1"),
                          pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0]); wtime = {}
    for rid, hid, fin, pop, num, gate, age, sex, pas, tsec, sire, ds, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.gate,r.age,r.sex,r.passing,r.time_sec,h.sire,h.damsire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        if fin == 1 and tsec:
            wtime[rid] = tsec
        try:
            p0 = int(str(pas).split("-")[0])
        except ValueError:
            p0 = None
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, gate=gate or 0, age=age or 9,
                              sex="牝" if str(sex or "").startswith("牝") else "牡セ", p0=p0, sire=sire, ds=ds, dsl=dsl, st=country_type(sl) if sl else None))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    cm = defaultdict(list); day = defaultdict(list); last = {}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r)):
        R = races[rid]; su = R["su"]; key = (R["co"], su, R["dist"])
        tgt = R["co"] == course and su == surface and (not dists or R["dist"] in dists) and (not since or R["date"] >= since)
        if tgt:
            pr = per(R["date"]); m = int(R["date"][5:7])
            fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
            prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
            sp = day[(R["date"], R["co"], su)] + day[(prev_day, R["co"], su)]
            ds_ = None if len(sp) < 2 else "高速日" if sum(sp) / len(sp) <= -0.5 else "時計がかかる日" if sum(sp) / len(sp) >= 0.5 else "平均的な日"
            season = "1-2月" if m <= 2 else "3-6月" if m <= 6 else "7-8月" if m <= 8 else "9-12月"
            for x in rows[rid]:
                pb = "1-3番人気" if x["pop"] <= 3 else "4番人気以下"
                gb = "1-3枠" if x["gate"] <= 3 else "4-6枠" if x["gate"] <= 6 else "7-8枠"
                fl = flags.get(x["hid"] or "", [])
                K = []
                if x["sire"]:
                    K += [("①父×人気", x["sire"], pb), ("①父", x["sire"], "全体"), ("②父×性別", x["sire"], x["sex"]),
                          ("③父×年齢", x["sire"], "2-3歳" if x["age"] <= 3 else "4歳" if x["age"] == 4 else "5歳以上")]
                if x["ds"]:
                    K.append(("④母父", x["ds"], "全体"))
                if x["dsl"]:
                    K.append(("④母父系統", x["dsl"], "全体"))
                if x["sire"]:
                    K.append(("⑨クラス×父", x["sire"], "OP以上" if R["op"] else "条件戦"))
                for f in fl:
                    K.append(("⑤5代の祖先", f, "全体"))
                if x["st"]:
                    K.append(("⑥時期×父の国別タイプ", f"{season}・父{x['st']}", "全体"))
                if "サドラーズウェルズ/ミルリーフ" in fl:
                    K.append(("⑥時期×5代にサドラーズ/ミルリーフ", season, "全体"))
                pz = last.get(x["hid"])
                if pz is not None:
                    K.append(("⑦前走の位置取り×枠", f"{'前15%' if pz <= 0.15 else '後方40%' if pz > 0.6 else '中団'}・{gb}", "全体"))
                if ds_:
                    K.append(("⑧当日の時計×枠", f"{ds_}・{gb}", "全体"))
                for k in K:
                    a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        wt = wtime.get(rid)
        if wt and len(cm[key]) >= 10:
            day[(R["date"], R["co"], su)].append(wt - sum(cm[key][-200:]) / len(cm[key][-200:]))
        if wt:
            cm[key].append(wt)
        for x in rows[rid]:
            last[x["hid"]] = x["p0"] / max(R["n"], 1) if x["p0"] else None

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = [f"# コース別検証: {course}{surface}{'・'.join(map(str, dists)) if dists else '全距離'}（自動生成 tools/course_sire_check.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各期間20走以上）。各日7R以降（未勝利除く）。"
         + (f"改修後（{since}〜）のレースのみ。" if since else ""),
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 見方 | 対象 | 区分 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 20:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {mark(ae)}{k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / f"{name}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    # 予想表示用: 3期間一貫した組（◎○×▽）を data/knowledge/course_sire_flags.json に保存（keiba/digest.py の course_check_horses が使う）
    kp = ROOT / "data" / "knowledge" / "course_sire_flags.json"
    try:
        kb = json.loads(kp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kb = {"_meta": "tools/course_sire_check.py。コース（場|芝ダ|距離, 距離空欄は全距離）ごとに3期間一貫した組", "specs": {}}
    spec = f"{course}|{surface}|{','.join(map(str, dists))}"
    rows_ = []
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 20:
            continue
        ae = [round(x[1] / x[2], 2) for x in A]
        if mark(ae):
            rows_.append({"k": list(k), "ae": ae, "mark": mark(ae), "fuku": [round(x[3] / x[0]) for x in A]})
    kb["specs"][spec] = {"source": name, "rows": rows_}
    kp.write_text(json.dumps(kb, ensure_ascii=False, indent=0), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], [int(x) for x in sys.argv[4:]])
