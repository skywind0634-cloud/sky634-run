"""双馬 第2章（p66-77）ディープインパクト・キングカメハメハのクセの検証（2026-10-15）.
本は2頭とも古い（ディープは2019年死去・最終世代2020年生、キンカメは2019年死去）ので、後継（ディープ系・キングカメハメハ系の他の種牡馬）でも同じ検証をする。
ディープ: ①広いコース（東京・新潟の芝）◎ / ローカル小回り芝1800（福島・小倉・函館・札幌）× ②母父の国別タイプ×年齢×性別（母父米国型は2-3歳◎・古馬牡で劣化、母父欧州型は古馬で開花、牝は劣化しにくい）
  ③牡4歳以上×母父米国型×馬体重500kg以上 ④牡5歳以上×1-3番人気（過去の栄光で人気）⑤そのレースのペース（テンが遅い/上がりが速い）
キンカメ: ⑥母父の国別タイプ（日本型=瞬発力・米国型=持続力・欧州型=スタミナ）× 東京芝・芝2200m以上・芝道悪・ダート・ローカル芝
  ⑦高速馬場（当日・前日の同場の芝の勝ちタイムがコース平均より0.5秒以上速い）×母父タイプ ⑧母父米国型でも母母父サンデー系なら東京芝の瞬発力勝負向き
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/souma_ch2a.py [ped5_full.json] → docs/analysis/souma_ch2a.md
"""
import datetime as dt
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

LOCAL = {"福島", "小倉", "函館", "札幌"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main(pedpath=None):
    ddss = {}
    if pedpath and Path(pedpath).exists():
        for hid, n in json.loads(Path(pedpath).read_text(encoding="utf-8"))["horses"].items():
            ddss[hid] = len(n) > 26 and ("サンデーサイレンス" in (n[12], n[26]))
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, going, f3, l3, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,going,first3f,last3f,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, going=going or "良", f3=f3, l3=l3, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0]); wtime = {}
    for rid, hid, fin, pop, num, age, sex, bw, tsec, sire, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.age,r.sex,r.body_weight,r.time_sec,h.sire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        if fin == 1 and tsec:
            wtime[rid] = tsec
        g = ("ディープインパクト" if sire == "ディープインパクト" else "ディープ系後継" if sl == "ディープインパクト系"
             else "キングカメハメハ" if sire == "キングカメハメハ" else "キンカメ系後継" if sl == "キングカメハメハ系" else None)
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, age=age or 9, male=not str(sex or "").startswith("牝"),
                              bw=bw or 0, g=g, sire=sire, dt=country_type(dsl) if dsl else None))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    cm = defaultdict(lambda: defaultdict(list))  # kind -> (co,su,dist) -> list
    day = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"]); key = (R["co"], su, R["dist"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}

        def dev(kind, v):
            L = cm[kind][key]
            return v - sum(L[-200:]) / len(L[-200:]) if v and len(L) >= 10 else None
        f3d, l3d, wtd = dev("f3", R["f3"]), dev("l3", R["l3"]), dev("wt", wtime.get(rid))
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        sp = day[(R["date"], R["co"], su)] + day[(prev_day, R["co"], su)]
        fast_day = (sum(sp) / len(sp) <= -0.5) if len(sp) >= 2 else None
        for x in rows[rid]:
            g = x["g"]
            if not g:
                continue
            pb = pband(x["pop"]); K = []
            ag = "2-3歳" if x["age"] <= 3 else "4歳" if x["age"] == 4 else "5歳以上"
            sx = "牡セ" if x["male"] else "牝"
            if g in ("ディープインパクト", "ディープ系後継") and su == "芝":
                ct = "東京・新潟" if R["co"] in ("東京", "新潟") else "ローカル小回り" if R["co"] in LOCAL else "その他"
                K.append(("①コース", f"{ct}・{'1800m' if R['dist'] == 1800 else '1800m以外'}", "全体"))
                if x["dt"]:
                    K.append(("②母父タイプ×年齢×性別", f"母父{x['dt']}・{ag}・{sx}", "全体"))
                if x["male"] and x["age"] >= 4 and x["dt"] == "米国型":
                    K.append(("③牡4歳以上×母父米国型×馬体重", "500kg以上" if x["bw"] >= 500 else "500kg未満", "全体"))
                if x["male"] and x["age"] >= 5:
                    K.append(("④牡5歳以上×人気", pb, pb))
                if f3d is not None:
                    K.append(("⑤そのレースのテン（結果, 理解用）", "遅い(+0.5秒以上)" if f3d >= 0.5 else "速い(-0.5秒以上)" if f3d <= -0.5 else "平均", "全体"))
                if l3d is not None:
                    K.append(("⑤そのレースの上がり（結果, 理解用）", "速い(-0.5秒以上)" if l3d <= -0.5 else "遅い(+0.5秒以上)" if l3d >= 0.5 else "平均", "全体"))
            if g in ("キングカメハメハ", "キンカメ系後継") and x["dt"]:
                conds = []
                if su == "ダ":
                    conds.append("ダート")
                else:
                    if R["co"] == "東京":
                        conds.append("東京芝")
                    if R["co"] in LOCAL:
                        conds.append("ローカル小回り芝")
                    if R["dist"] >= 2200:
                        conds.append("芝2200m以上")
                    if not R["going"].startswith("良"):
                        conds.append("芝道悪")
                    if wtd is not None and wtd <= -0.5:
                        conds.append("芝で勝ちタイムが速い（結果, 理解用）")
                    if fast_day:
                        conds.append("芝の高速日（当日・前日の同場が速い）")
                for cd in conds:
                    K.append(("⑥⑦母父タイプ×条件", f"{cd}・母父{x['dt']}", "全体"))
                if su == "芝" and R["co"] == "東京" and x["dt"] == "米国型" and x["hid"] in ddss:
                    K.append(("⑧東京芝×母父米国型", "母母父サンデー" if ddss[x["hid"]] else "母母父サンデー以外", "全体"))
            for k in K:
                k = (g,) + k
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        for kind, v in (("f3", R["f3"]), ("l3", R["l3"]), ("wt", wtime.get(rid))):
            if v:
                cm[kind][key].append(v)
        if wtd is not None:
            day[(R["date"], R["co"], su)].append(wtd)

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""

    L = ["# 双馬 第2章（p66-77）ディープインパクト・キングカメハメハのクセの検証（自動生成 tools/souma_ch2a.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。後継＝同じ系統の他の種牡馬。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 父 | 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {k[1]} | {mark(ae)}{k[2]} | {k[3]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_ch2a.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
