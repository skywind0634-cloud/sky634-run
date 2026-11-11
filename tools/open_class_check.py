"""①〜⑬で見つけた材料を、全クラスと OP以上（OP・L・G3・G2・G1）で比べる（2026-10-12）.
各材料について 発見2021-23 / 確認2024 / テスト2025-26 の 3着内A/E（人気から見込む数との比）と複勝・単勝回収率。
人気から見込む率はクラス別（OP以上はOP以上の人気別3着内率）で出す。
使い方: python3 tools/open_class_check.py → docs/analysis/open_class_check.md, data/knowledge/open_class_check.json
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
T_SUN = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "スペシャルウィーク系"}
D_SUN = {"ゴールドアリュール系", "ネオユニヴァース系"}
ROBERTO = {"スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系"}
MISPRO = {"キングカメハメハ系", "キングマンボ系", "フォーティナイナー系", "ファピアノ系", "シーキングザゴールド系", "ゴーンウエスト系", "マキャヴェリアン系",
          "スマートストライク系", "ミスタープロスペクター系"}
OPEN = {"OP", "L", "G3", "G2", "G1"}
SLOPE = {"中山", "阪神", "中京", "東京"}
LONG = {"東京", "新潟", "阪神", "京都", "中京"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, su, dist, going, grade, pay in c.execute(
            "select race_id,date,course,surface,distance,going,grade,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, going=going or "良", grade=grade, pay=json.loads(pay) if pay else {})
    rows = defaultdict(list)
    for rid, hid, fin, num, pop, age, sex, wc, t, sl, dsl, sire in c.execute(
            """select r.race_id,r.horse_id,r.finish,r.number,r.popularity,r.age,r.sex,r.weight_carried,r.time_sec,h.sire_line,h.damsire_line,h.sire
               from results r left join horses h using(horse_id)"""):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, num=num, pop=pop, age=age, sex=sex or "", wc=wc, t=t, sl=sl, dsl=dsl, sire=sire))
    base = {k: defaultdict(lambda: [0, 0]) for k in ("全クラス", "OP以上")}
    for rid, rs in rows.items():
        cl = "OP以上" if races[rid]["grade"] in OPEN else "全クラス"
        for x in rs:
            if x["fin"] and x["pop"]:
                for k in {cl, "全クラス"}:
                    b = base[k][min(x["pop"], 14)]; b[0] += 1; b[1] += x["fin"] <= 3
    exp = {k: {p: v[1] / v[0] for p, v in d.items()} for k, d in base.items()}
    hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; rs = rows[rid]; su, d, co = R["su"], R["dist"], R["co"]
        good = R["going"].startswith("良"); pr = per(R["date"])
        cls = ["全クラス"] + (["OP以上"] if R["grade"] in OPEN else [])
        wt = min((x["t"] for x in rs if x["fin"] == 1 and x["t"]), default=None)
        wcs = [x["wc"] for x in rs if x["wc"]]
        top3 = [x for x in rs if x["pop"] and x["pop"] <= 3]
        gap_race = (not good and su == "芝" and len(top3) == 3 and all(country_type(x["sl"]) == "日本型" for x in top3 if x["sl"]))
        fk = {cc: y for cc, y in R["pay"].get("複勝", [])}; tk = {cc: y for cc, y in R["pay"].get("単勝", [])}
        for x in rs:
            if not x["fin"] or not x["pop"]:
                continue
            st = country_type(x["sl"]) if x["sl"] else None; dt_ = country_type(x["dsl"]) if x["dsl"] else None
            h = hist[x["hid"]]; prv = h[-1] if h else None
            F = []
            # 基本の切り口
            if st:
                F += [f"父{st}×{su}", f"父{st}×{su}・{'良' if good else '道悪'}", f"父{st}×{su}・{'坂' if co in SLOPE else '平坦'}",
                      f"父{st}×{su}・直線{'長' if co in LONG else '短'}"]
                if su == "芝" and 1600 <= d <= 2500:
                    F.append(f"父{st}×芝・{'根幹' if d in (1600, 2000, 2400) else '非根幹'}")
            if x["sl"] in SS:
                F.append(f"父サンデー系×{su}")
            if x["sl"] in MISPRO:
                F.append(f"父ミスプロ系×{su}")
            F.append(f"{su}・{'牝' if x['sex'].startswith('牝') else '牡セ'}")
            if x["age"]:
                F.append(f"{su}・{'3歳' if x['age'] <= 3 else '4歳' if x['age'] == 4 else '5歳' if x['age'] == 5 else '6歳以上'}")
            if wcs and max(wcs) - min(wcs) >= 4 and x["wc"]:
                F.append(f"{su}・斤量差4kg以上のレースで" + ("トップ〜1kg差" if x["wc"] >= max(wcs) - 1 else "4kg以上軽い" if x["wc"] <= max(wcs) - 4 else "中間"))
            F.append(f"{su}・{'内枠1-4番' if x['num'] <= 4 else '外枠13番以降' if x['num'] >= 13 else '中枠'}")
            # これまでの材料
            if prv:
                days = (dt.date.fromisoformat(R["date"]) - dt.date.fromisoformat(prv["date"])).days
                F.append(f"{su}・{'休み明け(中9週以上)' if days >= 63 else '叩き2戦目' if prv['rest'] else '続戦'}")
                if days >= 63 and st:
                    F.append(f"{su}・休み明け×父{st}")
                if abs(d - prv["dist"]) >= 200:
                    F.append(f"{su}・{'延長' if d > prv['dist'] else '短縮'}")
                    if st:
                        F.append(f"{su}・{'延長' if d > prv['dist'] else '短縮'}×父{st}")
                if prv["su"] != su:
                    F.append(f"{prv['su']}→{su}")
                    if x["sl"] in SS:
                        F.append(f"{prv['su']}→{su}×父サンデー系")
                    if st:
                        F.append(f"{prv['su']}→{su}×父{st}")
                if su == "ダ" and all(y["su"] == "芝" for y in h):
                    F.append("初ダート")
                if su == "ダ" and d <= prv["dist"] - 200 and st == "米国型" and x["num"] >= 10:
                    F.append("ダ短縮×父米国型×2桁馬番")
                bs = [y["b"] for y in h[-3:] if y["b"] is not None]
                if len(bs) >= 2 and min(bs) >= 1.5:
                    F.append("近走すべて1.5秒以上負け")
                if prv["b"] is not None and prv["b"] <= 0.3 and prv["fin"] and prv["fin"] >= 2:
                    F.append(f"{su}・前走0.3秒差以内の負け")
                if prv["fin"] == 1:
                    F.append(f"{su}・前走1着")
                if prv["grade"] not in OPEN and R["grade"] in OPEN:
                    F.append(f"{su}・昇級（条件戦→OP以上）")
            if su == "ダ" and x["sl"] in D_SUN:
                F.append("Dサンデー×ダ")
            if su == "芝" and d >= 2200 and x["sl"] in T_SUN:
                F.append("Tサンデー×芝2200以上")
            if su == "芝" and d >= 2500 and dt_ == "欧州型":
                F.append("芝2500以上×母父欧州型")
            if su == "芝" and 2000 <= d <= 2400 and x["dsl"] == "ディープインパクト系":
                F.append("母父ディープ×芝2000-2400")
            if su == "芝" and co in ("札幌", "函館") and x["sl"] in ("ステイゴールド系", "ハーツクライ系", "マンハッタンカフェ系"):
                F.append("洋芝×ステゴ/ハーツ/マンカフェ系")
            if su == "ダ" and (x["age"] or 0) >= 5 and x["sl"] in ROBERTO:
                F.append("ロベルト系×ダ5歳以上")
            if gap_race and 4 <= x["pop"] <= 9 and st in ("欧州型", "米国型"):
                F.append("主流/反主流のずれ（芝道悪・人気上位が日本型）×反主流の4-9番人気")
            if su == "芝" and d >= 2000 and x["age"] == 3 and R["date"][5:7] <= "06" and x["sl"] == "ディープインパクト系":
                F.append("3歳前半×父ディープ×芝2000以上")
            for cl in cls:
                e = exp[cl][min(x["pop"], 14)]
                for f in F:
                    a = agg[(cl, f)][pr]; a[0] += 1; a[1] += x["fin"] <= 3; a[2] += e; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        for x in rs:
            hist[x["hid"]].append(dict(date=R["date"], su=su, dist=d, fin=x["fin"], grade=R["grade"],
                                       b=(x["t"] - wt) if (x["t"] and wt and x["fin"]) else None, rest=False))
        for x in rs:
            h = hist[x["hid"]]
            if len(h) >= 2:
                h[-1]["rest"] = (dt.date.fromisoformat(h[-1]["date"]) - dt.date.fromisoformat(h[-2]["date"])).days >= 63
    feats = sorted({f for (cl, f) in agg})
    L = ["# ①〜⑬の材料：全クラス vs OP以上（OP・L・重賞）（自動生成 tools/open_class_check.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数（OP以上はOP以上の人気別3着内率で見込む）。発見2021-23 / 確認2024 / テスト2025-26。",
         "- ◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下（OP以上は各期間30走以上）。「OPで強まる」＝OP以上の印が全クラスより強いもの。", "",
         "| 材料 | 全クラス A/E | 全クラス 複/単回収 | OP以上 A/E | OP以上 複/単回収 | OP以上 走数 | |", "|---|---|---|---|---|---|---|"]
    out = []

    def mark(ae):
        return "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""

    for f in feats:
        A, B = agg.get(("全クラス", f)), agg.get(("OP以上", f))
        if not A or not B or min(x[0] for x in B) < 30:
            continue
        ae_a = [x[1] / x[2] for x in A]; ae_b = [x[1] / x[2] for x in B]
        ma, mb = mark(ae_a), mark(ae_b)
        if not (ma or mb):
            continue
        rank = {"◎": 2, "○": 1, "": 0, "▽": -1, "×": -2}
        note = "OPで強まる" if abs(rank[mb]) > abs(rank[ma]) else "OPで弱まる" if abs(rank[mb]) < abs(rank[ma]) else ""
        fu = lambda X: "/".join(f"{x[3]/x[0]:.0f}" for x in X) + "% ・ " + "/".join(f"{x[4]/x[0]:.0f}" for x in X) + "%"
        L.append(f"| {f} | {ma}" + "/".join(f"{v:.2f}" for v in ae_a) + f" | {fu(A)} | {mb}" + "/".join(f"{v:.2f}" for v in ae_b) + f" | {fu(B)} | "
                 + "/".join(str(x[0]) for x in B) + f" | {note} |")
        if mb:
            out.append({"feature": f, "mark": mb, "ae": [round(v, 2) for v in ae_b], "fuku": [round(x[3] / x[0]) for x in B],
                        "tan": [round(x[4] / x[0]) for x in B], "n": [x[0] for x in B], "all_mark": ma})
    (ROOT / "docs" / "analysis" / "open_class_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "open_class_check.json").write_text(json.dumps({"_meta": "tools/open_class_check.py: OP以上で3期間一貫した材料", "rows": out},
                                                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
