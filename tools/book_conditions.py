"""亀谷敬正『勝ち馬がわかる 血統の教科書』の切り口（11大系統→小系統 × レース条件①〜⑫）で、各系統が条件ごとに人気以上に走るかを検証する（2026-10-12）.

レース条件: ①芝/ダ ②芝コース ③ダートコース ④距離 ⑤直線の長短 ⑥坂の有無 ⑦距離短縮/延長 ⑧芝↔ダ替わり ⑨年齢（早熟/晩成）
⑩休み明け（鉄砲駆け）/叩き2戦目 ⑪ハンデ戦（同レースの斤量差4kg以上で代用） ⑫牡/牝。⑬新馬戦は DB 対象外。
父・母父それぞれの小系統と大系統で、3着内の A/E（人気から見込む数との比）と複勝・単勝回収率を 発見2021-23 / 確認2024 / テスト2025-26 で集計。
◎＝3期間とも A/E 1.10以上、×＝3期間とも0.90以下（各期間100走以上）。結果は data/knowledge/book_conditions.json と docs/analysis/book_conditions.md。

使い方: python3 tools/book_conditions.py
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

# DB の系統名 → 本の小系統（大系統）
BOOK = {
    "ディープインパクト系": ("ディープインパクト系", "サンデーサイレンス系"), "ハーツクライ系": ("ハーツクライ系", "サンデーサイレンス系"),
    "ステイゴールド系": ("ステイゴールド系", "サンデーサイレンス系"), "フジキセキ系": ("フジキセキ系", "サンデーサイレンス系"),
    "ゴールドアリュール系": ("ゴールドアリュール系", "サンデーサイレンス系"), "ネオユニヴァース系": ("ネオユニヴァース系", "サンデーサイレンス系"),
    "アグネスタキオン系": ("アグネスタキオン系", "サンデーサイレンス系"),
    **{k: ("サンデー系その他", "サンデーサイレンス系") for k in ("ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系")},
    "キングカメハメハ系": ("キングマンボ系", "ミスタープロスペクター系"), "キングマンボ系": ("キングマンボ系", "ミスタープロスペクター系"),
    "フォーティナイナー系": ("フォーティナイナー系", "ミスタープロスペクター系"), "ファピアノ系": ("ファピアノ系", "ミスタープロスペクター系"),
    **{k: ("ミスプロ系その他", "ミスタープロスペクター系") for k in ("シーキングザゴールド系", "ゴーンウエスト系", "マキャヴェリアン系", "スマートストライク系", "ミスタープロスペクター系")},
    **{k: ("ロベルト系", "ターントゥ系") for k in ("スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系")},
    "ヘイルトゥリーズン系": ("ヘイロー系", "ターントゥ系"),
    "エーピーインディ系": ("ボールドルーラー系", "ナスルーラ系"), "プリンスリーギフト系": ("プリンスリーギフト系", "ナスルーラ系"),
    "ナスルーラ系": ("ナスルーラ系その他", "ナスルーラ系"),
    **{k: ("ストームバード系", "ノーザンダンサー系") for k in ("ヘネシー系", "テイルオブザキャット系", "ジャイアンツコーズウェイ系", "フォレストリー系",
                                                         "ハーランズホリデー系", "スキャットダディ系", "ストームキャット系")},
    **{k: ("ダンチヒ系", "ノーザンダンサー系") for k in ("デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系")},
    "デピュティミニスター系": ("ヴァイスリージェント系", "ノーザンダンサー系"),
    "サドラーズウェルズ系": ("サドラーズウェルズ系", "ノーザンダンサー系"), "ガリレオ系": ("サドラーズウェルズ系", "ノーザンダンサー系"),
    "リファール系": ("リファール系", "ノーザンダンサー系"), "マルジュ系": ("ノーザンダンサー系その他", "ノーザンダンサー系"),
    "ノーザンダンサー系": ("ノーザンダンサー系その他", "ノーザンダンサー系"),
}
LONG_STRAIGHT = {"東京", "新潟", "阪神", "京都", "中京"}   # 直線400m以上（courses.json の straight, Aコース目安）
SLOPE = {"中山", "阪神", "中京", "東京"}
GR = {"1勝": 1, "2勝": 2, "3勝": 3, "OP": 4, "L": 4, "G3": 5, "G2": 6, "G1": 7}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def band(su, d):
    if su == "芝":
        return "芝〜1400" if d <= 1400 else "芝1600-1800" if d <= 1800 else "芝2000-2400" if d <= 2400 else "芝2500〜"
    return "ダ〜1400" if d <= 1400 else "ダ1600-1900" if d <= 1900 else "ダ2000〜"


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, su, dist, pay, going in c.execute(
            "select race_id,date,course,surface,distance,payouts,going from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, su=su, dist=dist or 1600, pay=json.loads(pay) if pay else {}, going=going or "良")
    rows = defaultdict(list)
    for rid, hid, fin, num, pop, sex, age, wc, sl, dsl in c.execute(
            """select r.race_id,r.horse_id,r.finish,r.number,r.popularity,r.sex,r.age,r.weight_carried,h.sire_line,h.damsire_line
               from results r left join horses h using(horse_id)"""):
        if rid in races:
            rows[rid].append(dict(hid=hid, fin=fin, num=num, pop=pop, sex=sex or "", age=age, wc=wc, sl=sl, dsl=dsl))
    base = defaultdict(lambda: [0, 0])
    for rs in rows.values():
        for x in rs:
            if x["fin"] and x["pop"]:
                b = base[min(x["pop"], 14)]; b[0] += 1; b[1] += x["fin"] <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], r)):
        R = races[rid]; rs = rows[rid]; su = R["su"]
        wcs = [x["wc"] for x in rs if x["wc"]]
        handi = bool(wcs) and max(wcs) - min(wcs) >= 4
        fk = {cc: y for cc, y in R["pay"].get("複勝", [])}; tk = {cc: y for cc, y in R["pay"].get("単勝", [])}
        pr = per(R["date"])
        for x in rs:
            if not x["fin"] or not x["pop"]:
                continue
            h = hist[x["hid"]]
            conds = [("①芝ダ", su), ("②③コース", f"{R['co']}{su}"), ("④距離", band(su, R["dist"])),
                     ("⑤直線", f"{su}・直線{'長' if R['co'] in LONG_STRAIGHT else '短'}"), ("⑥坂", f"{su}・{'坂' if R['co'] in SLOPE else '平坦'}"),
                     ("馬場", f"{su}・{'良' if R['going'].startswith('良') else '道悪'}")]
            if h:
                p = h[-1]
                dd = R["dist"] - p["dist"]
                if abs(dd) >= 200:
                    conds.append(("⑦距離変更", f"{su}・{'延長' if dd > 0 else '短縮'}"))
                if p["su"] != su:
                    conds.append(("⑧芝ダ替わり", f"{p['su']}→{su}"))
                days = (dt.date.fromisoformat(R["date"]) - dt.date.fromisoformat(p["date"])).days
                if days >= 70:
                    conds.append(("⑩間隔", f"{su}・休み明け(10週+)"))
                elif len(h) >= 2 and (dt.date.fromisoformat(p["date"]) - dt.date.fromisoformat(h[-2]["date"])).days >= 70:
                    conds.append(("⑩間隔", f"{su}・叩き2戦目"))
            if x["age"]:
                conds.append(("⑨年齢", f"{su}・{x['age']}歳" if x["age"] <= 5 else f"{su}・6歳以上"))
            if handi:
                conds.append(("⑪ハンデ", f"{su}・斤量差4kg以上"))
            if x["sex"]:
                conds.append(("⑫性別", f"{su}・{'牝' if x['sex'].startswith('牝') else '牡セ'}"))
            lines = []
            for who, v in (("父", x["sl"]), ("母父", x["dsl"])):
                if v in BOOK:
                    small, big = BOOK[v]
                    lines += [(who, "小系統", small), (who, "大系統", big)]
            e = exp[min(x["pop"], 14)]
            for ln in lines:
                for cd in conds:
                    a = agg[(ln, cd)][pr]
                    a[0] += 1; a[1] += x["fin"] <= 3; a[2] += e; a[3] += fk.get(str(x["num"]), 0); a[4] += tk.get(str(x["num"]), 0)
        for x in rs:
            hist[x["hid"]].append(dict(date=R["date"], dist=R["dist"], su=su))
    out = []
    for (ln, cd), A in agg.items():
        if min(a[0] for a in A) < 100:
            continue
        ae = [a[1] / a[2] for a in A]
        if min(ae) >= 1.10 or max(ae) <= 0.90:
            out.append(dict(who=ln[0], level=ln[1], line=ln[2], cond=cd[0], value=cd[1], ae=[round(v, 2) for v in ae],
                            fuku=[round(a[3] / a[0]) for a in A], tan=[round(a[4] / a[0]) for a in A], n=[a[0] for a in A]))
    out.sort(key=lambda o: (o["cond"], -min(o["ae"])))
    (ROOT / "data" / "knowledge" / "book_conditions.json").write_text(json.dumps(
        {"_meta": "亀谷『血統の教科書』の切り口（小系統・大系統×レース条件）で3期間とも A/E 1.10以上(◎)/0.90以下(×)。tools/book_conditions.py",
         "book_map": BOOK, "long_straight": sorted(LONG_STRAIGHT), "slope": sorted(SLOPE), "rows": out},
        ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# 系統 × レース条件（亀谷『勝ち馬がわかる 血統の教科書』の切り口, 自動生成 tools/book_conditions.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各100走以上）。◎＝3期間とも1.10以上、×＝0.90以下。",
         "- ハンデ戦は同レースの斤量差4kg以上で代用。新馬戦（⑬）は DB 対象外。データは各日7R以降（未勝利除く）。", "",
         "| 条件 | 値 | | 父/母父 | 系統 | A/E | 複勝回収 | 単勝回収 | 走数 |", "|---|---|---|---|---|---|---|---|---|"]
    for o in out:
        m = "◎" if min(o["ae"]) >= 1.1 else "×"
        L.append(f"| {o['cond']} | {o['value']} | {m} | {o['who']} | {o['line']}（{o['level']}） | " + "/".join(f"{v:.2f}" for v in o["ae"])
                 + " | " + "/".join(map(str, o["fuku"])) + "% | " + "/".join(map(str, o["tan"])) + "% | " + "/".join(map(str, o["n"])) + " |")
    L.append(""); L.append(f"- ◎ {sum(1 for o in out if min(o['ae']) >= 1.1)} 件 / × {sum(1 for o in out if max(o['ae']) <= 0.9)} 件")
    (ROOT / "docs" / "analysis" / "book_conditions.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
