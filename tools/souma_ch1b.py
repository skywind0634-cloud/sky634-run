"""双馬 第1章（p52-64）の検証（2026-10-15）.
A) 異質な馬: 延長向き血統（父欧州型 or 本の延長得意リスト）なのに過去の短縮で好走 / 短縮向き血統（父米国型）なのに過去の延長で好走 → 今回ローテ × 人気
B) 2-3歳（3歳は6月まで）× ローテ × 人気。3歳前半の芝1600以下: 前走1800m以上組 vs 1400m以下組。新馬戦の距離（data/debut.db）1800m以上 vs 1400m以下
C) 父の国別タイプ × ローテ。父日本型は母父の国別タイプ × ローテ（本『サンデー系は母父で決まる』）
D) 当日の馬場: 同じ日・同じ場・同じ芝ダの先に行われたレース（＋前日の同場）で
   短縮馬が人気以上に来ている / 芝でダ→芝替わりの馬が3着内 / 上がりがコース平均より速い・遅い → 今回の短縮・延長。道悪×短縮、小倉芝×延長、
   上がりが速い日 × 父米国型 / 過去に上がり33.5秒以下の経験
好走＝人気より上の着順で5着以内かつ上がり3位以内（双馬の定義）。A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/souma_ch1b.py → docs/analysis/souma_ch1b.md
"""
import datetime as dt
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from souma_ability import EXT_SIRES  # noqa: E402


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def rot(a, b):
    dd = a - b
    return "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, going, l3, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,going,last3f,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, going=going or "良", l3=l3, pay=json.loads(pay) if pay else {})
    debut = {}
    try:
        d = sqlite3.connect(ROOT / "data" / "debut.db")
        for hid, su, dist in d.execute("select r.horse_id,ra.surface,ra.distance from results r join races ra using(race_id)"):
            debut[hid] = (su, dist)
    except sqlite3.Error:
        pass
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, age, l3, sire, ds, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.age,r.last3f,h.sire,h.damsire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, age=age or 9, l3=l3, sire=sire,
                                  st=country_type(sl) if sl else None, dt=country_type(dsl) if dsl else None))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = defaultdict(list)  # hid -> [(su, dist, rot, fin, pop, l3rank, l3)]
    day = defaultdict(lambda: dict(srt=0.0, ds_top3=0, l3d=[], n=0))  # (date, co, su)
    cl3 = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"]); mo = int(R["date"][5:7])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        l3s = sorted(x["l3"] for x in rows[rid] if x["l3"])
        for x in rows[rid]:
            x["l3r"] = (l3s.index(x["l3"]) + 1) if x["l3"] else 99
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        D0, D1 = day[(R["date"], R["co"], su)], day[(prev_day, R["co"], su)]
        dn = D0["n"] + D1["n"]
        srt = D0["srt"] + D1["srt"]; dtop = D0["ds_top3"] + D1["ds_top3"]; l3d = D0["l3d"] + D1["l3d"]
        ckey = (R["co"], su, R["dist"])
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h[0] == su]
            r1 = rot(R["dist"], H[-1][1]) if H else None
            pb = pband(x["pop"]); K = []
            young = x["age"] == 2 or (x["age"] == 3 and mo <= 6)
            # A) 異質な馬
            ext_b = x["st"] == "欧州型" or x["sire"] in EXT_SIRES
            sht_b = x["st"] == "米国型"
            good = lambda h: h[3] <= 5 and h[3] < h[4] and h[5] <= 3
            g_s = any(h[2] == "短縮" and good(h) for h in H); g_e = any(h[2] == "延長" and good(h) for h in H)
            if r1 and ext_b and g_s:
                K.append(("A異質: 延長向き血統（父欧州型/本のリスト）なのに短縮で好走歴", f"{su}・今回{r1}", pb))
            if r1 and ext_b and g_e and not g_s:
                K.append(("A普通: 延長向き血統で延長でだけ好走歴（比較用）", f"{su}・今回{r1}", pb))
            if r1 and sht_b and g_e:
                K.append(("A異質: 短縮向き血統（父米国型）なのに延長で好走歴", f"{su}・今回{r1}", pb))
            if r1 and sht_b and g_s and not g_e:
                K.append(("A普通: 短縮向き血統で短縮でだけ好走歴（比較用）", f"{su}・今回{r1}", pb))
            # B) 2-3歳
            if r1 and young:
                K.append(("B2-3歳（3歳は6月まで）×ローテ", f"{su}・{r1}", pb))
            if r1 and not young:
                K.append(("B古馬（比較用）×ローテ", f"{su}・{r1}", pb))
            if young and su == "芝" and R["dist"] <= 1600 and H:
                pd_ = H[-1][1]
                if pd_ >= 1800 or pd_ <= 1400:
                    K.append(("B2-3歳の芝1600以下: 前走距離", f"前走{'1800m以上' if pd_ >= 1800 else '1400m以下'}", pb))
            if young and x["hid"] in debut and debut[x["hid"]][0] == "芝" and su == "芝":
                dd_ = debut[x["hid"]][1]
                if dd_ >= 1800 or dd_ <= 1400:
                    K.append(("B2-3歳の芝: 新馬戦の距離", f"新馬{'1800m以上' if dd_ >= 1800 else '1400m以下'}・今回{'1800m以上' if R['dist'] >= 1800 else '1600m以下'}", pb))
            # C) 国別タイプ × ローテ
            if r1 and x["st"]:
                K.append(("C父の国別タイプ×ローテ", f"{su}・父{x['st']}・{r1}", "全体"))
                if x["st"] == "日本型" and x["dt"]:
                    K.append(("C父日本型×母父の国別タイプ×ローテ", f"{su}・母父{x['dt']}・{r1}", "全体"))
            # D) 当日の馬場
            if r1 and dn >= 2:
                K.append(("D当日・前日の同場で短縮馬が", f"{su}・{'人気以上（+0.5頭以上）' if srt >= 0.5 else '人気以下（-0.5頭以下）' if srt <= -0.5 else '人気なり'}→今回{r1}", "全体"))
                if su == "芝":
                    K.append(("D当日・前日の同場の芝でダ→芝替わりの馬が", f"{'3着内あり' if dtop else '3着内なし'}→今回{r1}", "全体"))
                if l3d:
                    m = sum(l3d) / len(l3d)
                    tag = "速い（平均より-0.5秒以上）" if m <= -0.5 else "遅い（+0.5秒以上）" if m >= 0.5 else "平均的"
                    K.append(("D当日・前日の同場の上がりが", f"{su}・{tag}→今回{r1}", "全体"))
                    if m <= -0.5 and su == "芝":
                        if x["st"] == "米国型":
                            K.append(("D上がりが速い日の芝", "父米国型", pb))
                        if any(h[6] and h[6] <= 33.5 for h in H):
                            K.append(("D上がりが速い日の芝", "過去に上がり33.5秒以下の経験あり", pb))
            if r1:
                if not R["going"].startswith("良"):
                    K.append(("D道悪×ローテ", f"{su}・{r1}", "全体"))
                if R["co"] == "小倉" and su == "芝":
                    K.append(("D小倉芝×ローテ", f"{r1}", "全体"))
            for k in K:
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        # 当日の集計を更新
        if R["l3"] and len(cl3[ckey]) >= 10:
            D0["l3d"].append(R["l3"] - sum(cl3[ckey][-200:]) / len(cl3[ckey][-200:]))
        if R["l3"]:
            cl3[ckey].append(R["l3"])
        D0["n"] += 1
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h[0] == su]
            r1 = rot(R["dist"], H[-1][1]) if H else None
            if r1 == "短縮":
                D0["srt"] += (x["fin"] <= 3) - exp[x["p"]]
            if su == "芝" and hist[x["hid"]] and hist[x["hid"]][-1][0] == "ダ" and x["fin"] <= 3:
                D0["ds_top3"] += 1
        for x in rows[rid]:
            H = [h for h in hist[x["hid"]] if h[0] == su]
            hist[x["hid"]].append((su, R["dist"], rot(R["dist"], H[-1][1]) if H else None, x["fin"], x["pop"], x["l3r"], x["l3"]))

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""

    L = ["# 双馬 第1章（p52-64）異質な馬・2-3歳の短縮・国別タイプ・当日の馬場の検証（自動生成 tools/souma_ch1b.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。前走は DB 内の同じ芝ダの前走。",
         "- 好走＝人気より上の着順で5着以内かつ上がり3位以内。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {mark(ae)}{k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_ch1b.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
