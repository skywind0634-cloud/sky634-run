"""双馬『1頭の種牡馬のクセ』第1章（前走より楽に感じると好走する）の検証と掘り下げ（2026-10-15）.
1) ローテ（同じ芝ダの前走比 短縮/延長/同距離, 変化幅）× 人気帯
2) 2走のローテの並び（前走のローテ→今回のローテ）× 前走の結果（3着内/4着以下）… 「短縮で好走→同距離（反動）」「延長で凡走→次走」
3) 引っかかり気味（前走の1コーナー位置が過去平均より0.25以上前で、6着以下）× 今回のローテ
4) 短距離血統（父の芝勝ち鞍平均1500m以下）で、前走まで1600m以上ばかり → 初めて1400m以下
5) その馬自身のローテ別成績（過去の短縮で3着内率が他より高い）× 今回短縮
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。
使い方: python3 tools/souma_rotation.py → docs/analysis/souma_rotation.md
"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def rot(dist, prev):
    if prev is None:
        return None
    dd = dist - prev
    return "短縮" if dd <= -200 else "延長" if dd >= 200 else "同距離"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {r[0]: dict(date=r[1], su=r[2], dist=r[3] or 1600, n=r[4] or 16, pay=json.loads(r[5]) if r[5] else {})
             for r in c.execute("select race_id,date,surface,distance,n_runners,payouts from races where surface in ('芝','ダ')")}
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, pas, sire in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.passing,h.sire from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, pas=pas, sire=sire))
            b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    # 父の芝の平均勝ち距離（短距離血統の判定）
    sw = defaultdict(list)
    for rid, rs in rows.items():
        if races[rid]["su"] == "芝":
            for x in rs:
                if x["fin"] == 1 and x["sire"]:
                    sw[x["sire"]].append(races[rid]["dist"])
    sprint = {s for s, v in sw.items() if len(v) >= 15 and sum(v) / len(v) <= 1500}
    hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        for x in rs_ if (rs_ := rows[rid]) else []:
            h = [y for y in hist[x["hid"]] if y["su"] == su]
            band = "1番人気" if x["pop"] == 1 else "2-3番人気" if x["pop"] <= 3 else "4-6番人気" if x["pop"] <= 6 else "7番人気以下"
            K = []
            if h:
                r1 = rot(R["dist"], h[-1]["dist"])
                dd = R["dist"] - h[-1]["dist"]
                K += [("①ローテ", f"{su}・{r1}", "全体"), ("①ローテ", f"{su}・{r1}", band)]
                if r1 != "同距離":
                    K.append(("①変化幅", f"{su}・{r1}{'400m以上' if abs(dd) >= 400 else '200m'}", "全体"))
                if len(h) >= 2:
                    r0 = rot(h[-1]["dist"], h[-2]["dist"])
                    res = "好走(3着内)" if (h[-1]["fin"] or 99) <= 3 else "凡走(6着以下)" if (h[-1]["fin"] or 99) >= 6 else "4-5着"
                    K += [("②前走ローテ→今回", f"{su}・前走{r0}で{res}→今回{r1}", "全体"), ("②前走ローテ→今回", f"{su}・前走{r0}で{res}→今回{r1}", band)]
                # 引っかかり気味
                ps = [y["pos"] for y in h[:-1][-4:] if y["pos"] is not None]
                if h[-1]["pos"] is not None and len(ps) >= 2 and h[-1]["pos"] <= sum(ps) / len(ps) - 0.25 and (h[-1]["fin"] or 0) >= 6:
                    K.append(("③前走で前に行きすぎて失速", f"{su}・今回{r1}", "全体"))
                # 短距離血統の初短距離
                if su == "芝" and x["sire"] in sprint and R["dist"] <= 1400 and len(h) >= 2 and all(y["dist"] >= 1600 for y in h):
                    K.append(("④短距離血統（父）が初めて芝1400以下", "芝", "全体"))
                # その馬自身の短縮成績
                own = defaultdict(lambda: [0, 0])
                for i in range(1, len(h)):
                    rr = rot(h[i]["dist"], h[i - 1]["dist"]); o = own[rr]; o[0] += 1; o[1] += (h[i]["fin"] or 99) <= 3
                s_, o_ = own["短縮"], [own["延長"][0] + own["同距離"][0], own["延長"][1] + own["同距離"][1]]
                if s_[0] >= 2 and o_[0] >= 2 and r1 == "短縮":
                    lab = "過去の短縮で好走率が高い馬" if s_[1] / s_[0] >= o_[1] / o_[0] + 0.25 else "過去の短縮で好走率が低い馬" if s_[1] / s_[0] <= o_[1] / o_[0] - 0.25 else "差なし"
                    K.append(("⑤その馬の短縮実績×今回短縮", f"{su}・{lab}", "全体"))
            for k in K:
                a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        for x in rows[rid]:
            try:
                pos = int(str(x["pas"]).split("-")[0]) / R["n"]
            except (ValueError, TypeError):
                pos = None
            hist[x["hid"]].append(dict(su=su, dist=R["dist"], fin=x["fin"], pos=pos))
    L = ["# 双馬『1頭の種牡馬のクセ』第1章（前走より楽なら好走）の検証と掘り下げ（自動生成 tools/souma_rotation.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各日7R以降（未勝利除く）。ローテは同じ芝ダの前走比±200m。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 主張 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 40:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "souma_rotation.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
