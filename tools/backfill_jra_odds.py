"""JRA の最終オッズ（単勝・複勝・馬連・ワイド・3連複）を過去レースぶん取得し、odds/<YYYYMM>.json.gz に保存する（2026-10-17）.
対象は data/keiba.db にある対象レース（7R以降・未勝利/障害を除く）。結果ページ → 『オッズ』ボタン → 券種タブ と辿る。
新しい月から順に取り、取得済みのレースは飛ばす（途中で止めても再開できる）。残りのレース数を最後に出力する。
使い方: python tools/backfill_jra_odds.py --since 2021-01 --budget-min 300 --out odds
"""
import argparse, datetime as dt, gzip, json, sqlite3, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from keiba.scraper import jra  # noqa: E402


def months(since: str, until: str) -> list[str]:
    y, m = int(since[:4]), int(since[5:7])
    out = []
    while f"{y}{m:02d}" <= until.replace("-", "")[:6]:
        out.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out[::-1]


def load(path: Path) -> dict:
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def fetch_race(cname: str) -> dict | None:
    html = jra.post("/JRADB/accessS.html", cname, use_cache=False)
    link = jra.odds_link(html)
    if not link:
        return None
    first = jra.post(*link, use_cache=False)
    rec = {"tanpuku": jra.parse_odds(first, "tanpuku")}
    for kind, (p, c) in jra.odds_tabs(first, link[1]).items():
        if kind == "tanpuku":
            continue
        rec[kind] = jra.parse_odds(jra.post(p, c, use_cache=False), kind)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2021-01")
    ap.add_argument("--until", default=dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--budget-min", type=float, default=300)
    ap.add_argument("--out", default="odds")
    a = ap.parse_args()
    end = time.time() + a.budget_min * 60
    out = Path(a.out)
    conn = sqlite3.connect(ROOT / "data" / "keiba.db")
    targets = dict(conn.execute("select race_id, date from races where date >= ?", (a.since + "-01",)).fetchall())
    mc = jra.month_cnames()
    done = 0
    for ym in months(a.since, a.until):
        path = out / f"{ym}.json.gz"
        data = load(path)
        if time.time() > end:
            break
        want = {t for t, d in targets.items() if d.replace("-", "")[:6] == ym and t not in data}
        if not want:
            continue
        try:
            days = jra.day_lists_in_month(ym, mc)
        except jra.FetchError as e:
            print(ym, "month failed", e, flush=True)
            continue
        changed = False
        for day in reversed(days):
            try:
                races = jra.races_in_day(day)
            except jra.FetchError as e:
                print(day[1], "day failed", e, flush=True)
                continue
            for _p, rc in races:
                rid = jra.race_id_from_cname(rc)
                if not rid or rid not in targets or rid in data:
                    continue
                if time.time() > end:
                    break
                try:
                    rec = fetch_race(rc)
                except jra.FetchError as e:
                    print(rid, e, flush=True)
                    continue
                if rec:
                    data[rid] = rec
                    done += 1
                    changed = True
        if changed:
            save(path, data)
            print(f"{ym}: {len(data)} races saved (this run {done})", flush=True)
    have = set()
    for f in out.glob("*.json.gz"):
        have |= set(load(f))
    remaining = sum(1 for t in targets if t not in have)
    print(f"done {done} remaining {remaining}")
    Path("/tmp/odds_remaining").write_text(str(remaining if done else 0))  # 1件も取れなかったら続きを起動しない


if __name__ == "__main__":
    main()
