"""亀谷『血統の教科書』p81-90 の検証（2026-10-12）.
1) ダートの道悪（重・不良）: 父サンデー系/日本型、近走に芝出走のある馬、父米国型の前走先行馬
2) ダート中距離(1600-2000): 5代にヌレイエフ、父欧州型
3) 芝2500m以上: 父ハーツ/ステゴ系、母父欧州型、母父ダンスインザダーク / ダート1900m以上: 父ロベルト系、5代にリボー
4) 非根幹距離（芝1800・2200・2500等）vs 根幹（1600・2000・2400）: 父サンデー系/欧州型、自身が非根幹で3着内の実績
5) 直線の長短（本 p88 の表: 外回り/内回りを距離で判定）: 父サンデー系、父キンカメ系×母父サンデー系、父米国型、父ミスプロ系、父欧州型、父ステゴ系×母父欧州型
A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。
使い方: python3 tools/book_ch3b.py <ped5_full.json> → docs/analysis/book_ch3b.md
"""
from __future__ import annotations

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
MISPRO = {"キングカメハメハ系", "キングマンボ系", "フォーティナイナー系", "ファピアノ系", "シーキングザゴールド系", "ゴーンウエスト系", "マキャヴェリアン系",
          "スマートストライク系", "ミスタープロスペクター系"}
ROBERTO = {"スクリーンヒーロー系", "シンボリクリスエス系", "ブライアンズタイム系", "クリスエス系", "グラスワンダー系"}
ROOT_DIST = {1600, 2000, 2400}
# 本 p88: 芝の外回り（直線400m以上）を距離で判定
OUTER = {"新潟": {1600, 1800, 2000, 3000}, "阪神": {1600, 1800, 2400, 2600}, "京都": {1600, 1800, 2200, 2400, 3000, 3200}}


def straight(co, su, d):
    if su == "ダ":
        return "長" if co in ("東京", "中京") else "短"
    if co in ("東京", "中京"):
        return "長"
    if co in OUTER:
        return "長" if d in OUTER[co] else "短"
    return "短"


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(pedpath):
    H = json.loads(Path(pedpath).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    rows = []; base = defaultdict(lambda: [0, 0])
    for date, rid, co, su, dist, going, n, hid, fin, pop, num, pas, sire, sl, dsl, ds, pay in c.execute(
            """select ra.date, ra.race_id, ra.course, ra.surface, ra.distance, ra.going, ra.n_runners, r.horse_id, r.finish, r.popularity, r.number, r.passing,
                      h.sire, h.sire_line, h.damsire_line, h.damsire, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, rid, co, su, dist or 1600, going or "良", n or 16, hid, fin, p, num, pas, sire, sl, dsl, ds, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}; hist = defaultdict(list)
    for date, rid, co, su, dist, going, n, hid, fin, p, num, pas, sire, sl, dsl, ds, pay in rows:
        if rid not in pc:
            pc[rid] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[rid].get(str(num), 0); pr = per(date)
        st = country_type(sl) if sl else None; dt_ = country_type(dsl) if dsl else None
        names = set(H.get(hid) or [])
        h = hist[hid]
        keys = []
        heavy = going[:1] in ("重", "不")
        if su == "ダ":
            gl = "ダ・重/不良" if heavy else "ダ・良/稍重"
            if sl in SS:
                keys.append(("①ダートの道悪", gl, "父サンデー系"))
            if st:
                keys.append(("①ダートの道悪", gl, f"父{st}"))
            if any(x["su"] == "芝" for x in h[-3:]):
                keys.append(("①ダートの道悪", gl, "近3走に芝出走あり"))
            if st == "米国型" and h and h[-1]["pos"] is not None and h[-1]["pos"] <= 0.25:
                keys.append(("①ダートの道悪", gl, "父米国型で前走先行（前25%）"))
            if 1600 <= dist <= 2000:
                if names & {"Nureyev", "ヌレイエフ"}:
                    keys.append(("②ダート中距離", "ダ1600-2000", "5代にヌレイエフ"))
                if st == "欧州型":
                    keys.append(("②ダート中距離", "ダ1600-2000", "父欧州型"))
            if dist >= 1900:
                if sl in ROBERTO:
                    keys.append(("③長距離", "ダ1900以上", "父ロベルト系"))
                if names & {"Ribot", "リボー"}:
                    keys.append(("③長距離", "ダ1900以上", "5代にリボー"))
        if su == "芝":
            if dist >= 2500:
                if sl in ("ハーツクライ系", "ステイゴールド系"):
                    keys.append(("③長距離", "芝2500以上", "父ハーツ/ステゴ系"))
                if dt_ == "欧州型":
                    keys.append(("③長距離", "芝2500以上", "母父欧州型"))
                if ds == "ダンスインザダーク":
                    keys.append(("③長距離", "芝2500以上", "母父ダンスインザダーク"))
            if 1600 <= dist <= 2500:
                rd = "根幹(1600/2000/2400)" if dist in ROOT_DIST else "非根幹(1800/2200/2500)"
                if sl in SS:
                    keys.append(("④根幹/非根幹", rd, "父サンデー系"))
                if st == "欧州型":
                    keys.append(("④根幹/非根幹", rd, "父欧州型"))
                if dist not in ROOT_DIST:
                    nr = [x for x in h if x["su"] == "芝" and 1600 <= x["dist"] <= 2500 and x["dist"] not in ROOT_DIST]
                    rr = [x for x in h if x["su"] == "芝" and x["dist"] in ROOT_DIST]
                    if nr and any(x["fin"] <= 3 for x in nr) and rr and not any(x["fin"] <= 3 for x in rr):
                        keys.append(("④根幹/非根幹", rd, "非根幹で3着内あり・根幹では3着内なし"))
        sg = straight(co, su, dist)
        g5 = []
        if sl in SS:
            g5.append("父サンデー系")
        if sl in ("キングカメハメハ系", "キングマンボ系") and dsl in SS:
            g5.append("父キンカメ系×母父サンデー系")
        if st == "米国型":
            g5.append("父米国型")
        if sl in MISPRO:
            g5.append("父ミスプロ系")
        if st == "欧州型":
            g5.append("父欧州型")
        if sl == "ステイゴールド系" and dt_ == "欧州型":
            g5.append("父ステゴ系×母父欧州型")
        for g in g5:
            keys.append(("⑤直線", f"{su}・直線{sg}", g))
        for k in keys:
            x = agg[k][pr]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
        try:
            pos = int(str(pas).split("-")[0]) / n
        except (ValueError, TypeError):
            pos = None
        h.append({"su": su, "dist": dist, "fin": fin, "pos": pos})
    L = ["# 亀谷『血統の教科書』p81-90 の検証（自動生成 tools/book_ch3b.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
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
    (ROOT / "docs" / "analysis" / "book_ch3b.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (ROOT / "data" / "knowledge" / "book_ch3b.json").write_text(json.dumps({"_meta": "tools/book_ch3b.py", "rows": keep}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
