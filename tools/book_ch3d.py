"""亀谷『血統の教科書』p98-105 の検証（2026-10-12）.
1) 早熟/晩成: 3歳限定(〜6月) vs 古馬混合 × 父米国型・ダンチヒ系・ストームバード系・ミスプロ系 / 父欧州型・5代にノーザンテースト・リボー / 父ディープ系（芝2000以上）・ディープ×母父米国型
2) 鉄砲（中9週以上）/ 叩き2戦目（前走が中9週以上の休み明け）× 父タイプ・5代にノーザンテースト・父キンカメ系・ディープ×母父欧州型
3) ハンデ戦（同レースの斤量差4kg以上の OP・重賞で代用）: トップハンデ〜1kg差 / 4kg以上軽い・内枠(1-6番)×父米国型/ミスプロ系/ディープ×母父ミスプロ・ナスルーラ系
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch3d.py <ped5_full.json> → docs/analysis/book_ch3d.md
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

MISPRO = {"キングカメハメハ系", "キングマンボ系", "フォーティナイナー系", "ファピアノ系", "シーキングザゴールド系", "ゴーンウエスト系", "マキャヴェリアン系",
          "スマートストライク系", "ミスタープロスペクター系"}
DANZIG = {"デインヒル系", "ウォーフロント系", "グリーンデザート系", "ダンチヒ系"}
STORM = {"ヘネシー系", "テイルオブザキャット系", "ジャイアンツコーズウェイ系", "フォレストリー系", "ハーランズホリデー系", "スキャットダディ系", "ストームキャット系"}
NASRULLAH = {"プリンスリーギフト系", "エーピーインディ系", "ナスルーラ系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pedpath):
    H = json.loads(Path(pedpath).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    rows = []; base = defaultdict(lambda: [0, 0]); wc_by = defaultdict(list)
    for date, rid, su, dist, grade, hid, fin, pop, num, age, wc, sl, dsl, pay in c.execute(
            """select ra.date, ra.race_id, ra.surface, ra.distance, ra.grade, r.horse_id, r.finish, r.popularity, r.number, r.age, r.weight_carried,
                      h.sire_line, h.damsire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, rid, su, dist or 1600, grade, hid, fin, p, num, age, wc, sl, dsl, pay))
        if wc:
            wc_by[rid].append(wc)
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}; last = {}
    for date, rid, su, dist, grade, hid, fin, p, num, age, wc, sl, dsl, pay in rows:
        if rid not in pc:
            pc[rid] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[rid].get(str(num), 0); pr = per(date)
        st = country_type(sl) if sl else None; dt_ = country_type(dsl) if dsl else None
        names = set(H.get(hid) or [])
        nt = bool(names & {"Northern Taste", "ノーザンテースト"}); rb = bool(names & {"Ribot", "リボー"})
        keys = []
        # 1) 早熟/晩成: 3歳のみのレース(前半) vs 古馬混合
        ages = None
        stage = "3歳(1-6月)" if age == 3 and date[5:7] <= "06" else "4歳以上(古馬混合)" if (age or 0) >= 4 else None
        if stage:
            g = []
            if st:
                g.append(f"父{st}")
            if sl in DANZIG:
                g.append("父ダンチヒ系")
            if sl in STORM:
                g.append("父ストームバード系")
            if sl in MISPRO:
                g.append("父ミスプロ系")
            if nt:
                g.append("5代にノーザンテースト")
            if rb:
                g.append("5代にリボー")
            if sl == "ディープインパクト系" and su == "芝" and dist >= 2000:
                g.append("父ディープ系×芝2000以上")
                if dt_ == "米国型":
                    g.append("父ディープ系×母父米国型×芝2000以上")
            for x in g:
                keys.append(("①早熟/晩成", f"{su}・{stage}", x))
        # 2) 鉄砲/叩き2戦目
        L = last.get(hid)
        rot = None
        if L:
            gap = (dt.date.fromisoformat(date) - dt.date.fromisoformat(L["date"])).days
            if gap >= 63:
                rot = "休み明け(中9週以上)"
            elif L.get("rest") and gap <= 42:
                rot = "叩き2戦目"
            else:
                rot = "使い詰め"
            g = [f"父{st}"] if st else []
            if nt:
                g.append("5代にノーザンテースト")
            if sl in ("キングカメハメハ系", "キングマンボ系"):
                g.append("父キンカメ系")
            if sl == "ディープインパクト系":
                g.append("父ディープ×母父欧州型" if dt_ == "欧州型" else "父ディープ×母父欧州型以外")
            for x in g:
                keys.append(("②鉄砲/叩き", f"{su}・{rot}", x))
        # 3) ハンデ戦代用
        w = wc_by.get(rid) or []
        if grade in ("OP", "L", "G3", "G2", "G1") and w and max(w) - min(w) >= 4 and wc:
            top = max(w)
            cls = "トップハンデ〜1kg差" if wc >= top - 1 else "4kg以上軽い" if wc <= top - 4 else "中間"
            keys.append(("③ハンデ戦(斤量差4kg以上のOP・重賞)", su, cls))
            if num <= 6:
                g = []
                if st == "米国型":
                    g.append("内枠(1-6番)×父米国型")
                if sl in MISPRO:
                    g.append("内枠(1-6番)×父ミスプロ系")
                if sl == "ディープインパクト系" and (dsl in MISPRO or dsl in NASRULLAH):
                    g.append("内枠(1-6番)×父ディープ×母父ミスプロ/ナスルーラ系")
                for x in g:
                    keys.append(("③ハンデ戦(斤量差4kg以上のOP・重賞)", su, x))
        for k in keys:
            x = agg[k][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
        last[hid] = {"date": date, "rest": rot == "休み明け(中9週以上)"}
    L = ["# 亀谷『血統の教科書』p98-105 の検証（自動生成 tools/book_ch3d.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。",
         "- 間隔・前走は DB 内（各日7R以降）の前走で判定。ハンデ戦は名称で判別できないため、斤量差4kg以上の OP・重賞で代用。", "",
         "| 主張 | 条件 | 区分 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|---|"]
    keep = []
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 60:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {k[1]} | {m}{k[2]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
        if m:
            keep.append({"claim": k[0], "cond": k[1], "group": k[2], "mark": m, "ae": [round(v, 2) for v in ae]})
    (ROOT / "docs" / "analysis" / "book_ch3d.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "book_ch3d.json").write_text(json.dumps({"_meta": "tools/book_ch3d.py", "rows": keep}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
