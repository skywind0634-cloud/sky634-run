"""双馬 第2章 p138-141「高速血統」の検証（2026-10-15）.
芝: 高速馬場をこなすかは母の血統で決まる。母父がボールドルーラー系・ヴァイスリージェント系・ストームキャット系（ジャイアンツコーズウェイ除く）・
  米国型ミスプロ系・キングマンボ系（キングズベスト/ワークフォース/ルーラーシップ除く）、または5代に In Reality
  → 当日・前日の同場の芝の勝ちタイム（コース平均との差）が速い日 / 平均 / 遅い日 × 父サンデー系かどうか × 人気帯
ダート: ①前が止まらない馬場（重・不良）は米国の先行型（父エーピーインディ系・ボールドルーラー系・ヘネシー系・ストームキャット系・ファピアノ系・
  キングカメハメハ系・ゴーンウエスト系）②差しが決まる馬場（稍重＝乾きかけ）は父または母父サンデー系
  ＋ 当日・前日の同場のダートの勝ちタイムが速い日でも同じ比較。前走の位置取り（先行/差し）も掛ける
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各30走以上）。
使い方: python3 tools/speed_blood.py → docs/analysis/speed_blood.md
"""
import datetime as dt
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS = {"ディープインパクト系", "ステイゴールド系", "ハーツクライ系", "ダイワメジャー系", "サンデーサイレンス系", "マンハッタンカフェ系", "スペシャルウィーク系",
      "フジキセキ系", "アグネスタキオン系", "ゴールドアリュール系", "ネオユニヴァース系", "ダンスインザダーク系", "キズナ系", "ブラックタイド系"}
TURF_FAST_DS = {"ボールドルーラー系", "エーピーインディ系", "デピュティミニスター系", "ストームキャット系", "ヘネシー系", "ミスタープロスペクター系",
                "フォーティナイナー系", "ファピアノ系", "ゴーンウエスト系", "シーキングザゴールド系", "スマートストライク系", "キングマンボ系", "キングカメハメハ系"}
EURO_KM = {"キングズベスト", "ワークフォース", "ルーラーシップ"}
DIRT_FRONT_SIRE = {"エーピーインディ系", "ボールドルーラー系", "ヘネシー系", "ストームキャット系", "ファピアノ系", "キングカメハメハ系", "ゴーンウエスト系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def pband(p):
    return "1-3番人気" if p <= 3 else "4-6番人気" if p <= 6 else "7番人気以下"


def main():
    try:
        flags = json.loads((ROOT / "data/knowledge/ped5_flags.json").read_text(encoding="utf-8"))["flags"]
    except (OSError, ValueError, KeyError):
        flags = {}
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    races = {}
    for rid, date, co, no, su, dist, n, going, pay in c.execute(
            "select race_id,date,course,race_no,surface,distance,n_runners,going,payouts from races where surface in ('芝','ダ')"):
        races[rid] = dict(date=date, co=co, no=no or 0, su=su, dist=dist or 1600, n=n or 16, going=going or "良", pay=json.loads(pay) if pay else {})
    rows = defaultdict(list); base = defaultdict(lambda: [0, 0]); wtime = {}
    for rid, hid, fin, pop, num, pas, tsec, sire, ds, sl, dsl in c.execute(
            "select r.race_id,r.horse_id,r.finish,r.popularity,r.number,r.passing,r.time_sec,h.sire,h.damsire,h.sire_line,h.damsire_line "
            "from results r left join horses h using(horse_id) where r.finish is not null and r.popularity is not null"):
        if rid not in races:
            continue
        if fin == 1 and tsec:
            wtime[rid] = tsec
        try:
            p0 = int(str(pas).split("-")[0])
        except ValueError:
            p0 = None
        fast_dam = (dsl in TURF_FAST_DS and ds not in EURO_KM and dsl != "ジャイアンツコーズウェイ系") or "インリアリティ" in flags.get(hid or "", [])
        rows[rid].append(dict(hid=hid, fin=fin, pop=pop, p=min(pop, 14), num=num, p0=p0, fast_dam=fast_dam, sss=sl in SS,
                              ss_any=sl in SS or dsl in SS, front_sire=sl in DIRT_FRONT_SIRE))
        b = base[min(pop, 14)]; b[0] += 1; b[1] += fin <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    cm = defaultdict(list); day = defaultdict(list); last = {}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0, 0] for _ in range(3)])
    for rid in sorted(races, key=lambda r: (races[r]["date"], races[r]["co"], races[r]["no"], r)):
        R = races[rid]; su = R["su"]; pr = per(R["date"]); key = (R["co"], su, R["dist"])
        fk = {a: y for a, y in R["pay"].get("複勝", [])}; tk = {a: y for a, y in R["pay"].get("単勝", [])}
        prev_day = (dt.date.fromisoformat(R["date"]) - dt.timedelta(days=1)).isoformat()
        sp = day[(R["date"], R["co"], su)] + day[(prev_day, R["co"], su)]
        ds_ = None if len(sp) < 2 else "高速日" if sum(sp) / len(sp) <= -0.5 else "時計がかかる日" if sum(sp) / len(sp) >= 0.5 else "平均的な日"
        g = "良" if R["going"].startswith("良") else "稍重" if R["going"].startswith("稍") else "重・不良"
        for x in rows[rid]:
            pb = pband(x["pop"]); K = []
            pz = last.get(x["hid"])
            style = None if pz is None else "前走先行(前15%)" if pz <= 0.15 else "前走差し(後方40%)" if pz > 0.6 else "前走中団"
            if su == "芝" and ds_:
                tag = "母系に高速血統" if x["fast_dam"] else "母系に高速血統なし"
                K.append(("芝×当日の時計", f"{ds_}・{tag}", pb))
                if x["sss"]:
                    K.append(("芝×当日の時計×父サンデー系", f"{ds_}・{tag}", pb))
            if su == "ダ":
                if x["front_sire"]:
                    K.append(("ダ×馬場状態×父が米国の先行型", g, pb))
                    if style:
                        K.append(("ダ×馬場状態×父が米国の先行型×脚質", f"{g}・{style}", "全体"))
                if x["ss_any"]:
                    K.append(("ダ×馬場状態×父か母父サンデー系", g, pb))
                    if style:
                        K.append(("ダ×馬場状態×父か母父サンデー系×脚質", f"{g}・{style}", "全体"))
                if ds_:
                    if x["front_sire"]:
                        K.append(("ダ×当日の時計×父が米国の先行型", ds_, pb))
                    if x["ss_any"]:
                        K.append(("ダ×当日の時計×父か母父サンデー系", ds_, pb))
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
    L = ["# 双馬 p138-141「高速血統」の検証（自動生成 tools/speed_blood.py）", "",
         "- 当日の時計＝当日（先のレース）・前日の同場の勝ちタイムとコース平均との差の平均（±0.5秒）。",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26（各30走以上）。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 見方 | 条件 | 人気 | 走数 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        L.append(f"| {k[0]} | {mark(ae)}{k[1]} | {k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | "
                 + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% | " + "/".join(f"{x[4]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "speed_blood.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
