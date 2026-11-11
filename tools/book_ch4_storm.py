"""第4章 ストームバード系・サドラーズウェルズ系（p256-269）の検証（2026-10-15）.
- 父ストームバード系: 2-3歳/4歳以上、ダ1400以下/芝1400以下/芝1800以上(古馬)、ヘニーヒューズ(芝/ダ・2-3歳)、ドレフォン
- 母父ストームキャット系(5代にStorm Cat): 父ディープ系の芝
- 父サドラーズウェルズ系(ガリレオ・モンジュー等): 芝の良/道悪、芝2000以上
- 5代にサドラーズウェルズ(母系): 父サンデー系の芝・道悪/良
- 父ローエングリン/ロゴタイプ: 芝・先行（前走前25%）
使い方: python3 tools/book_ch4_storm.py <ped5_full.json> → docs/analysis/book_ch4_storm.md
"""
import json, sqlite3, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SS = {"ディープインパクト系", "ハーツクライ系", "ステイゴールド系", "フジキセキ系", "ゴールドアリュール系", "ネオユニヴァース系", "アグネスタキオン系",
      "ダイワメジャー系", "ブラックタイド系", "マンハッタンカフェ系", "スペシャルウィーク系", "サンデーサイレンス系"}
STORM = {"ヘネシー系", "テイルオブザキャット系", "ジャイアンツコーズウェイ系", "フォレストリー系", "ハーランズホリデー系", "スキャットダディ系", "ストームキャット系"}
SAD = {"サドラーズウェルズ系", "ガリレオ系"}


def per(d):
    return 0 if d < "2024-01-01" else 1 if d < "2025-01-01" else 2


def main(path):
    H = json.loads(Path(path).read_text(encoding="utf-8"))["horses"]
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    base = defaultdict(lambda: [0, 0]); rows = []
    for date, su, dist, going, n, hid, fin, pop, num, age, pas, sire, sl, pay in c.execute(
            """select ra.date, ra.surface, ra.distance, ra.going, ra.n_runners, r.horse_id, r.finish, r.popularity, r.number, r.age, r.passing,
                      h.sire, h.sire_line, ra.payouts
               from results r join races ra using(race_id) join horses h using(horse_id)
               where ra.surface in ('芝','ダ') and r.finish is not null and r.popularity is not null order by ra.date, ra.race_id"""):
        p = min(pop, 14); b = base[p]; b[0] += 1; b[1] += fin <= 3
        rows.append((date, su, dist or 1600, going or "良", n or 16, hid, fin, p, num, age, pas, sire, sl, pay))
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [[0, 0, 0.0, 0] for _ in range(3)]); pc = {}; last = {}
    for date, su, dist, going, n, hid, fin, p, num, age, pas, sire, sl, pay in rows:
        prev = last.get(hid)
        try:
            last[hid] = int(str(pas).split("-")[0]) / n
        except (ValueError, TypeError):
            last[hid] = None
        if pay not in pc:
            pc[pay] = {cc: y for cc, y in (json.loads(pay).get("複勝", []) if pay else [])}
        fk = pc[pay].get(str(num), 0)
        names = set(nm for nm in (H.get(hid) or []) if nm)
        ag = "2-3歳" if (age or 9) <= 3 else "4歳以上"
        good = "良" if going.startswith("良") else "道悪"
        K = []
        if sl in STORM:
            K.append(("父ストームバード系", f"{su}・{ag}"))
            if dist <= 1400:
                K.append(("父ストームバード系", f"{su}1400以下"))
            if su == "芝" and dist >= 1800 and ag == "4歳以上":
                K.append(("父ストームバード系", "芝1800以上×4歳以上（古馬の芝中距離）"))
        if sire in ("ヘニーヒューズ", "ドレフォン", "ディスクリートキャット", "ブリックスアンドモルタル"):
            K.append((sire, f"{su}・{ag}"))
        if sl == "ディープインパクト系" and su == "芝" and names & {"Storm Cat", "ストームキャット"}:
            K.append(("父ディープ系×5代にストームキャット", f"芝・{good}"))
        if sl in SAD:
            K.append(("父サドラーズウェルズ系", f"{su}・{good}"))
        if sl in SS and su == "芝" and names & {"Sadler's Wells", "サドラーズウェルズ"}:
            K.append(("父サンデー系×5代にサドラーズウェルズ", f"芝・{good}"))
        if sire in ("ローエングリン", "ロゴタイプ") and su == "芝":
            K.append((sire, "芝・前走先行" if prev is not None and prev <= 0.25 else "芝・その他"))
        for k in K:
            x = agg[k][per(date)]; x[0] += 1; x[1] += fin <= 3; x[2] += exp[p]; x[3] += fk
    L = ["# 第4章 ストームバード系・サドラーズウェルズ系（p256-269）の検証（自動生成 tools/book_ch4_storm.py）", "",
         "- A/E＝3着内の実数÷人気から見込む数。発見2021-23 / 確認2024 / テスト2025-26。◎＝3期間とも1.10以上、○＝1.05以上、×＝0.90以下、▽＝0.95以下。", "",
         "| 血統 | 条件 | 走数 | A/E | 複勝回収 |", "|---|---|---|---|---|"]
    for k in sorted(agg):
        A = agg[k]
        if min(x[0] for x in A) < 30:
            continue
        ae = [x[1] / x[2] for x in A]
        m = "◎" if min(ae) >= 1.1 else "○" if min(ae) >= 1.05 else "×" if max(ae) <= 0.9 else "▽" if max(ae) <= 0.95 else ""
        L.append(f"| {k[0]} | {m}{k[1]} | " + "/".join(str(x[0]) for x in A) + " | " + "/".join(f"{v:.2f}" for v in ae) + " | " + "/".join(f"{x[3]/x[0]:.0f}" for x in A) + "% |")
    (ROOT / "docs" / "analysis" / "book_ch4_storm.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
