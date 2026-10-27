"""坂上明大「重賞血統査定」の取得ページ（sakagami-sealed で取得したテキスト）から、血統傾向〜各馬の査定の部分だけを取り出し、
そのレースの条件（DBの重賞から記事の日付とレース名で特定）を "RACE: 東京 芝 2400 外" 行として付ける（tools/trait_mining.py の入力）.
使い方: python3 -I tools/sakagami_prep.py <取得テキストのディレクトリ> <出力ディレクトリ> <keiba.db>
"""
import re, sys, os, json, sqlite3, unicodedata, datetime as dt
src, dst, dbp = sys.argv[1:]
c = sqlite3.connect(dbp)
races = c.execute("select date,name,course,surface,distance,layout from races where grade in ('G1','G2','G3')").fetchall()
n = nr = 0
for f in os.listdir(src):
    t = open(os.path.join(src, f), encoding="utf-8").read().replace("\\r", "").replace("\r", "")
    t = unicodedata.normalize("NFKC", t)
    head = t.split("\n\n", 1)[0]
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    try:
        a = next(i for i, l in enumerate(lines) if re.match(r"[〈<].*血統傾向[〉>]", l))
    except StopIteration:
        continue
    last = max((i for i, l in enumerate(lines) if re.match(r"(能力|素質)評価", l)), default=len(lines) - 1)
    body = lines[a:last + 1]
    title = re.search(r"TITLE: (.*)", head).group(1)
    pub = re.search(r'"datePublished":"(\d{4}-\d\d-\d\d)', t)
    rname = re.findall(r"【([^】]+)】", title)
    race = None
    if pub and rname:
        d0 = dt.date.fromisoformat(pub.group(1))
        for rn in rname:
            key = re.sub(r"(G[1-3]|ステークス|S$)", "", rn)[:4]
            cand = [r for r in races if key and key in (r[1] or "") and 0 <= (dt.date.fromisoformat(r[0]) - d0).days <= 8]
            if cand:
                race = cand[0]; break
    trend, k = [], 1
    while k < len(body) and not re.fullmatch(r"[ァ-ヴー・]{2,18}", body[k]):
        if not body[k].endswith("?"):
            trend.append(body[k])
        k += 1
    out = head + "\n" + (f"RACE: {race[2]} {race[3]} {race[4]} {race[5] or ''}\n" if race else "") + "\n"
    out += "\n".join("【傾向】" + x for x in trend) + "\n" + "\n".join(body[k:])
    open(os.path.join(dst, f), "w", encoding="utf-8").write(out); n += 1; nr += bool(race)
print(n, "本, レース特定", nr)
