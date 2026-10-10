"""JRA公式サイト(JRADB)からのデータ取得とパース.

JRADB はページごとの `CNAME`(末尾2桁はチェックサム)を POST して遷移する。チェックサムは自前で計算せず、
  過去レース結果検索(pw01skl00999999/B3) → 埋め込みの月別キー(objParam) → 月ページ(pw01skl10YYYYMM)
  → 開催日ページ(pw01srl10…) → レース結果(pw01sde10…) / 馬ページ(pw01dud…)
  出馬表(pw01dli00/F3) → 開催日(pw01drl10…) → 各レース出馬表(pw01dde10…)
とリンクを辿る。ページは Shift_JIS。取得間隔は config.REQUEST_INTERVAL 秒以上。

cname の番号体系: pw01sde10 + 場(2) + 年(4) + 回(2) + 日(2) + R(2) + 日付(8)
→ race_id = 年 + 場 + 回 + 日 + R（netkeiba と同じ12桁）。馬の ID は pw01dud?? に続く10桁。
"""
from __future__ import annotations

import hashlib
import re
import time

import requests
from bs4 import BeautifulSoup

from ..config import COURSE_CODES, DATA_DIR

import os as _os
REQUEST_INTERVAL = float(_os.environ.get("JRA_INTERVAL", "1.0"))  # JRA へのアクセス間隔(秒)

BASE = "https://www.jra.go.jp"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CACHE_DIR = DATA_DIR / "cache" / "jra"

SEARCH = ("/JRADB/accessS.html", "pw01skl00999999/B3")
LATEST_RESULTS = ("/JRADB/accessS.html", "pw01sli00/AF")
ENTRIES_TOP = ("/JRADB/accessD.html", "pw01dli00/F3")

ACTION_RE = re.compile(r"doAction\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
HREF_RE = re.compile(r'href="(/JRADB/access\w\.html)\?CNAME=([^"&]+)"')
ROMAN = {"Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3"}


class FetchError(RuntimeError):
    pass


_session: requests.Session | None = None
_last = 0.0


def _sess() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = UA
        try:
            _session.get(BASE + "/", timeout=30)
        except requests.RequestException:
            pass
    return _session


def post(path: str, cname: str, use_cache: bool = True) -> str:
    """cname を POST してページを取得（キャッシュ付き）."""
    global _last
    key = CACHE_DIR / (hashlib.sha1(f"{path}|{cname}".encode()).hexdigest() + ".html")
    if use_cache and key.exists():
        return key.read_text(encoding="utf-8")
    wait = REQUEST_INTERVAL - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        try:
            r = _sess().post(BASE + path, data={"cname": cname}, timeout=30)
            break
        except requests.RequestException as e:
            if attempt == 2:
                raise FetchError(f"{cname}: {e}") from e
            time.sleep(5 * (attempt + 1))
    _last = time.time()
    if r.status_code != 200:
        raise FetchError(f"{cname}: HTTP {r.status_code}")
    html = r.content.decode("cp932", errors="replace")
    if not ACTION_RE.search(html) and not HREF_RE.search(html):
        # 正常な JRADB ページには必ず doAction / CNAME リンクがある
        title = BeautifulSoup(html[:5000], "lxml").title
        body = re.sub(r"\s+", " ", BeautifulSoup(html, "lxml").get_text(" "))[:200]
        raise FetchError(f"{cname}: error page (title={title.get_text() if title else None}; {body})")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key.write_text(html, encoding="utf-8")
    return html


def links(html: str, prefix: str) -> list[tuple[str, str]]:
    """ページ内の (path, cname) リンクのうち cname が prefix で始まるもの（出現順・重複なし）."""
    out, seen = [], set()
    for p, c in ACTION_RE.findall(html) + HREF_RE.findall(html):
        if c.startswith(prefix) and c not in seen:
            seen.add(c)
            out.append((p, c))
    return out


def norm_name(s: str | None) -> str | None:
    if s is None:
        return None
    return re.sub(r"\s+", "", s.replace("　", "")) or None


def _num(s, typ=float):
    if s is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", str(s).replace(",", ""))
    return typ(m.group()) if m else None


def _time_to_sec(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"(?:(\d+):)?(\d+)\.(\d)", s)
    if not m:
        return None
    return int(m.group(1) or 0) * 60 + int(m.group(2)) + int(m.group(3)) / 10


def _date(s: str) -> str | None:
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def race_id_from_cname(cname: str) -> str | None:
    """pw01sde10 CC YYYY KK DD RR YYYYMMDD / pw01dde10… → YYYY CC KK DD RR."""
    m = re.match(r"pw01[sd]de\d{2}(\d{2})(\d{4})(\d{2})(\d{2})(\d{2})(\d{8})", cname)
    if not m:
        return None
    cc, yyyy, kk, dd, rr, _ = m.groups()
    return f"{yyyy}{cc}{kk}{dd}{rr}"


def horse_id_from_cname(cname: str) -> str | None:
    m = re.match(r"pw01dud\d{2}(\d{10})", cname)
    return m.group(1) if m else None


def day_date_from_cname(cname: str) -> str | None:
    m = re.search(r"(\d{8})/", cname)
    if not m:
        return None
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def _grade_from(el) -> str | None:
    img = el.select_one(".grade_icon img") if el else None
    if not img:
        return None
    alt = img.get("alt", "")
    for k, v in ROMAN.items():
        alt = alt.replace(k, v)
    m = re.search(r"J?G\s*([123])", alt)
    if m:
        return ("JG" if "J" in alt else "G") + m.group(1)
    if "L" in alt or "リステッド" in alt:
        return "L"
    src = img.get("src", "")
    m = re.search(r"icon_grade_(?:s_)?(j?g[123]|l)", src)
    return m.group(1).upper() if m else None


CLASS_MAP = {"新馬": "新馬", "未勝利": "未勝利", "1勝クラス": "1勝", "2勝クラス": "2勝", "3勝クラス": "3勝",
             "オープン": "OP", "500万円以下": "1勝", "1000万円以下": "2勝", "1600万円以下": "3勝"}


def _race_header(soup) -> dict:
    head = {}
    d = soup.select_one(".race_header .date_line .date") or soup.select_one(".date_line .cell.date")
    head["date"] = _date(d.get_text(" ", strip=True)) if d else None
    wx = soup.select_one(".baba li.weather .txt")
    head["weather"] = wx.get_text(strip=True) if wx else None
    head["going"] = None
    for li in soup.select(".baba li"):
        if "weather" in (li.get("class") or []):
            continue
        t = li.select_one(".txt")
        if t:
            head["going"] = t.get_text(strip=True)
    rn = soup.select_one(".race_title .race_name")
    name = ""
    if rn:
        name = rn.find(string=True, recursive=False) or rn.get_text(strip=True)
        name = str(name).strip()
    head["name"] = name
    grade = _grade_from(soup.select_one(".race_title"))
    cls = soup.select_one(".race_title .type .class")
    cls_t = cls.get_text(strip=True) if cls else ""
    head["grade"] = grade or CLASS_MAP.get(cls_t, cls_t or None)
    course = soup.select_one(".race_title .type .course")
    ct = course.get_text(" ", strip=True) if course else ""
    head["distance"] = _num(ct.replace(",", ""), int)
    detail = course.select_one(".detail").get_text(strip=True) if course and course.select_one(".detail") else ""
    is_jump = "障害" in detail or "障害" in (name or "") or "ジャンプ" in (name or "")
    head["surface"] = "障" if is_jump else ("ダ" if "ダート" in detail else ("芝" if "芝" in detail else None))
    head["direction"] = next((x for x in ("右", "左", "直") if x in detail), None)
    return head


def parse_result(html: str, cname: str) -> tuple[dict, list[dict]]:
    """レース結果ページ(pw01sde…) → (race, results)."""
    from .netkeiba import classify_pace
    soup = BeautifulSoup(html, "lxml")
    head = _race_header(soup)
    rid = race_id_from_cname(cname)
    results = []
    table = soup.select_one("#race_result table")
    for tr in (table.select("tbody tr") if table else []):
        def td(cls):
            return tr.select_one(f"td.{cls}")

        def tx(cls):
            el = td(cls)
            return el.get_text(" ", strip=True) if el else None
        a = td("horse").find("a") if td("horse") else None
        if not a:
            continue
        hc = re.search(r"CNAME=([^\"&]+)", a.get("href", ""))
        hcname = hc.group(1) if hc else None
        place = tx("place") or ""
        waku = td("waku").find("img") if td("waku") else None
        corners = [li.get_text(strip=True) for li in tr.select("td.corner li")]
        hw = tx("h_weight") or ""
        hwm = re.match(r"(\d+)\s*\(([+-]?\d+)\)", hw.replace(" ", ""))
        age = tx("age") or ""
        sex = age[:1]
        if age.startswith("せん"):
            sex = "セ"
        results.append({
            "race_id": rid,
            "horse_id": horse_id_from_cname(hcname) if hcname else None,
            "_horse_name": a.get_text(strip=True),
            "_horse_cname": hcname,
            "finish": int(place) if place.isdigit() else None,
            "gate": _num(waku.get("alt"), int) if waku else None,
            "number": _num(tx("num"), int),
            "sex": sex or None,
            "age": _num(age, int),
            "weight_carried": _num(tx("weight")),
            "jockey": norm_name(tx("jockey")),
            "trainer": norm_name(tx("trainer")),
            "time_sec": _time_to_sec(tx("time")),
            "margin": (tx("margin") or "").strip() or None,
            "passing": "-".join(c for c in corners if c.isdigit()) or None,
            "last3f": _num(tx("f_time")),
            "odds": None,
            "popularity": _num(tx("pop"), int),
            "body_weight": int(hwm.group(1)) if hwm else _num(hw, int),
            "body_weight_diff": int(hwm.group(2)) if hwm else None,
        })

    laps = []
    for th in soup.select(".result_time_data th"):
        if "ハロン" in th.get_text():
            td_ = th.find_next_sibling("td")
            laps = [float(x) for x in re.findall(r"\d+\.\d", td_.get_text())] if td_ else []
    payouts = parse_payouts(soup)
    # 単勝払戻から勝ち馬のオッズを復元（回収率集計用）
    for kind, rows in payouts.items():
        if kind == "単勝":
            for combo, yen in rows:
                for r in results:
                    if str(r["number"]) == combo and yen:
                        r["odds"] = yen / 100
    race = {
        "race_id": rid,
        "date": head["date"] or day_date_from_cname(cname),
        "course": COURSE_CODES.get(rid[4:6], "?") if rid else None,
        "race_no": int(rid[-2:]) if rid else None,
        "name": head["name"],
        "grade": head["grade"],
        "surface": head["surface"],
        "distance": head["distance"],
        "direction": head["direction"],
        "weather": head["weather"],
        "going": head["going"],
        "n_runners": len(results),
        "laps": laps,
        "first3f": round(sum(laps[:3]), 1) if len(laps) >= 3 else None,
        "last3f": round(sum(laps[-3:]), 1) if len(laps) >= 3 else None,
        "pace_type": classify_pace(laps),
        "payouts": payouts,
    }
    return race, results


def parse_payouts(soup) -> dict:
    out: dict[str, list] = {}
    for li in soup.select(".refund_area li"):
        dt = li.find("dt")
        if not dt:
            continue
        kind = dt.get_text(strip=True).replace("３連", "3連")
        rows = []
        for line in li.select("dd .line"):
            num = line.select_one(".num")
            yen = line.select_one(".yen")
            if num and yen:
                rows.append([num.get_text(strip=True).replace(" ", ""), _num(yen.get_text(), int)])
        if rows:
            out[kind] = rows
    return out


def parse_horse(html: str, cname: str | None = None) -> dict:
    """馬ページ(pw01dud…) → 馬の基本情報と血統(父・母・母の父・母の母)."""
    soup = BeautifulSoup(html, "lxml")
    prof = {}
    for dl in soup.select("dl"):
        k = dl.find("dt")
        v = dl.find("dd")
        if k and v:
            prof[k.get_text(strip=True)] = v.get_text(" ", strip=True)
    # dl 以外の表組みの場合に備え、テキスト全体からも拾う
    text = soup.get_text("\n", strip=True)

    def after(label):
        if label in prof:
            return prof[label]
        m = re.search(rf"\n{label}\n([^\n]+)", text)
        return m.group(1).strip() if m else None
    name_el = soup.select_one(".horse_name, h1, .header_line .name")
    def clean(v):
        return re.sub(r"\s*産駒$", "", v).strip() if v else None
    ped = {k: clean(v) for k, v in {
        "S": after("父"), "D": after("母"), "DS": after("母の父"), "DD": after("母の母"),
    }.items() if clean(v)}
    return {
        "horse_id": horse_id_from_cname(cname) if cname else None,
        "name": name_el.get_text(strip=True) if name_el else None,
        "sex": after("性別"),
        "birth": _date(after("生年月日") or ""),
        "pedigree": ped,
    }


def parse_shutuba(html: str, cname: str) -> dict:
    """出馬表(pw01dde…) → カード dict（前4走つき）."""
    soup = BeautifulSoup(html, "lxml")
    head = _race_header(soup)
    rid = race_id_from_cname(cname)
    entries = []
    for tr in soup.select("table tbody tr"):
        hcell = tr.select_one("td.horse")
        if not hcell:
            continue
        a = hcell.select_one(".name a")
        if not a:
            continue
        hc = re.search(r"CNAME=([^\"&]+)", a.get("href", ""))
        waku = tr.select_one("td.waku img")
        num = tr.select_one("td.num")
        odds = hcell.select_one(".odds_line .num")
        pop = hcell.select_one(".odds_line .pop_rank")
        bw = hcell.select_one(".result_line .weight")
        bwt = bw.get_text(strip=True) if bw else ""
        bwd = re.search(r"\(([+-]?\d+)\)", bwt)
        sire = hcell.select_one(".family_line .sire")
        mare = hcell.select_one(".family_line .mare")
        bloodmare = mare.select_one(".bloodmare") if mare else None
        dam = None
        if mare:
            dam = (mare.find(string=True, recursive=False) or "")
            dam = "".join(t for t in mare.find_all(string=True, recursive=False)).strip() or None
        jc = tr.select_one("td.jockey")
        agec = jc.select_one(".age").get_text(strip=True) if jc and jc.select_one(".age") else ""
        sex = "セ" if agec.startswith("せん") else agec[:1]
        trainer = hcell.select_one(".trainer a")
        recent = [parse_past_cell(td) for td in tr.select("td.past")]
        entries.append({
            "gate": _num(waku.get("alt"), int) if waku else None,
            "number": _num((num.get_text(" ", strip=True).split() or [None])[0] if num else None, int),
            "horse_id": horse_id_from_cname(hc.group(1)) if hc else None,
            "_horse_cname": hc.group(1) if hc else None,
            "name": a.get_text(strip=True),
            "sex": sex or None,
            "age": _num(agec, int),
            "weight": _num(jc.select_one(".weight").get_text() if jc and jc.select_one(".weight") else None),
            "jockey": norm_name(jc.select_one(".jockey").get_text(strip=True)) if jc and jc.select_one(".jockey") else None,
            "trainer": norm_name(trainer.get_text(strip=True)) if trainer else None,
            "odds": _num(odds.get_text()) if odds else None,
            "popularity": _num(pop.get_text(), int) if pop else None,
            "body_weight_diff": int(bwd.group(1)) if bwd else None,
            "sire": sire.get_text(strip=True).replace("父：", "") if sire else None,
            "dam": dam.replace("母：", "") if dam else None,
            "damsire": re.sub(r"[()（）]|母の父：", "", bloodmare.get_text(strip=True)) if bloodmare else None,
            "recent": [r for r in recent if r],
        })
    provisional = bool(entries) and any(e["number"] is None for e in entries)
    if provisional:   # 枠順確定前: 馬番が無いので掲載順の仮番号（枠順確定後の出馬表で置き換わる）
        for i, e in enumerate(entries, 1):
            e["number"], e["gate"] = i, None
    return {
        "race_id": rid,
        "provisional_numbers": provisional,
        "date": head["date"] or day_date_from_cname(cname),
        "course": COURSE_CODES.get(rid[4:6], "?") if rid else None,
        "race_no": int(rid[-2:]) if rid else None,
        "name": head["name"],
        "grade": head["grade"],
        "surface": head["surface"],
        "distance": head["distance"],
        "going": head["going"],
        "entries": entries,
        "_cname": cname,
    }


def parse_past_cell(td) -> dict | None:
    """出馬表の前走セル → 近走 dict."""
    d = td.select_one(".date_line .date")
    if not d:
        return None
    link = td.select_one(".race_line .name a")
    rc = re.search(r"CNAME=([^\"&]+)", link.get("href", "")) if link else None
    place = td.select_one(".place_line .place")
    dist = td.select_one(".dist")
    dist_t = dist.get_text(strip=True) if dist else ""
    fin_line = td.select_one(".fin")
    behind = None
    if fin_line and fin_line.select_one(".time"):
        behind = _num(fin_line.select_one(".time").get_text())
    finish = _num(place.get_text(), int) if place else None
    if behind is not None and finish == 1:
        behind = -abs(behind)   # 勝った時は2着馬との差(マイナス=先着)
    corners = [li.get_text(strip=True) for li in td.select(".corner_list li")]
    f3 = td.select_one(".f3")
    grade = _grade_from(td.select_one(".race_line"))
    rid = race_id_from_cname(rc.group(1)) if rc else None

    def g(sel):
        el = td.select_one(sel)
        return el.get_text(strip=True) if el else None
    return {
        "date": _date(d.get_text()),
        "course": g(".date_line .rc"),
        "race_name": link.get_text(strip=True) if link else None,
        "race_id": rid,
        "_race_cname": rc.group(1) if rc else None,
        "grade": grade,
        "finish": finish,
        "n_runners": _num(g(".num .max"), int),
        "number": _num(g(".num .gate"), int),
        "popularity": _num(g(".num .pop"), int),
        "jockey": norm_name(g(".info_line1 .jockey")),
        "weight_carried": _num(g(".info_line1 .weight")),
        "distance": _num(dist_t, int),
        "surface": "ダ" if "ダ" in dist_t else ("障" if "障" in dist_t else "芝"),
        "time_sec": _time_to_sec(g(".time")),
        "going": g(".condition"),
        "body_weight": _num(g(".h_weight"), int),
        "passing": "-".join(c for c in corners if c.isdigit()) or None,
        "last3f": _num(f3.get_text().replace("3F", "")) if f3 else None,
        "behind": behind,
    }


# ---------------------------------------------------------------- 巡回

def month_cnames(html: str | None = None) -> dict[str, str]:
    """過去レース結果検索ページの objParam → {YYYYMM: cname}."""
    html = html or post(*SEARCH, use_cache=False)
    out = {}
    for yymm, cs in re.findall(r'objParam\["(\d{4})"\]\s*=\s*"([0-9A-F]{2})"', html):
        out["20" + yymm] = f"pw01skl10{'20' + yymm}/{cs}"
    return out


def day_lists_in_month(yyyymm: str, months: dict | None = None) -> list[tuple[str, str]]:
    """月の開催日ページ一覧. 月ページに加え、直近分は『最新のレース結果』ページからも拾う."""
    months = months or month_cnames()
    out: dict[str, tuple[str, str]] = {}
    cn = months.get(yyyymm)
    errors = []
    if cn:
        try:
            for p, c in links(post("/JRADB/accessS.html", cn, use_cache=False), "pw01srl1"):
                out[c] = (p, c)
        except FetchError as e:
            errors.append(e)
    try:
        for p, c in links(post(*LATEST_RESULTS, use_cache=False), "pw01srl1"):
            if (day_date_from_cname(c) or "").replace("-", "")[:6] == yyyymm:
                out[c] = (p, c)
    except FetchError as e:
        errors.append(e)
    if not out and errors:
        raise errors[0]
    return sorted(out.values(), key=lambda x: (day_date_from_cname(x[1]) or "", x[1]))


def races_in_day(day: tuple[str, str]) -> list[tuple[str, str]]:
    html = post(*day)
    return links(html, "pw01sde1")


def entry_days() -> list[tuple[str, str]]:
    """出馬表トップの開催日リンク。枠順確定後は pw01drl1…、確定前（出走予定馬）は pw01drl0… の形。
    同じ開催日に両方あれば枠順確定後（1）を優先する."""
    ls = links(post(*ENTRIES_TOP, use_cache=False), "pw01drl")
    best: dict = {}
    for p, c in ls:
        key = c[9:].split("/")[0]    # 'pw01drl' + 種別2桁 の後ろ（場・年・回・日・日付。/以降の検査値は除く）
        if key not in best or c.startswith("pw01drl1"):
            best[key] = (p, c)
    return list(best.values())


def entry_races(day: tuple[str, str]) -> list[tuple[str, str]]:
    return links(post(*day, use_cache=False), "pw01dde")
