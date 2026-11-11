"""当日の結果を Yahoo!競馬の結果ページ（fetch-pages で取得したHTML）から実績DBに入れる（JRA公式の過去成績に載る前の暫定）.
使い方: python tools/import_yahoo_results.py <HTMLのフォルダ（urls.txt と 01.html…）> <カードのフォルダ cards/YYYY-MM-DD>
レース情報（クラス・距離・頭数）はカードから、着順・タイム・人気（単勝オッズ順）・上がり・騎手・斤量・馬体重は結果ページから。"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bs4 import BeautifulSoup  # noqa: E402
from keiba import db  # noqa: E402

src, cards = Path(sys.argv[1]), Path(sys.argv[2])
conn = db.connect()
urls = (src / "urls.txt").read_text().split()
n_r = 0
for i, u in enumerate(urls, 1):
    yid = u.rstrip("/").rsplit("/", 1)[1]          # 2605040307
    rid = "20" + yid
    cf = cards / f"{rid}.json"
    if not cf.exists():
        continue
    card = json.loads(cf.read_text(encoding="utf-8"))
    s = BeautifulSoup((src / f"{i:02d}.html").read_text(encoding="utf-8"), "html.parser")
    rows = []
    for tb in s.find_all("table"):
        trs = tb.find_all("tr")
        if not trs or "着順" not in trs[0].get_text():
            continue
        for tr in trs[1:]:
            td = [x.get_text(" ", strip=True) for x in tr.find_all("td")]
            a = [x["href"] for x in tr.find_all("a", href=True)]
            hid = next((re.search(r"/horse/(\d+)", h).group(1) for h in a if "/horse/" in h), None)
            if len(td) < 8 or not hid:
                continue
            m = re.match(r"(\d+):(\d+\.\d)", td[4])
            bw = re.search(r"/(\d+)\(([+-]?\d+)\)", td[3])
            odds = re.search(r"\(([\d.]+)\)", td[7])
            jw = re.match(r"(.+?)\s+([\d.]+)$", td[6])
            rows.append({"race_id": rid, "horse_id": hid, "finish": int(td[0]) if td[0].isdigit() else None,
                         "gate": int(td[1]) if td[1].isdigit() else None, "number": int(td[2]),
                         "sex": None, "age": None, "weight_carried": float(jw.group(2)) if jw else None,
                         "jockey": (jw.group(1) if jw else td[6]).replace(" ", ""), "trainer": td[8].replace(" ", "") if len(td) > 8 else None,
                         "time_sec": int(m.group(1)) * 60 + float(m.group(2)) if m else None,
                         "margin": td[4].split()[-1] if " " in td[4] else None, "passing": None,
                         "last3f": float(td[5].split()[-1]) if re.search(r"\d+\.\d$", td[5]) else None,
                         "odds": float(odds.group(1)) if odds else None, "popularity": None,
                         "body_weight": int(bw.group(1)) if bw else None, "body_weight_diff": int(bw.group(2)) if bw else None,
                         "_name": td[3].split()[0]})
        break
    if not rows or not any(r["finish"] for r in rows):
        continue
    for k, r in enumerate(sorted([r for r in rows if r["odds"]], key=lambda r: r["odds"]), 1):
        r["popularity"] = k
    db.upsert_race(conn, {"race_id": rid, "date": card["date"], "course": card["course"], "race_no": card["race_no"],
                          "name": card.get("name"), "grade": card.get("grade"), "surface": card.get("surface"),
                          "distance": card.get("distance"), "direction": card.get("direction"), "weather": None,
                          "going": card.get("going"), "n_runners": len(rows), "laps": None})
    ent = {e.get("horse_id"): e for e in card.get("entries", [])}
    for r in rows:
        name = r.pop("_name")
        e = ent.get(r["horse_id"], {})
        r["sex"], r["age"] = e.get("sex"), e.get("age")
        db.upsert_result(conn, r)
        if not db.has_horse(conn, r["horse_id"]):
            db.upsert_horse(conn, {"horse_id": r["horse_id"], "name": name, "sex": e.get("sex"), "sire": e.get("sire"),
                                   "dam": e.get("dam"), "damsire": e.get("damsire"), "pedigree": e.get("pedigree") or {}})
    n_r += 1
conn.commit()
print("races", n_r)
