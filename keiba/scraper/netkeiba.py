"""netkeiba からのレース結果・出馬表・5代血統表の取得とパース（予備のデータ源）.

主データ源は JRA 公式サイト（keiba/scraper/jra.py）。こちらは `--source netkeiba` 指定時のみ使う。
アクセスは config.REQUEST_INTERVAL 秒以上の間隔を空け、取得済みページはキャッシュして再取得しない。
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ..config import COURSE_CODES, DATA_DIR, REQUEST_INTERVAL, USER_AGENT

CACHE_DIR = DATA_DIR / "cache"
_last_request = 0.0


class FetchError(RuntimeError):
    pass


def fetch(url: str, use_cache: bool = True, encoding: str = "EUC-JP") -> str:
    global _last_request
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if use_cache and key.exists():
        return key.read_text(encoding="utf-8")
    wait = REQUEST_INTERVAL - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    except requests.RequestException as e:
        raise FetchError(f"{url}: {e}") from e
    _last_request = time.time()
    if r.status_code != 200:
        raise FetchError(f"{url}: HTTP {r.status_code}")
    enc = r.encoding if r.encoding and r.encoding.lower() not in ("iso-8859-1",) else encoding
    html = r.content.decode(enc, errors="replace")
    key.write_text(html, encoding="utf-8")
    return html


# ---------------------------------------------------------------- race list

def race_ids_for_date(yyyymmdd: str) -> list[str]:
    """開催日の JRA 全レース ID."""
    url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={yyyymmdd}"
    html = fetch(url, use_cache=False, encoding="UTF-8")
    ids = sorted(set(re.findall(r"race_id=(\d{12})", html)))
    return [i for i in ids if i[4:6] in COURSE_CODES]


def course_of(race_id: str) -> str:
    return COURSE_CODES.get(race_id[4:6], "?")


# ---------------------------------------------------------------- helpers

def _num(s: str | None, typ=float):
    if s is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return typ(m.group()) if m else None


def _time_to_sec(s: str) -> float | None:
    m = re.match(r"(?:(\d+):)?(\d+)\.(\d)", s.strip())
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


GRADE_RE = re.compile(r"\((G[123]|J\.?G[123]|L|OP)\)")


def _grade(name: str, extra: str = "") -> str | None:
    m = GRADE_RE.search(name)
    if m:
        return m.group(1).replace("J.", "J")
    for k in ("新馬", "未勝利", "1勝クラス", "2勝クラス", "3勝クラス", "オープン"):
        if k in extra or k in name:
            return {"1勝クラス": "1勝", "2勝クラス": "2勝", "3勝クラス": "3勝", "オープン": "OP"}.get(k, k)
    return None


def classify_pace(laps: list[float]) -> str | None:
    """ラップから展開を分類.

    瞬発: 後半3Fが前半3Fより1秒以上速く、かつラスト2Fで加速(11秒台前半以下)
    持続: 中盤から緩みなく11秒台が続く(ラスト4Fの最大と最小の差が小さい)
    消耗: 前半3Fが後半3Fより1秒以上速い(前傾)
    平均: それ以外
    """
    if not laps or len(laps) < 6:
        return None
    first3 = sum(laps[:3])
    last3 = sum(laps[-3:])
    last4 = laps[-4:]
    if first3 - last3 >= 1.0 and min(laps[-2:]) <= 11.4:
        return "瞬発"
    if last3 - first3 >= 1.0:
        return "消耗"
    if max(last4) - min(last4) <= 0.6:
        return "持続"
    return "平均"


# ---------------------------------------------------------------- results

def parse_result(html: str, race_id: str) -> tuple[dict, list[dict]]:
    """db.netkeiba.com/race/{race_id}/ のパース."""
    soup = BeautifulSoup(html, "lxml")
    name = ""
    h1 = soup.select_one("dl.racedata h1") or soup.select_one("h1")
    if h1:
        name = h1.get_text(strip=True)
    info = ""
    span = soup.select_one("dl.racedata diary_snap_cut span") or soup.select_one("dl.racedata span")
    if span:
        info = span.get_text(" ", strip=True)
    small = soup.select_one("p.smalltxt")
    small_t = small.get_text(" ", strip=True) if small else ""

    surface = "障" if "障" in info[:3] else ("ダ" if "ダ" in info[:3] else "芝")
    direction = next((d for d in ("右", "左", "直") if d in info[:4]), None)
    distance = _num(re.search(r"(\d{3,4})m", info).group(1), int) if re.search(r"(\d{3,4})m", info) else None
    weather = (re.search(r"天候\s*:\s*(\S+)", info) or [None, None])[1]
    going = (re.search(r"(?:芝|ダート)\s*:\s*(良|稍重|重|不良)", info) or [None, None])[1]
    dm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", small_t)
    date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else None

    results = []
    table = soup.select_one("table.race_table_01")
    if table:
        rows = table.find_all("tr")
        header = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        idx = {h: i for i, h in enumerate(header)}

        def col(cells, key):
            i = idx.get(key)
            return cells[i] if i is not None and i < len(cells) else None

        for tr in rows[1:]:
            cells = tr.find_all("td")
            if not cells:
                continue
            txt = lambda k: (col(cells, k).get_text(strip=True) if col(cells, k) else None)  # noqa: E731
            horse_a = col(cells, "馬名").find("a") if col(cells, "馬名") else None
            if not horse_a:
                continue
            horse_id = re.search(r"/horse/(\w+)", horse_a["href"]).group(1)
            sexage = txt("性齢") or ""
            bw = txt("馬体重") or ""
            bwm = re.match(r"(\d+)\(([+-]?\d+)\)", bw)
            jockey_c = col(cells, "騎手")
            trainer_c = col(cells, "調教師")
            results.append({
                "race_id": race_id,
                "horse_id": horse_id,
                "_horse_name": horse_a.get_text(strip=True),
                "finish": _num(txt("着順"), int) if (txt("着順") or "").isdigit() else None,
                "gate": _num(txt("枠番"), int),
                "number": _num(txt("馬番"), int),
                "sex": sexage[:1] or None,
                "age": _num(sexage[1:], int),
                "weight_carried": _num(txt("斤量")),
                "jockey": jockey_c.get_text(strip=True) if jockey_c else None,
                "trainer": re.sub(r"^\[.\]", "", trainer_c.get_text(strip=True)) if trainer_c else None,
                "time_sec": _time_to_sec(txt("タイム") or ""),
                "margin": txt("着差"),
                "passing": txt("通過"),
                "last3f": _num(txt("上り")),
                "odds": _num(txt("単勝")),
                "popularity": _num(txt("人気"), int),
                "body_weight": int(bwm.group(1)) if bwm else None,
                "body_weight_diff": int(bwm.group(2)) if bwm else None,
            })

    laps = []
    for th in soup.find_all("th"):
        if th.get_text(strip=True) == "ラップ":
            td = th.find_next_sibling("td")
            if td:
                laps = [float(x) for x in re.findall(r"\d+\.\d", td.get_text())]
            break
    # 端数距離(例: 1800m は 12.x で始まる 200m 刻み, 2500m は先頭が 100m 区間)
    first3f = sum(laps[:3]) if len(laps) >= 3 else None
    last3f = sum(laps[-3:]) if len(laps) >= 3 else None

    race = {
        "race_id": race_id,
        "date": date,
        "course": course_of(race_id),
        "race_no": int(race_id[-2:]),
        "name": GRADE_RE.sub("", name).strip() or name,
        "grade": _grade(name, small_t),
        "surface": surface,
        "distance": distance,
        "direction": direction,
        "weather": weather,
        "going": going,
        "n_runners": len(results),
        "laps": laps,
        "first3f": round(first3f, 1) if first3f else None,
        "last3f": round(last3f, 1) if last3f else None,
        "pace_type": classify_pace(laps),
        "payouts": parse_payouts(soup),
    }
    return race, results


def parse_payouts(soup) -> dict:
    """払戻表 (table.pay_table_01) → {券種: [[組番, 払戻円], ...]}."""
    out: dict[str, list] = {}
    for table in soup.select("table.pay_table_01"):
        for tr in table.find_all("tr"):
            th = tr.find("th")
            tds = tr.find_all("td")
            if not th or len(tds) < 2:
                continue
            kind = th.get_text(strip=True)
            combos = [c.strip() for c in tds[0].get_text("\n").split("\n") if c.strip()]
            pays = [c.strip() for c in tds[1].get_text("\n").split("\n") if c.strip()]
            out[kind] = [[c.replace(" ", ""), _num(pz, int)] for c, pz in zip(combos, pays)]
    return out


def fetch_result(race_id: str) -> tuple[dict, list[dict]]:
    return parse_result(fetch(f"https://db.netkeiba.com/race/{race_id}/"), race_id)


# ---------------------------------------------------------------- shutuba

def parse_shutuba(html: str, race_id: str) -> dict:
    """race.netkeiba.com/race/shutuba.html のパース → カード dict."""
    soup = BeautifulSoup(html, "lxml")
    name_el = soup.select_one(".RaceName")
    name = name_el.get_text(strip=True) if name_el else ""
    d1 = soup.select_one(".RaceData01")
    d1t = d1.get_text(" ", strip=True) if d1 else ""
    d2 = soup.select_one(".RaceData02")
    d2t = d2.get_text(" ", strip=True) if d2 else ""
    m = re.search(r"(芝|ダ|障)\s*(\d{3,4})m", d1t)
    surface, distance = (m.group(1), int(m.group(2))) if m else (None, None)
    going = (re.search(r"馬場\s*:\s*(良|稍|稍重|重|不良|不)", d1t) or [None, None])[1]
    going = {"稍": "稍重", "不": "不良"}.get(going, going)
    grade = None
    icon = soup.select_one(".RaceName .Icon_GradeType")
    if icon:
        cls = " ".join(icon.get("class", []))
        gm = re.search(r"Icon_GradeType(\d+)", cls)
        grade = {"1": "G1", "2": "G2", "3": "G3", "5": "OP", "15": "L"}.get(gm.group(1)) if gm else None
    grade = grade or _grade(name, d2t)

    entries = []
    for tr in soup.select("table.Shutuba_Table tr.HorseList"):
        def t(sel):
            el = tr.select_one(sel)
            return el.get_text(strip=True) if el else None
        a = tr.select_one(".HorseInfo a") or tr.select_one(".HorseName a")
        if not a:
            continue
        hid = re.search(r"/horse/(\w+)", a.get("href", ""))
        barei = t(".Barei") or ""
        tds = tr.find_all("td")
        weight = None
        for i, td in enumerate(tds):
            if "Barei" in (td.get("class") or []) and i + 1 < len(tds):
                weight = _num(tds[i + 1].get_text(strip=True))
        odds = t(".Popular span") or t(".Txt_R.Popular")
        entries.append({
            "gate": _num(t("td[class^=Waku]"), int),
            "number": _num(t("td[class^=Umaban]"), int),
            "horse_id": hid.group(1) if hid else None,
            "name": a.get("title") or a.get_text(strip=True),
            "sex": barei[:1] or None,
            "age": _num(barei[1:], int),
            "weight": weight,
            "jockey": t(".Jockey a") or t(".Jockey"),
            "trainer": t(".Trainer a") or t(".Trainer"),
            "odds": _num(odds) if odds and re.search(r"\d", odds) else None,
        })

    return {
        "race_id": race_id,
        "course": course_of(race_id),
        "race_no": int(race_id[-2:]),
        "name": name,
        "grade": grade,
        "surface": surface,
        "distance": distance,
        "going": going,
        "entries": entries,
    }


def fetch_shutuba(race_id: str) -> dict:
    html = fetch(f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}", use_cache=False)
    return parse_shutuba(html, race_id)


# ---------------------------------------------------------------- pedigree

ROWSPAN_GEN = {"16": 1, "8": 2, "4": 3, "2": 4}


def parse_pedigree(html: str) -> dict:
    """5代血統表 (blood_table) → {位置: 馬名}. 位置は 'S'=父, 'D'=母, 'DS'=母父 ..."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.blood_table")
    if not table:
        return {}
    ped: dict[str, str] = {}
    current: dict[int, str] = {0: ""}
    children: dict[str, int] = {}
    for td in table.find_all("td"):
        gen = ROWSPAN_GEN.get(td.get("rowspan", ""), 5)
        parent = current.get(gen - 1, "")
        k = children.get(parent, 0)
        pos = parent + ("S" if k == 0 else "D")
        children[parent] = k + 1
        current[gen] = pos
        a = td.find("a")
        nm = (a.get_text("\n", strip=True) if a else td.get_text("\n", strip=True)).split("\n")[0].strip()
        ped[pos] = nm
    return ped


def fetch_pedigree(horse_id: str) -> dict:
    return parse_pedigree(fetch(f"https://db.netkeiba.com/horse/ped/{horse_id}/"))
