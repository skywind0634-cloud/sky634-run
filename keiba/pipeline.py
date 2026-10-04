"""データ収集パイプライン: 結果取り込み・血統取り込み・出馬表(カード)作成."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from . import db
from . import knowledge as K
from .config import CARDS_DIR, is_target_race
from .scraper import jra
from .scraper import netkeiba as nk


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def ingest_horse(conn, horse_id: str, name: str | None = None, sex: str | None = None,
                 birth_year: int | None = None) -> dict | None:
    if db.has_horse(conn, horse_id):
        return None
    try:
        ped = nk.fetch_pedigree(horse_id)
    except nk.FetchError as e:
        log("  pedigree fetch failed:", e)
        ped = {}
    sire, dam, damsire = ped.get("S"), ped.get("D"), ped.get("DS")
    fam, _ = K.detect_family(ped, dam)
    row = {
        "horse_id": horse_id, "name": name or horse_id, "sex": sex, "birth_year": birth_year,
        "sire": sire, "dam": dam, "damsire": damsire,
        "sire_line": K.resolve_line(sire, ped, "S"),
        "damsire_line": K.resolve_line(damsire, ped, "DS"),
        "family": fam, "pedigree": ped,
    }
    db.upsert_horse(conn, row)
    return row


def ingest_race(conn, race_id: str, with_pedigree: bool = True) -> bool:
    if db.has_race(conn, race_id):
        return False
    race, results = nk.fetch_result(race_id)
    if not results:
        return False
    db.upsert_race(conn, race)
    year = int(race_id[:4])
    for r in results:
        name = r.pop("_horse_name")
        db.upsert_result(conn, r)
        if with_pedigree:
            ingest_horse(conn, r["horse_id"], name, r["sex"], year - (r["age"] or 0) if r["age"] else None)
        elif not db.has_horse(conn, r["horse_id"]):
            db.upsert_horse(conn, {"horse_id": r["horse_id"], "name": name, "sex": r["sex"]})
    conn.commit()
    return True


def update_results(conn, start: dt.date, end: dt.date, with_pedigree: bool = True,
                   max_races: int | None = None, deadline: float | None = None,
                   newest_first: bool = False) -> tuple[int, bool]:
    """期間内の全レース結果(＋5代血統)を取り込む.

    deadline(UNIX時刻)を過ぎたらそこで中断し (取り込み数, 完了したか) を返す。
    取り込み済みの開催日は fetched_dates に記録し、再実行時はスキップする（途中再開可能）。
    """
    import time
    n = 0
    days = list(daterange(start, end))
    if newest_first:
        days.reverse()
    today = dt.date.today()
    for d in days:
        if not _may_have_races(d):
            continue
        # 2日以上前の開催日で取り込み完了済みならスキップ
        if d < today - dt.timedelta(days=2) and db.date_done(conn, d.isoformat()):
            continue
        if deadline and time.time() > deadline:
            return n, False
        try:
            ids = nk.race_ids_for_date(d.strftime("%Y%m%d"))
        except nk.FetchError as e:
            log(d, "race list failed:", e)
            continue
        if ids:
            log(f"{d}: {len(ids)} races")
        complete = True
        for rid in ids:
            if deadline and time.time() > deadline:
                return n, False
            try:
                if ingest_race(conn, rid, with_pedigree):
                    n += 1
            except nk.FetchError as e:
                log("  ", rid, e)
                complete = False
            if max_races and n >= max_races:
                return n, False
        if complete and d < today - dt.timedelta(days=2):
            db.mark_date_done(conn, d.isoformat(), len(ids))
    return n, True


def _may_have_races(d: dt.date) -> bool:
    # 土日＋祝日の月曜。年末年始(12月・1月)は平日開催もあるので全日確認(空振りは race list が空)
    return d.weekday() in (5, 6, 0) or d.month in (1, 12)


def backfill_pedigrees(conn, limit: int = 500) -> int:
    rows = conn.execute("SELECT horse_id, name, sex FROM horses WHERE pedigree IS NULL LIMIT ?", (limit,)).fetchall()
    n = 0
    for r in rows:
        conn.execute("DELETE FROM horses WHERE horse_id=?", (r["horse_id"],))
        ingest_horse(conn, r["horse_id"], r["name"], r["sex"])
        n += 1
        if n % 50 == 0:
            conn.commit()
    conn.commit()
    return n


def build_cards(conn, date: dt.date, out_dir: Path = CARDS_DIR) -> list[Path]:
    """出馬表を取得し、血統を付与したカード JSON を cards/YYYY-MM-DD/ に保存."""
    out = []
    ids = nk.race_ids_for_date(date.strftime("%Y%m%d"))
    folder = out_dir / date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    for rid in ids:
        try:
            card = nk.fetch_shutuba(rid)
        except nk.FetchError as e:
            log(rid, e)
            continue
        card["date"] = date.isoformat()
        for e in card["entries"]:
            if e.get("horse_id"):
                ingest_horse(conn, e["horse_id"], e["name"], e.get("sex"))
                row = conn.execute("SELECT * FROM horses WHERE horse_id=?", (e["horse_id"],)).fetchone()
                if row:
                    e["sire"], e["dam"], e["damsire"] = row["sire"], row["dam"], row["damsire"]
        conn.commit()
        p = folder / f"{rid}.json"
        p.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
        out.append(p)
    return out


def load_cards(date: dt.date, cards_dir: Path = CARDS_DIR) -> list[dict]:
    folder = cards_dir / date.isoformat()
    if not folder.exists():
        return []
    cards = []
    for p in sorted(folder.glob("*.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        c.setdefault("date", date.isoformat())
        c["_path"] = str(p)
        cards.append(c)
    return cards


# ================================================================ JRA公式サイトから取り込み

def _extend_pedigree(ped: dict) -> dict:
    """JRA は父・母・母の父・母の母まで。父系の祖先はナレッジ(sires.json)の父子関係で補完する."""
    ped = dict(ped)
    for pos in ("S", "DS"):
        cur = ped.get(pos)
        p = pos
        for _ in range(3):
            info = K.sires().get(cur or "")
            if not info or not info.get("sire"):
                break
            p += "S"
            cur = info["sire"]
            ped.setdefault(p, cur)
    return ped


def ingest_horse_jra(conn, horse_id: str, cname: str | None, name: str | None = None,
                     sex: str | None = None) -> None:
    if not horse_id or db.has_horse(conn, horse_id):
        return
    info = {"pedigree": {}}
    if cname:
        try:
            info = jra.parse_horse(jra.post("/JRADB/accessU.html", cname), cname)
        except jra.FetchError as e:
            log("  horse fetch failed:", e)
    ped = _extend_pedigree(info.get("pedigree") or {})
    sire, dam, damsire = ped.get("S"), ped.get("D"), ped.get("DS")
    fam, _ = K.detect_family(ped, dam)
    db.upsert_horse(conn, {
        "horse_id": horse_id, "name": name or info.get("name") or horse_id, "sex": sex or info.get("sex"),
        "birth_year": int(info["birth"][:4]) if info.get("birth") else None,
        "sire": sire, "dam": dam, "damsire": damsire,
        "sire_line": K.resolve_line(sire, ped, "S"), "damsire_line": K.resolve_line(damsire, ped, "DS"),
        "family": fam, "pedigree": ped,
    })


def ingest_race_jra(conn, cname: str, with_pedigree: bool = True) -> bool:
    rid = jra.race_id_from_cname(cname)
    if rid and (db.has_race(conn, rid) or not is_target_race(int(rid[-2:]))):
        return False   # 取り込み済み or 第6レース以前（ページを取りに行かない）
    race, results = jra.parse_result(jra.post("/JRADB/accessS.html", cname), cname)
    if not results or not is_target_race(race["race_no"], race["grade"], race["surface"], race["name"]):
        return False   # 未勝利戦・障害は対象外
    db.upsert_race(conn, race)
    for r in results:
        name, hc = r.pop("_horse_name"), r.pop("_horse_cname")
        if not r["horse_id"]:
            continue
        db.upsert_result(conn, r)
        if with_pedigree:
            ingest_horse_jra(conn, r["horse_id"], hc, name, r["sex"])
        elif not db.has_horse(conn, r["horse_id"]):
            db.upsert_horse(conn, {"horse_id": r["horse_id"], "name": name, "sex": r["sex"]})
    conn.commit()
    return True


def _months_between(start: dt.date, end: dt.date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y}{m:02d}")
        y, m = (y + (m == 12), 1 if m == 12 else m + 1)
    return out


def update_results_jra(conn, start: dt.date, end: dt.date, with_pedigree: bool = True,
                       max_races: int | None = None, deadline: float | None = None,
                       newest_first: bool = False) -> tuple[int, bool]:
    """JRA公式の過去レース結果を 月→開催日→レース と辿って取り込む（途中再開可）."""
    import time
    n = 0
    months = jra.month_cnames()
    order = _months_between(start, end)
    if newest_first:
        order.reverse()
    today = dt.date.today()
    all_ok = True
    for ym in order:
        try:
            days = jra.day_lists_in_month(ym, months)
        except jra.FetchError as e:
            log(ym, "month page failed:", e)
            all_ok = False
            continue
        log(f"{ym}: 開催日ページ {len(days)} 件")
        if newest_first:
            days = list(reversed(days))
        for day in days:
            ds = jra.day_date_from_cname(day[1])
            if not ds or not (start.isoformat() <= ds <= end.isoformat()):
                continue
            key = "jra:" + day[1].split("/")[0]
            if db.date_done(conn, key):
                continue
            if deadline and time.time() > deadline:
                return n, False
            try:
                races = jra.races_in_day(day)
            except jra.FetchError as e:
                log(ds, "day page failed:", e)
                continue
            log(f"{ds} {day[1][9:11]}: {len(races)} races")
            complete = True
            for _p, rc in races:
                if deadline and time.time() > deadline:
                    return n, False
                try:
                    if ingest_race_jra(conn, rc, with_pedigree):
                        n += 1
                except jra.FetchError as e:
                    log("  ", rc, e)
                    complete = False
                if max_races and n >= max_races:
                    return n, False
            if complete and races and dt.date.fromisoformat(ds) < today - dt.timedelta(days=1):
                db.mark_date_done(conn, key, len(races))
    if not all_ok and n == 0:
        raise SystemExit("JRAからの取り込みに失敗しました（上のログを参照）")
    return n, True


def build_cards_jra(conn, dates: list[dt.date], out_dir: Path = CARDS_DIR) -> list[Path]:
    """JRA公式の出馬表から、前4走つきのカード JSON を作る."""
    targets = {d.isoformat() for d in dates}
    out = []
    days = jra.entry_days()
    print(f"出馬表の開催日リンク: {len(days)} 件", [(c, jra.day_date_from_cname(c)) for _p, c in days][:12], flush=True)
    if not days:   # ページ構造が変わった場合の手がかり
        html = jra.post(*jra.ENTRIES_TOP, use_cache=False)
        print("出馬表トップ: 長さ", len(html), "pw01d系リンク:",
              sorted({c[:40] for _p, c in jra.ACTION_RE.findall(html) + jra.HREF_RE.findall(html) if c.startswith("pw01d")})[:20],
              flush=True)
    for day in days:
        ds = jra.day_date_from_cname(day[1])
        if ds not in targets:
            continue
        folder = out_dir / ds
        folder.mkdir(parents=True, exist_ok=True)
        for _p, rc in jra.entry_races(day):
            rid = jra.race_id_from_cname(rc)
            if rid and not is_target_race(int(rid[-2:])):
                continue
            try:
                card = jra.parse_shutuba(jra.post("/JRADB/accessD.html", rc, use_cache=False), rc)
            except Exception as e:   # noqa: BLE001  1レースの不具合で全体を止めない
                log(rc, e)
                continue
            if not is_target_race(card.get("race_no"), card.get("grade"), card.get("surface"), card.get("name")):
                continue   # 未勝利戦・障害は対象外
            for e in card["entries"]:
                ingest_horse_jra(conn, e.get("horse_id"), e.pop("_horse_cname", None), e["name"], e.get("sex"))
                if e.get("horse_id"):
                    row = conn.execute("SELECT pedigree FROM horses WHERE horse_id=?", (e["horse_id"],)).fetchone()
                    if row and row["pedigree"]:
                        e["pedigree"] = json.loads(row["pedigree"])
                for r in e.get("recent", []):
                    r.pop("_race_cname", None)
            conn.commit()
            card.pop("_cname", None)
            p = folder / f"{card['race_id']}.json"
            p.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
            out.append(p)
    return out
