"""コマンドライン.

  python -m keiba.cli update-results --from 2026-09-26 --to 2026-09-28   # 結果+血統を取り込み
  python -m keiba.cli analyze                                           # 集計 → docs/db_summary.md
  python -m keiba.cli build-cards --weekend 2026-10-03                  # 土日の出馬表カード作成
  python -m keiba.cli predict --weekend 2026-10-03                      # 予想 → predictions/2026-10-03/
  python -m keiba.cli weekly                                            # 上記を今週分まとめて実行
  python -m keiba.cli review --weekend 2026-09-26                       # 予想の検証
  python -m keiba.cli backtest --from 2026-07-01 --to 2026-09-28        # バックテスト・温度調整
"""
from __future__ import annotations

import argparse
from pathlib import Path
import datetime as dt
import json
import math
import sys

from . import analysis, db, pipeline, report
from .betting import build_plan
from .config import DATA_DIR, ROOT
from .model import PARAMS, evaluate_race

JST = dt.timezone(dt.timedelta(hours=9))
PARAMS_PATH = DATA_DIR / "model_params.json"


def today_jst() -> dt.date:
    return dt.datetime.now(JST).date()


def next_saturday(d: dt.date) -> dt.date:
    return d + dt.timedelta(days=(5 - d.weekday()) % 7)


def current_weekend(d: dt.date) -> dt.date:
    """カード・予想の対象週末の土曜: 日曜は前日の土曜（当日オッズで作り直すため）、それ以外は次の土曜."""
    return d - dt.timedelta(days=1) if d.weekday() == 6 else next_saturday(d)


def load_params() -> dict:
    if PARAMS_PATH.exists():
        return json.loads(PARAMS_PATH.read_text())
    return {}


def cmd_update_results(a):
    conn = db.connect()
    start = dt.date.fromisoformat(a.date_from)
    end = dt.date.fromisoformat(a.date_to) if a.date_to else today_jst()
    import os
    import time
    deadline = time.time() + a.time_budget_min * 60 if a.time_budget_min else None
    fn = pipeline.update_results_jra if a.source == "jra" else pipeline.update_results
    n, done = fn(conn, start, end, with_pedigree=not a.no_pedigree, max_races=a.max_races,
                 deadline=deadline, newest_first=a.newest_first)
    total = conn.execute("SELECT COUNT(*) FROM races").fetchone()[0]
    print(f"取り込み: {n} レース（DB累計 {total} レース）{'・完了' if done else '・時間切れで中断（再実行で続きから）'}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"pending={'false' if done else 'true'}\nimported={n}\n")


def cmd_deep(a):
    """取り込みデータの徹底分析 → docs/analysis/ と data/knowledge/learned_sires.json、専門家見解の検証."""
    from . import deep, experts
    conn = db.connect()
    print(deep.run(conn))
    from . import value
    value.run(conn)
    print("妙味条件の分析: docs/analysis/value_segments.md")
    print("専門家見解の検証:", sum(1 for v in experts.verify(conn).values() if v["verdict"] == "裏付けあり"), "件が裏付けあり")


def cmd_validate(a):
    """バックテストで検証し、重みを自動調整 → docs/analysis/backtest.md, data/model_params.json."""
    from . import validate
    conn = db.connect()
    end = a.date_to or (today_jst() - dt.timedelta(days=1)).isoformat()
    start = a.date_from or (dt.date.fromisoformat(end) - dt.timedelta(days=a.days)).isoformat()
    print(validate.run(conn, start, end, save=not a.no_save))


def cmd_merge_db(a):
    conn = db.connect()
    for src in a.sources:
        print(src, db.merge_into(conn, src))
    print("累計", {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("races", "results", "horses")})


def cmd_plan_shards(a):
    """期間を月単位で n 分割して JSON で出力（並列取り込みのマトリクス用）."""
    start = a.date_from
    if start == "3y":
        t = today_jst()
        start = f"{t.year - 3}-{t.month:02d}-01"
    elif start == "all":
        from .scraper import jra
        m = sorted(jra.month_cnames())[0]
        start = f"{m[:4]}-{m[4:]}-01"
    end = a.date_to or today_jst().isoformat()
    months = pipeline._months_between(dt.date.fromisoformat(start), dt.date.fromisoformat(end))
    n = max(1, min(a.n, len(months)))
    if a.recent_weighted:
        # 直近ほど短く: 新しい方から 1, 2, 4, 8 … か月、最後の分割が残り全部
        groups, rest = [], list(reversed(months))
        size = 1
        while rest and len(groups) < n - 1:
            groups.append(sorted(rest[:size]))
            rest = rest[size:]
            size *= 2
        if rest:
            groups.append(sorted(rest))
        groups = list(reversed(groups))   # 古い順に並べ直す（id は古い方から）
    else:
        size = -(-len(months) // n)
        groups = [months[i * size:(i + 1) * size] for i in range(n)]
    shards = []
    for i, ms in enumerate(groups):
        if not ms:
            continue
        f = f"{ms[0][:4]}-{ms[0][4:]}-01"
        last = dt.date(int(ms[-1][:4]), int(ms[-1][4:]), 28) + dt.timedelta(days=4)
        t = min(last - dt.timedelta(days=last.day), dt.date.fromisoformat(end))
        shards.append({"id": i, "from": f, "to": t.isoformat()})
    print(json.dumps(shards))


def cmd_tail_female(a):
    from . import tailfemale
    conn = db.connect()
    n, left = tailfemale.run(conn, budget_min=a.time_budget_min, limit=a.limit)
    print(f"tail-female: fetched {n}, remaining {left}")
    if a.remaining_file:
        Path(a.remaining_file).write_text(str(left))


def cmd_learn(a):
    """重みの学習（条件付きロジット）: 直近1年を検証、その前の期間で学習."""
    from . import validate
    conn = db.connect()
    end = (today_jst() - dt.timedelta(days=1))
    test_from = end - dt.timedelta(days=a.test_days)
    train_from = test_from - dt.timedelta(days=a.train_days)
    print(validate.learn(conn, train_from.isoformat(), (test_from - dt.timedelta(days=1)).isoformat(),
                         test_from.isoformat(), end.isoformat(), save=not a.no_save))


def cmd_jra_earliest(a):
    """JRA公式の過去レース結果検索で遡れる最も古い月の1日を表示."""
    from .scraper import jra
    months = sorted(jra.month_cnames())
    print(f"{months[0][:4]}-{months[0][4:]}-01" if months else "")


def cmd_backfill(a):
    conn = db.connect()
    print(f"血統補完: {pipeline.backfill_pedigrees(conn, a.limit)} 頭")


def relines(conn) -> int:
    """血統ナレッジの更新を反映して、全馬の父系・母父系統・牝系を判定し直す."""
    from . import knowledge as K
    n = 0
    for h in conn.execute("SELECT horse_id, sire, damsire, dam, pedigree FROM horses").fetchall():
        ped = json.loads(h["pedigree"]) if h["pedigree"] else {}
        sl = K.resolve_line(h["sire"], ped, "S")
        dsl = K.resolve_line(h["damsire"], ped, "DS")
        fam, _ = K.detect_family(ped, h["dam"])
        conn.execute("UPDATE horses SET sire_line=?, damsire_line=?, family=? WHERE horse_id=?",
                     (sl, dsl, fam, h["horse_id"]))
        n += 1
    conn.commit()
    return n


def cmd_analyze(a):
    conn = db.connect()
    relines(conn)
    st = analysis.build_stats(conn)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "db_summary.md").write_text(analysis.summary_markdown(st), encoding="utf-8")
    analysis.dump_json(st, DATA_DIR / "stats.json")
    print(f"集計完了: {st.n_races} レース → docs/db_summary.md, data/stats.json")


def cmd_build_cards(a):
    conn = db.connect()
    sat = dt.date.fromisoformat(a.weekend) if a.weekend else current_weekend(today_jst())
    days = [sat, sat + dt.timedelta(days=1)]
    if getattr(a, "source", "jra") == "jra":
        ps = pipeline.build_cards_jra(conn, days)
        print(f"{days[0]}〜{days[1]}: {len(ps)} カード（JRA公式）")
    else:
        for d in days:
            ps = pipeline.build_cards(conn, d)
            print(f"{d}: {len(ps)} カード")


def cmd_predict(a):
    conn = db.connect()
    sat = dt.date.fromisoformat(a.weekend) if a.weekend else current_weekend(today_jst())
    st = analysis.build_stats(conn)
    cards = pipeline.load_cards(sat) + pipeline.load_cards(sat + dt.timedelta(days=1))
    if not cards:
        print(f"カードがありません: cards/{sat}/ と cards/{sat + dt.timedelta(days=1)}/ を作成してください", file=sys.stderr)
        sys.exit(1)
    import keiba.model as M
    M.PARAMS.update(load_params())
    analyzed = report.analyze_cards(cards, st, conn)
    chosen = report.select_races(analyzed, a.max_races)
    notes = []
    if st.n_races == 0:
        notes.append("実績DBが未構築のため、今回は血統ナレッジ（事前知識）＋近走情報＋オッズ中心の評価です。")
    graded = [x for x in analyzed if x not in chosen and x["card"].get("grade") in ("G1", "G2", "G3")]
    p = report.write_week_report(chosen, sat, len(analyzed), st, notes=notes, graded=graded)
    print(f"予想レポート: {p.relative_to(ROOT)}")


def cmd_digest(a):
    """その日の対象レースの注目馬一覧を表示（チャットに貼る用）."""
    from . import digest
    from .config import is_target_race
    conn = db.connect()
    st = analysis.build_stats(conn)
    import keiba.model as M
    M.PARAMS.update(load_params())
    day = dt.date.fromisoformat(a.date) if a.date else today_jst()
    for c in sorted(pipeline.load_cards(day), key=lambda c: (c.get("course", ""), c.get("race_no", 0))):
        if not c.get("entries") or not is_target_race(c.get("race_no"), c.get("grade"), c.get("surface"), c.get("name")):
            continue
        if a.race and f"{c.get('course')}{c.get('race_no')}R" not in a.race:
            continue
        from .model import evaluate_race
        print(digest.text(c, evaluate_race(c, st, conn, n_sims=0), report.race_title(c)), "\n")


def cmd_weekly(a):
    """金曜実行想定: 先週末の結果取り込み → 集計 → 今週末のカード → 予想."""
    conn = db.connect()
    today = today_jst()
    sat = next_saturday(today)
    last_sat = sat - dt.timedelta(days=7)
    fn = pipeline.update_results_jra if a.source == "jra" else pipeline.update_results
    # 月曜祝日開催も含めて前週の土〜月を取り込む
    n, _ = fn(conn, last_sat, last_sat + dt.timedelta(days=2))
    print(f"先週分の取り込み: {n} レース")
    report.review_week(conn, last_sat)
    a.weekend = sat.isoformat()
    cmd_analyze(a)
    cmd_deep(a)   # 学習適性を更新してから予想する
    cmd_build_cards(a)
    cmd_predict(a)


def cmd_review(a):
    conn = db.connect()
    p = report.review_week(conn, dt.date.fromisoformat(a.weekend))
    print(p or "picks.json がありません")


def _race_card_from_db(conn, race_id: str) -> tuple[dict, dict]:
    race = dict(conn.execute("SELECT * FROM races WHERE race_id=?", (race_id,)).fetchone())
    rows = conn.execute("SELECT r.*, h.name FROM results r LEFT JOIN horses h ON h.horse_id=r.horse_id "
                        "WHERE r.race_id=?", (race_id,)).fetchall()
    card = {**race, "entries": [{"horse_id": r["horse_id"], "name": r["name"] or r["horse_id"],
                                 "number": r["number"], "gate": r["gate"], "age": r["age"],
                                 "jockey": r["jockey"], "trainer": r["trainer"], "odds": r["odds"],
                                 "weight": r["weight_carried"], "sex": r["sex"],
                                 "body_weight_diff": r["body_weight_diff"]}
                                for r in rows]}
    fin = {r["number"]: r["finish"] for r in rows}
    return card, fin


def cmd_backtest(a):
    conn = db.connect()
    st = analysis.build_stats(conn, before=a.date_from)
    ids = [r["race_id"] for r in conn.execute(
        "SELECT race_id FROM races WHERE date BETWEEN ? AND ? AND surface IN ('芝','ダ') ORDER BY date",
        (a.date_from, a.date_to)).fetchall()]
    if not ids:
        print("対象レースなし")
        return
    grid_T = [0.6, 0.8, 1.0, 1.3, 1.7]
    grid_m = [0.0, 0.3, 0.45, 0.6] if not a.no_market else [0.0]
    best = None
    races = [_race_card_from_db(conn, rid) for rid in ids]
    for T in grid_T:
        for mw in grid_m:
            ll = hit1 = n = 0
            for card, fin in races:
                ev = evaluate_race(card, st, conn, {"T": T, "market_w": mw}, n_sims=200)
                winner = [h for h in ev if fin.get(h.number) == 1]
                if not winner:
                    continue
                ll += -math.log(max(winner[0].p_win, 1e-6))
                hit1 += fin.get(ev[0].number) == 1
                n += 1
            if n and (best is None or ll / n < best[0]):
                best = (ll / n, T, mw, hit1 / n, n)
            print(f"T={T} market_w={mw}: logloss={ll / max(n,1):.4f} ◎勝率={hit1 / max(n,1):.1%} (n={n})")
    if best:
        print(f"最良: T={best[1]} market_w={best[2]} logloss={best[0]:.4f} ◎勝率={best[3]:.1%}")
        if a.save:
            PARAMS_PATH.write_text(json.dumps({"T": best[1], "market_w": best[2]}, indent=1))
            print(f"保存: {PARAMS_PATH.relative_to(ROOT)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="keiba")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("update-results"); p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to"); p.add_argument("--no-pedigree", action="store_true")
    p.add_argument("--max-races", type=int); p.add_argument("--time-budget-min", type=float)
    p.add_argument("--newest-first", action="store_true")
    p.add_argument("--source", choices=["jra", "netkeiba"], default="jra"); p.set_defaults(fn=cmd_update_results)
    p = sub.add_parser("backfill-pedigree"); p.add_argument("--limit", type=int, default=500); p.set_defaults(fn=cmd_backfill)
    p = sub.add_parser("jra-earliest"); p.set_defaults(fn=cmd_jra_earliest)
    p = sub.add_parser("merge-db"); p.add_argument("sources", nargs="+"); p.set_defaults(fn=cmd_merge_db)
    p = sub.add_parser("plan-shards"); p.add_argument("--from", dest="date_from", default="3y")
    p.add_argument("--to", dest="date_to"); p.add_argument("--n", type=int, default=4)
    p.add_argument("--recent-weighted", action="store_true"); p.set_defaults(fn=cmd_plan_shards)
    p = sub.add_parser("deep-analysis"); p.set_defaults(fn=cmd_deep)
    p = sub.add_parser("tail-female"); p.add_argument("--time-budget-min", type=float, default=50)
    p.add_argument("--limit", type=int); p.add_argument("--remaining-file"); p.set_defaults(fn=cmd_tail_female)
    p = sub.add_parser("learn"); p.add_argument("--train-days", type=int, default=1000)
    p.add_argument("--test-days", type=int, default=365); p.add_argument("--no-save", action="store_true")
    p.set_defaults(fn=cmd_learn)
    p = sub.add_parser("validate"); p.add_argument("--from", dest="date_from"); p.add_argument("--to", dest="date_to")
    p.add_argument("--days", type=int, default=180); p.add_argument("--no-save", action="store_true")
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("analyze"); p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("build-cards"); p.add_argument("--weekend")
    p.add_argument("--source", choices=["jra", "netkeiba"], default="jra"); p.set_defaults(fn=cmd_build_cards)
    p = sub.add_parser("predict"); p.add_argument("--weekend"); p.add_argument("--max-races", type=int, default=0)
    p.set_defaults(fn=cmd_predict)
    p = sub.add_parser("digest"); p.add_argument("--date"); p.add_argument("--race", nargs="*", help="例: 京都11R")
    p.set_defaults(fn=cmd_digest)
    p = sub.add_parser("weekly"); p.add_argument("--max-races", type=int, default=0)
    p.add_argument("--source", choices=["jra", "netkeiba"], default="jra"); p.set_defaults(fn=cmd_weekly)
    p = sub.add_parser("review"); p.add_argument("--weekend", required=True); p.set_defaults(fn=cmd_review)
    p = sub.add_parser("backtest"); p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True); p.add_argument("--no-market", action="store_true")
    p.add_argument("--save", action="store_true"); p.set_defaults(fn=cmd_backtest)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
