"""地方競馬（NAR, keiba.go.jp）のレース（最終レース or 全レース）の取得と解析.

取得（GitHub Actions 上で実行。2秒以上の間隔、取得済みはキャッシュ）:
  月別開催日程 → その日のレース一覧（最終レースの番号）→ 成績表（着順・人気・払戻）＋ 出馬表（父・母・母父・近5走）
出力: data/nar/<競馬場コード>.jsonl（1行1レース）
競馬場コード: 浦和=18, 船橋=19, 大井=20, 川崎=21, 高知=31（keiba.go.jp の k_babaCode）
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path

BASE = "https://www.keiba.go.jp/KeibaWeb"
BABA = {"18": "浦和", "19": "船橋", "20": "大井", "21": "川崎", "31": "高知"}
CACHE = Path("data/cache/nar")
INTERVAL = 2.0
_last = [0.0]


def get(url: str) -> str:
    import requests
    CACHE.mkdir(parents=True, exist_ok=True)
    fn = CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".html")
    if fn.exists():
        return fn.read_text(encoding="utf-8")
    wait = INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for i in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (sky634 research; low-frequency)"}, timeout=30)
            _last[0] = time.time()
            r.encoding = r.apparent_encoding
            if r.status_code == 200:
                fn.write_text(r.text, encoding="utf-8")
                return r.text
        except Exception:   # noqa: BLE001
            time.sleep(5 * (i + 1))
    return ""


def _d(date: dt.date) -> str:
    return f"{date.year}%2f{date.month:02d}%2f{date.day:02d}"


def race_dates(baba: str, year: int, month: int) -> list[dt.date]:
    h = get(f"{BASE}/MonthlyConveneInfo/MonthlyConveneInfoTop?k_year={year}&k_month={month}")
    out = set()
    for y, m, d in re.findall(r"RaceList\?k_raceDate=(\d{4})%2[Ff](\d{2})%2[Ff](\d{2})&(?:amp;)?k_babaCode=" + baba + r"\b", h):
        out.add(dt.date(int(y), int(m), int(d)))
    return sorted(out)


def race_nos(baba: str, date: dt.date) -> list[int]:
    h = get(f"{BASE}/TodayRaceInfo/RaceList?k_raceDate={_d(date)}&k_babaCode={baba}")
    return sorted({int(x) for x in re.findall(r"RaceMarkTable\?k_raceDate=[^\"']+?k_raceNo=(\d+)", h)})


def final_race_no(baba: str, date: dt.date) -> int | None:
    nos = race_nos(baba, date)
    return nos[-1] if nos else None


def _txt(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def parse_result(h: str) -> dict | None:
    from bs4 import BeautifulSoup
    s = BeautifulSoup(h, "html.parser")
    body = s.get_text("\n", strip=True)
    m = re.search(r"(\d{4})年(\d+)月(\d+)日.*?第(\d+)競走\n競走成績\n(.*?)\n(ダート|芝)[　 ]*(\d+)ｍ", body, re.S)
    if not m:
        return None
    name = " ".join(m.group(5).split("\n"))
    head = body[m.start():m.start() + 400]
    weather = (re.search(r"天候：(\S+)", head) or [None, None])[1]
    going = (re.search(r"馬場：(\S+)", head) or [None, None])[1]
    rows = []
    for t in s.find_all("table"):
        ths = [_txt(x) for x in t.find_all("th")]
        if "着順" in ths and "馬名" in ths:
            for tr in t.find_all("tr")[1:]:
                c = {(td.get("class") or [""])[0]: _txt(td) for td in tr.find_all("td", recursive=False)}
                if not c.get("c"):
                    continue
                sa = c.get("f", "").split()
                bw = re.match(r"(\d+)\s*\(([-+]?\d+)\)", c.get("j", ""))
                rows.append({"fin": int(c["a"]) if c.get("a", "").isdigit() else None, "fin_raw": c.get("a"),
                             "gate": int(c["b"]) if c.get("b", "").isdigit() else None, "num": int(c["c"]),
                             "name": c.get("d"), "belong": c.get("e"), "sex": sa[0] if sa else None,
                             "age": int(sa[1]) if len(sa) > 1 and sa[1].isdigit() else None,
                             "wt": float(c["g"]) if re.match(r"^\d+(\.\d)?$", c.get("g", "")) else None,
                             "jockey": re.sub(r"[▲△☆◇★]", "", c.get("h", "").split("（")[0]).strip(),
                             "trainer": c.get("i"), "bw": int(bw.group(1)) if bw else None,
                             "bwd": int(bw.group(2)) if bw else None, "time": c.get("k"), "margin": c.get("l"),
                             "last3f": float(c["m"]) if re.match(r"^\d+\.\d$", c.get("m", "")) else None,
                             "passing": c.get("n"), "pop": int(c["o"]) if c.get("o", "").isdigit() else None})
    pay = {}
    for t in s.find_all("table"):
        if not t.find("td", class_="refundMoney"):
            continue
        kind = None
        for tr in t.find_all("tr"):
            title = tr.find("td", class_="title")
            if title:
                kind = _txt(title)
            money = tr.find("td", class_="refundMoney")
            if not money or not kind:
                continue
            combo = _txt(tr.find("td", class_=["a", "d"]))
            yen = int(re.sub(r"[^\d]", "", _txt(money)) or 0)
            pop = re.sub(r"[^\d]", "", _txt(tr.find("td", class_="c")))
            pay.setdefault(kind, []).append([combo, yen, int(pop) if pop else None])
    return {"date": f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", "race_no": int(m.group(4)),
            "name": name, "surface": m.group(6), "distance": int(m.group(7)), "weather": weather, "going": going,
            "n_runners": sum(1 for r in rows if r["fin"]), "entries": rows, "pay": pay}


def parse_deba(h: str) -> dict:
    """出馬表: 馬番 → 父・母・母父・近5走."""
    from bs4 import BeautifulSoup
    s = BeautifulSoup(h, "html.parser")
    out = {}
    for tr in s.select("tr.tBorder"):
        num_td = tr.find("td", class_="horseNum")
        if not num_td or not _txt(num_td).isdigit():
            continue
        rows = [tr]
        n = tr
        for _ in range(4):
            n = n.find_next_sibling("tr")
            if n is None:
                break
            rows.append(n)
        if len(rows) < 5:
            continue
        cells = [[_txt(td) for td in r.find_all("td", recursive=False)] for r in rows]
        # 近5走は各行の末尾5セル（枠番セルが2頭で共有される行は先頭の列数が1つ少ないので、末尾から数える）
        tail = [c[-5:] if len(c) >= 5 else [""] * 5 for c in cells]
        past = []
        for i, c0 in enumerate(tail[0]):
            mm = re.match(r"(\d+|\S+)\s+(\d{2})\.(\d{2})\.(\d{2})\s+(\S+)\s+(\d+)頭\s+(\S+)\s+(\S)?(\d+)\s+(\d+)番", c0)
            if not mm:
                continue
            pn = re.match(r"(\d+)人\s+(\d+)?\s*(\S+)?\s*([\d.]+)?", tail[2][i])
            tp = tail[3][i].split()
            mg = tail[4][i].split()
            past.append({"fin": int(mm.group(1)) if mm.group(1).isdigit() else None,
                         "date": f"20{mm.group(2)}-{mm.group(3)}-{mm.group(4)}", "going": mm.group(5),
                         "heads": int(mm.group(6)), "course": mm.group(7), "dist": int(mm.group(9)),
                         "num": int(mm.group(10)), "class": tail[1][i], "pop": int(pn.group(1)) if pn else None,
                         "jockey": pn.group(3) if pn else None,
                         "time": tp[0] if tp else None, "passing": tp[1] if len(tp) > 2 else None,
                         "last3f": float(tp[-1]) if len(tp) > 1 and re.match(r"^\d+\.\d$", tp[-1]) else None,
                         "margin": mg[0] if mg else None, "winner": " ".join(mg[1:]) or None})
        head = cells[0][:len(cells[0]) - 5]
        jidx = next((j for j, c in enumerate(head) if "（" in c), None)
        out[int(_txt(num_td))] = {"name": head[jidx - 1] if jidx else None,
                                  "jockey": head[jidx].split("（")[0].strip() if jidx is not None else None,
                                  "jockey_belong": (re.search(r"（(.+?)）", head[jidx]) or [None, None])[1] if jidx is not None else None,
                                  "wt": (re.match(r"([\d.]+)", cells[1][3]) or [None, None])[1] if len(cells[1]) > 3 else None,
                                  "trainer": cells[2][1] if len(cells[2]) > 1 else None,
                                  "sire": cells[2][0] if cells[2] else None, "dam": cells[3][0] if cells[3] else None,
                                  "damsire": (cells[4][0] if cells[4] else "").strip("（）()") or None, "past": past}
    return out


def collect(baba: str, start: dt.date, end: dt.date, out_dir: Path = Path("data/nar"), budget_min: float = 140,
            all_races: bool = False, out_name: str | None = None) -> int:
    """all_races=False: その日の最終レースだけ。True: 全レース（out_name で出力ファイル名を指定）."""
    t0 = time.time()
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = out_dir / (out_name or f"{baba}.jsonl")
    done = set()
    if fn.exists():
        for line in fn.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                done.add((r["date"], r["race_no"] if all_races else None))
            except (ValueError, KeyError):
                pass
    n = 0
    y, m = start.year, start.month
    with fn.open("a", encoding="utf-8") as f:
        while (y, m) <= (end.year, end.month):
            for d in race_dates(baba, y, m):
                if not (start <= d <= end) or (not all_races and (d.isoformat(), None) in done):
                    continue
                nos = race_nos(baba, d)
                if not all_races:
                    nos = nos[-1:]
                for rno in nos:
                    if all_races and (d.isoformat(), rno) in done:
                        continue
                    if (time.time() - t0) / 60 > budget_min:
                        return n
                    res = parse_result(get(f"{BASE}/TodayRaceInfo/RaceMarkTable?k_raceDate={_d(d)}&k_raceNo={rno}&k_babaCode={baba}"))
                    if not res or not res["entries"]:
                        continue
                    deba = parse_deba(get(f"{BASE}/TodayRaceInfo/DebaTable?k_raceDate={_d(d)}&k_raceNo={rno}&k_babaCode={baba}"))
                    for e in res["entries"]:
                        e.update(deba.get(e["num"], {}))
                    res["baba"] = BABA.get(baba, baba)
                    res["final"] = rno == max(race_nos(baba, d))
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                    f.flush()
                    n += 1
                    print(res["date"], res["baba"], res["race_no"], res["name"][:30], len(res["entries"]), flush=True)
            m += 1
            if m > 12:
                y, m = y + 1, 1
    return n


if __name__ == "__main__":
    import sys
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("baba"); ap.add_argument("start"); ap.add_argument("end")
    ap.add_argument("--all", action="store_true", help="全レース")
    ap.add_argument("--out", default=None, help="出力ファイル名（data/nar/ 配下）")
    ap.add_argument("--budget", type=float, default=140, help="取得に使う最大分数")
    a = ap.parse_args()
    print("races", collect(a.baba, dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end),
                           budget_min=a.budget, all_races=a.all, out_name=a.out))
