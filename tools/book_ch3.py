"""亀谷『血統の教科書』p63-80 の主張の検証（2026-10-12）. 本は2018年頃なので、最新の種牡馬は産駒実績（ダートシェア・リーディング順位）で当てはめる.
1) 芝の道悪 × 父のダートシェア（勝利数のダート比率）×リーディング（前年の勝利数順位）
2) 早熟/晩成: 父ダンチヒ系・米国型 / 5代にミルリーフ・リボー・ファイントップ・ノーザンテースト / 父欧州型ロベルト系 / 父ディープ系 × 年齢
3) 洋芝（札幌・函館）: キンカメ系・ハービンジャー・ダイワメジャー・ステゴ/ハーツ/マンカフェ系・欧州型 / ディープ系の札幌と函館
4) 芝1200以下: 父ミスプロ系(大系統)・米国型・プリンスリーギフト系・ダンチヒ系・Pサンデー
5) 初ダート（前走まで芝のみ）: 母父タイプ別、初ダート凡走（6着以下）後のダート2戦目
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch3.py <ped5_full.json> → docs/analysis/book_ch3.md, data/knowledge/book_ch3.json
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.knowledge import country_type  # noqa: E402

MISPRO = {"キングカメハメハ系", "キングマンボ系", "フォーティナイナー系", "ファピアノ系", "シーキングザゴールド系", "ゴーンウエスト系", "マキャヴェリアン系",
          "スマートストライク系", "ミスタープロスペクター系"}
DANZIG = {"デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系"}
ROBERTO = {"スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系"}
P_SUN = {"ダイワメジャー系", "アグネスタキオン系", "フジキセキ系"}
T_SUN_YOU = {"ステイゴールド系", "ハーツクライ系", "マンハッタンカフェ系"}
LATE = {"Mill Reef", "ミルリーフ", "Ribot", "リボー", "Fine Top", "ファイントップ", "Northern Taste", "ノーザンテースト"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pedpath):
    P = json.loads(Path(pedpath).read_text(encoding="utf-8")); H = P["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    rows = []
    base = defaultdict(lambda: [0, 0])
    for date, rid, co, su, dist, going, hid, fin, pop, num, age, sire, sl, dsl, pay in c.execute(
            """select ra.date, ra.race_id, ra.course, ra.surface, ra.distance, ra.going, r.horse_id, r.finish, r.popularity, r.number, r.age,
                      h.sire, h.sire_line, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, rid, co, su, dist or 1600, going or "良", hid, fin, p, num, age, sire, sl, dsl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    # 父のダートシェア（勝利数）と、年ごとの勝利数順位
    wins = defaultdict(Counter); ywins = defaultdict(Counter)
    for date, rid, co, su, dist, going, hid, fin, p, num, age, sire, sl, dsl, pay in rows:
        if fin == 1 and sire:
            wins[sire][su] += 1; ywins[date[:4]][sire] += 1
    dshare = {s: w["ダ"] / (w["ダ"] + w["芝"]) for s, w in wins.items() if sum(w.values()) >= 20}
    rank = {y: {s: i + 1 for i, (s, _) in enumerate(cn.most_common())} for y, cn in ywins.items()}
    pc = {}
    hist = defaultdict(list)
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)])

    def add(k, pr, fin, p, fk):
        x = agg[k][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk

    for date, rid, co, su, dist, going, hid, fin, p, num, age, sire, sl, dsl, pay in rows:
        if rid not in pc:
            pc[rid] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[rid].get(str(num), 0); pr = per(date)
        good = going.startswith("良")
        st = country_type(sl) if sl else None
        h = hist[hid]
        # 1) 芝の道悪 × ダートシェア × リーディング
        if su == "芝" and sire in dshare:
            rk = rank.get(str(int(date[:4]) - 1), {}).get(sire, 999)
            lead = "リーディング上位(前年20位内)" if rk <= 20 else "リーディング下位"
            ds = "ダートシェア45%超" if dshare[sire] > 0.45 else "ダートシェア45%以下"
            add(("①芝・ダートシェア×リーディング", f"{'良' if good else '道悪'}", f"{ds}・{lead}"), pr, fin, p, fk)
        # 2) 早熟/晩成
        ag = "2-3歳" if (age or 9) <= 3 else "4歳" if age == 4 else "5歳以上"
        names = set(H.get(hid) or [])
        grp = []
        if sl in DANZIG:
            grp.append("父ダンチヒ系")
        if st == "米国型":
            grp.append("父米国型")
        if sl in ROBERTO:
            grp.append("父ロベルト系")
        if sl == "ディープインパクト系":
            grp.append("父ディープ系")
        if names & LATE:
            grp.append("5代にミルリーフ・リボー・ファイントップ・ノーザンテースト")
        for g in grp:
            add(("②早熟/晩成", f"{su}・{ag}", g), pr, fin, p, fk)
        # 3) 洋芝
        if su == "芝" and co in ("札幌", "函館"):
            g3 = []
            if sl in ("キングカメハメハ系", "キングマンボ系"):
                g3.append("父キングマンボ系")
            if sire == "ハービンジャー":
                g3.append("父ハービンジャー")
            if sl == "ダイワメジャー系":
                g3.append("父ダイワメジャー系")
            if sl in T_SUN_YOU:
                g3.append("父ステゴ/ハーツ/マンカフェ系")
            if st == "欧州型":
                g3.append("父欧州型")
            if sl == "ディープインパクト系":
                g3.append(f"父ディープ系（{co}）")
            for g in g3:
                add(("③洋芝", "札幌・函館", g), pr, fin, p, fk)
        # 4) 芝1200以下
        if su == "芝" and dist <= 1200:
            g4 = []
            if sl in MISPRO:
                g4.append("父ミスプロ系")
            if st == "米国型":
                g4.append("父米国型")
            if sl == "プリンスリーギフト系":
                g4.append("父プリンスリーギフト系")
            if sl in DANZIG:
                g4.append("父ダンチヒ系")
            if sl in P_SUN:
                g4.append("父Pサンデー")
            if sl == "ディープインパクト系":
                g4.append("父ディープ系")
            for g in g4:
                add(("④芝1200以下", "芝〜1200", g), pr, fin, p, fk)
        # 5) 初ダート / 初ダート凡走後の2戦目
        if su == "ダ" and h:
            dt_ = country_type(dsl) if dsl else "不明"
            if all(x[0] == "芝" for x in h):
                add(("⑤初ダート", "前走まで芝のみ", f"母父{dt_}"), pr, fin, p, fk)
                add(("⑤初ダート", "前走まで芝のみ", f"父{st or '不明'}"), pr, fin, p, fk)
            elif sum(x[0] == "ダ" for x in h) == 1 and h[-1][0] == "ダ" and (h[-1][1] or 99) >= 6:
                add(("⑤初ダート", "初ダート6着以下→ダート2戦目", f"母父{dt_}"), pr, fin, p, fk)
        h.append((su, fin))
    out = []
    L = ["# 亀谷『血統の教科書』p63-80 の検証（自動生成 tools/book_ch3.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。",
         "- ダートシェア＝父の産駒の勝利数に占めるダートの割合（DB全期間）。リーディング＝前年の勝利数順位（第7R以降・未勝利除くデータ内）。", "",
         "| 主張 | 条件 | 区分 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 60:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {k[1]} | {m}{k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
        if m:
            out.append({"claim": k[0], "cond": k[1], "group": k[2], "ae": [round(v, 2) for v in ae], "fuku": [round(x[3] / x[0]) for x in A], "n": [x[0] for x in A], "mark": m})
    (ROOT / "docs" / "analysis" / "book_ch3.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "book_ch3.json").write_text(json.dumps(
        {"_meta": "tools/book_ch3.py", "dirt_share": {s: round(v, 3) for s, v in dshare.items()},
         "rank": {y: {s: r for s, r in d.items() if r <= 30} for y, d in rank.items()}, "rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
