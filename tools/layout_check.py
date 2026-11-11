"""内回り/外回りで傾向が変わるか（2026-10-15, ユーザー指摘: 京都・新潟などは内回りと外回りで直線の長さが違う）.
京都・阪神・新潟・中山の芝 × 内回り/外回り（races.layout, レース結果の表記）ごとに:
 ①脚質（前走の最初のコーナー位置: 前15% / 中団 / 後方40%）× 人気帯  ②枠（1-3 / 4-6 / 7-8）
 ③父系統（100走以上）④父の国別タイプ ⑤前走が同じ場の逆の回り（内→外 / 外→内）
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。各期間30走以上。
使い方: python3 tools/layout_check.py → docs/analysis/layout_check.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, su, dist, n, lay, pay in c.execute(
            "select race_id,date,course,surface,distance,n_runners,layout,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, su=su, dist=dist, n=n or 16, lay=lay, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0])
    for rid, hid, fin, pop, num, gate, pas, sl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.gate,r.passing,h.sire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        try:
            p0 = int(str(pas).split("-")[0])
        except ValueError:
            p0 = None
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, gate=gate or 0, p0=p0, sl=sl, st=country_type(sl) if sl else None))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = {}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    nolay = 0
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; pr = per(R["date"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        tgt = R["su"] == "芝" and R["co"] in ("京都", "阪神", "新潟", "中山") and R["lay"] in ("内", "外")
        if R["su"] == "芝" and R["co"] in ("京都", "阪神", "新潟", "中山") and not R["lay"]:
            nolay += 1
        if tgt:
            cl = f"{R['co']}芝{'外回り' if R['lay'] == '外' else '内回り'}"
            for x in rows[rid]:
                pv = hist.get(x["hid"]); pb = pband(x["pop"]); K = []
                if pv and pv[0] is not None:
                    K.append(("①前走の位置取り", f"{'前15%' if pv[0] <= 0.15 else '後方40%' if pv[0] > 0.6 else '中団'}", pb))
                K.append(("②枠", f"{'1-3枠' if x['gate'] <= 3 else '4-6枠' if x['gate'] <= 6 else '7-8枠'}", "全体"))
                if x["sl"]:
                    K.append(("③父系統", x["sl"], "全体"))
                if x["st"]:
                    K.append(("④父の国別タイプ", x["st"], "全体"))
                if pv and pv[1] == R["co"] and pv[2] and pv[2] != R["lay"]:
                    K.append(("⑤前走が同じ場の逆の回り", f"前走{'外' if pv[2] == '外' else '内'}回り→今回{'外' if R['lay'] == '外' else '内'}回り", "全体"))
                for k in K:
                    k = (cl,) + k
                    a = agg[k][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += exp[x["p"]]; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        for x in rows[rid]:
            hist[x["hid"]] = (x["p0"] / max(R["n"], 1) if x["p0"] else None, R["co"] if R["su"] == "芝" else None, R["lay"] if R["su"] == "芝" else None)

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
    L = ["# 内回り/外回りで傾向が変わるか（自動生成 tools/layout_check.py）", "",
         f"- 京都・阪神・新潟・中山の芝。内回り/外回りはレース結果の表記（races.layout）。未判定のレース {nolay} は除外。",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各30走以上）。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| コース | 見方 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {k[1]} | {mark(ae)}{k[2]} | {k[3]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "layout_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
