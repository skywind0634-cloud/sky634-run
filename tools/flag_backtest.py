"""予想ページの注目馬フラグ（○◎の数 − ×▽▼の数）が当たるかの総合バックテスト（2026-10-15）.
DB の過去レースから出馬表（近走つき）を作り直し、keiba/digest.py の book_condition_horses / pace_l3_horses / course_check_horses を当てて
フラグ点（プラス−マイナス）ごとに 3着内率・A/E・複勝/単勝回収率を集計する。人気は確定時の単勝人気。
注意: フラグの多くは2021-26年の全期間で「3期間とも一貫」を条件に選んだので、ここでの成績は選んだ期間の中での確認になる（真の未来の検証は今後の週）。
使い方: python3 tools/flag_backtest.py <開始日> <終了日> [並列数] → docs/analysis/flag_backtest.md
"""
import json, os, re, sqlite3, sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PLUS, MINUS = re.compile(r"[◎○]（"), re.compile(r"[×▽▼]（")
ITEM = re.compile(r"(?:^|、|\s)([^、]+?) ([◎○×▽▼])（")


def flag_items(t):
    """材料の文 → [(材料名, 印)]。材料名は前置きの展開予想を除いた短い名前（2026-11-07 材料ごとの検証用）."""
    out = []
    for name, mark in ITEM.findall(t):
        name = re.sub(r"^.*?予想（[^）]*）: ", "", name.strip())
        out.append((name[:80], mark))
    return out


def cards(conn, start, end):
    conn.row_factory = sqlite3.Row
    ids = [r[0] for r in conn.execute("select race_id from races where date between ? and ? and surface in ('芝','ダ') order by date", (start, end))]
    for rid in ids:
        R = dict(conn.execute("select * from races where race_id=?", (rid,)).fetchone())
        rows = conn.execute("select r.*, h.sire, h.damsire, h.sire_line, h.damsire_line, h.pedigree from results r left join horses h using(horse_id) "
                            "where r.race_id=? and r.finish is not null and r.popularity is not null", (rid,)).fetchall()
        if len(rows) < 5:
            continue
        ents = []
        for r in rows:
            rec = []
            for p in conn.execute("select ra.race_id, ra.date, ra.course, ra.surface, ra.distance, ra.n_runners, ra.grade, ra.going, "
                                  "x.finish, x.popularity, x.passing, x.last3f, x.body_weight, x.number, x.weight_carried, x.jockey, "
                                  "x.time_sec - (select min(y.time_sec) from results y where y.race_id=x.race_id and y.finish=1) behind "
                                  "from results x join races ra using(race_id) where x.horse_id=? and ra.date<? order by ra.date desc limit 5",
                                  (r["horse_id"], R["date"])):
                rec.append(dict(p))
            ents.append(dict(horse_id=r["horse_id"], number=r["number"], gate=r["gate"], age=r["age"], sex=r["sex"], weight=r["weight_carried"],
                             body_weight=r["body_weight"], body_weight_diff=r["body_weight_diff"], jockey=r["jockey"], trainer=r["trainer"], popularity=r["popularity"], odds=r["odds"], sire=r["sire"], damsire=r["damsire"],
                             pedigree=json.loads(r["pedigree"]) if r["pedigree"] else {}, recent=rec,
                             _fin=r["finish"], _sl=r["sire_line"], _dsl=r["damsire_line"]))
        yield R, ents


ERRS = {}


def run(args):
    start, end = args
    from keiba import digest as D
    conn = sqlite3.connect(ROOT / "data" / "keiba.db")
    out = []
    for R, ents in cards(conn, start, end):
        card = dict(R)
        # BLIND=1: 人気・オッズを見ない（前日のオッズ前と同じ条件の「適性だけ」のフラグ点。2026-11-07 ユーザー指示の検証）
        blind = os.environ.get("BLIND") == "1"
        card["entries"] = [dict(e, popularity=None, odds=None) for e in ents] if blind else ents
        evals = [SimpleNamespace(number=e["number"], name=str(e["number"]), sire=e["sire"], damsire=e["damsire"], sire_line=e["_sl"] or "",
                                 damsire_line=e["_dsl"] or "", pop_rank=None if blind else e["popularity"], odds=None if blind else e["odds"]) for e in ents]
        txt = defaultdict(str)
        for f in (D.book_condition_horses, D.pace_l3_horses, D.course_check_horses):
            try:
                for num, t in f(card, evals):
                    txt[num] += " " + t
            except Exception as ex:  # noqa: BLE001
                txt["_err"] += f"{f.__name__}:{ex};"
        if txt.get("_err"):
            ERRS[txt["_err"][:120]] = ERRS.get(txt["_err"][:120], 0) + 1
        pay = json.loads(R["payouts"]) if R["payouts"] else {}
        fk = {a: y for a, y in pay.get("複勝", [])}; tk = {a: y for a, y in pay.get("単勝", [])}
        for e in ents:
            t = txt.get(e["number"], "")
            out.append(dict(date=R["date"], rid=R["race_id"], pop=e["popularity"], fin=e["_fin"], plus=len(PLUS.findall(t)), minus=len(MINUS.findall(t)),
                            flags=flag_items(t),
                            fuku=fk.get(str(e["number"]), 0), tan=tk.get(str(e["number"]), 0)))
    return out


def main(start, end, workers=6):
    import datetime as dt
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    chunks, d = [], d0
    while d <= d1:
        e = min(d + dt.timedelta(days=30), d1)
        chunks.append((d.isoformat(), e.isoformat())); d = e + dt.timedelta(days=1)
    rows = []
    with ProcessPoolExecutor(workers) as ex:
        for r in ex.map(run, chunks):
            rows += r
    base = defaultdict(lambda: [0, 0])
    conn = sqlite3.connect(ROOT / "data" / "keiba.db")
    for p, f in conn.execute("select popularity, finish from results where finish is not null and popularity is not null"):
        b = base[min(p, 14)]; b[0] += 1; b[1] += f <= 3
    exp = {p: v[1] / v[0] for p, v in base.items()}
    agg = defaultdict(lambda: [0, 0, 0.0, 0, 0])
    for r in rows:
        sc = r["plus"] - r["minus"]
        sb = "+2以上" if sc >= 2 else "+1" if sc == 1 else "0（フラグなし）" if r["plus"] == r["minus"] == 0 else "0（±相殺）" if sc == 0 else "-1" if sc == -1 else "-2以下"
        pb = "1-3番人気" if r["pop"] <= 3 else "4-6番人気" if r["pop"] <= 6 else "7番人気以下"
        for k in ((pb, sb), ("全体", sb)):
            a = agg[k]; a[0] += 1; a[1] += r["fin"] <= 3; a[2] += exp[min(r["pop"], 14)]; a[3] += r["fuku"]; a[4] += r["tan"]
    order = ["+2以上", "+1", "0（フラグなし）", "0（±相殺）", "-1", "-2以下"]
    L = [f"# 注目馬フラグの総合バックテスト {start}〜{end}（自動生成 tools/flag_backtest.py）", "",
         "- フラグ点＝○◎の数 − ×▽▼の数（book_condition_horses・pace_l3_horses・course_check_horses）。A/E＝3着内の実数÷人気から見込む数。",
         "- フラグは2021-26年の全期間で一貫したものを選んでいるので、これは選んだ期間の中での確認（未来の検証は今後の週で行う）。", "",
         "| 人気 | フラグ点 | 頭数 | 3着内率 | A/E | 複勝回収 | 単勝回収 |", "|---|---|---|---|---|---|---|"]
    for pb in ("1-3番人気", "4-6番人気", "7番人気以下", "全体"):
        for sb in order:
            a = agg.get((pb, sb))
            if a and a[0] >= 30:
                L.append(f"| {pb} | {sb} | {a[0]} | {a[1]/a[0]*100:.1f}% | {a[1]/a[2]:.2f} | {a[3]/a[0]:.0f}% | {a[4]/a[0]:.0f}% |")
    sfx = ("_blind" if os.environ.get("BLIND") == "1" else "") + os.environ.get("SFX", "")
    (ROOT / "docs" / "analysis" / f"flag_backtest{sfx}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    json.dump(rows, open(ROOT / "data" / "cache" / f"flag_backtest_rows{sfx}.json", "w"))
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6)
