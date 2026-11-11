"""亀谷『血統の教科書』p91-97 の検証（2026-10-12）.
1) 坂のある芝・良 × リーディング上位（前年20位内）/ ダイワメジャー系の前走先行
2) 平坦な芝（京都・新潟・札幌・函館・小倉）× 父米国型 / 父ボールドルーラー系（エーピーインディ系）
3) 坂のあるダート1800以上（中山・阪神・中京・東京）× 父欧州型・ロベルト系・5代にリボー/プリンスキロ（1-2勝クラス）
4) 距離延長（前走+200m以上）× 父日本型・欧州型・リーディング上位 / 短縮 × 父米国型 / ダート短縮×父米国型×2桁馬番
5) 芝→ダート: 父米国型 / 父サンデー系 / 父米国型×母父サンデー系 / 母父ダートシェア高(>0.5) ・ ダート→芝: 父欧州型、前走5番人気以内
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch3c.py <ped5_full.json> → docs/analysis/book_ch3c.md
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

SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
ROBERTO = {"スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系"}
SLOPE = {"中山", "阪神", "中京", "東京"}
FLAT = {"京都", "新潟", "札幌", "函館", "小倉"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pedpath):
    H = json.loads(Path(pedpath).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    rows = []; base = defaultdict(lambda: [0, 0])
    for date, rid, co, su, dist, going, n, grade, hid, fin, pop, num, pas, sire, sl, dsl, ds, pay in c.execute(
            """select ra.date, ra.race_id, ra.course, ra.surface, ra.distance, ra.going, ra.n_runners, ra.grade, r.horse_id, r.finish, r.popularity, r.number,
                      r.passing, h.sire, h.sire_line, h.damsire_line, h.damsire, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, rid, co, su, dist or 1600, going or "良", n or 16, grade, hid, fin, p, pop, num, pas, sire, sl, dsl, ds, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    wins = defaultdict(Counter); ywins = defaultdict(Counter)
    for r in rows:
        if r[9] == 1 and r[14]:
            wins[r[14]][r[3]] += 1; ywins[r[0][:4]][r[14]] += 1
    dshare = {s: w["ダ"] / sum(w.values()) for s, w in wins.items() if sum(w.values()) >= 20}
    rank = {y: {s: i + 1 for i, (s, _) in enumerate(cn.most_common())} for y, cn in ywins.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}; hist = defaultdict(list)
    for date, rid, co, su, dist, going, n, grade, hid, fin, p, pop, num, pas, sire, sl, dsl, ds, pay in rows:
        if rid not in pc:
            pc[rid] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[rid].get(str(num), 0); pr = per(date)
        st = country_type(sl) if sl else None
        names = set(H.get(hid) or [])
        good = going.startswith("良")
        lead = rank.get(str(int(date[:4]) - 1), {}).get(sire, 999) <= 20
        h = hist[hid]; prev = h[-1] if h else None
        keys = []
        if su == "芝" and good:
            sg = "芝・坂・良" if co in SLOPE else "芝・平坦・良" if co in FLAT else None
            if sg:
                keys.append(("①②坂/平坦", sg, "父リーディング上位(前年20位内)" if lead else "父リーディング下位"))
                if st:
                    keys.append(("①②坂/平坦", sg, f"父{st}"))
                if sl == "エーピーインディ系":
                    keys.append(("①②坂/平坦", sg, "父ボールドルーラー系(エーピーインディ)"))
                if sl == "ダイワメジャー系" and prev and prev["pos"] is not None and prev["pos"] <= 0.3:
                    keys.append(("①②坂/平坦", sg, "父ダイワメジャー系で前走先行"))
        if su == "ダ" and dist >= 1800:
            sg = "ダ1800以上・坂" if co in SLOPE else "ダ1800以上・平坦"
            cls = "1-2勝クラス" if grade in ("1勝", "2勝") else "3勝以上"
            for g in ([f"父{st}"] if st else []) + (["父ロベルト系"] if sl in ROBERTO else []) + \
                    (["5代にリボー/プリンスキロ"] if names & {"Ribot", "リボー", "Prince Chevalier", "Princequillo", "プリンスキロ"} else []):
                keys.append(("③坂のあるダート中距離", f"{sg}・{cls}", g))
        if prev and abs(dist - prev["dist"]) >= 200 and prev["su"] == su:
            ch = "延長" if dist > prev["dist"] else "短縮"
            for g in ([f"父{st}"] if st else []) + (["父リーディング上位"] if lead else []):
                keys.append(("④距離変更", f"{su}・{ch}", g))
            if su == "ダ" and ch == "短縮" and st == "米国型":
                keys.append(("④距離変更", "ダ・短縮", f"父米国型×{'2桁馬番' if num >= 10 else '1桁馬番'}"))
        if prev and prev["su"] != su:
            if su == "ダ":
                gs = []
                if st == "米国型":
                    gs.append("父米国型×母父サンデー系" if dsl in SS else "父米国型（母父サンデー系以外）")
                if sl in SS:
                    gs.append("父サンデー系")
                if ds in dshare:
                    gs.append("母父ダートシェア50%超" if dshare[ds] > 0.5 else "母父ダートシェア50%以下")
                for g in gs:
                    keys.append(("⑤芝ダ替わり", "芝→ダ", g))
            else:
                gs = [f"父{st}"] if st else []
                if st == "欧州型" and prev["pop"] and prev["pop"] <= 5:
                    gs.append("父欧州型×前走5番人気以内")
                for g in gs:
                    keys.append(("⑤芝ダ替わり", "ダ→芝", g))
        for k in keys:
            x = agg[k][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
        try:
            pos = int(str(pas).split("-")[0]) / n
        except (ValueError, TypeError):
            pos = None
        h.append({"su": su, "dist": dist, "pos": pos, "pop": pop})
    L = ["# 亀谷『血統の教科書』p91-97 の検証（自動生成 tools/book_ch3c.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。",
         "- 前走・距離変更・芝ダ替わりは DB 内（各日7R以降）の前走で判定。", "",
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
    (ROOT / "docs" / "analysis" / "book_ch3c.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "book_ch3c.json").write_text(json.dumps({"_meta": "tools/book_ch3c.py", "dirt_share": {s: round(v, 3) for s, v in dshare.items()}, "rows": keep}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
