"""JRA公式サイト(JRADB)の構造調査用クローラ.

JRADB は `doAction('/JRADB/accessS.html', 'pw01sli00/AF')` のように cname を POST して遷移する。
シードから cname を辿って最大 N ページを保存し、probe/jra/ に HTML と索引(index.json)を出力する。
GitHub Actions 上で実行し、結果を probe-jra ブランチに保存 → 開発環境で構造を解析する。
"""
import json
import re
import sys
import time
from collections import deque
from pathlib import Path

import requests

BASE = "https://www.jra.go.jp"
OUT = Path("probe/jra")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SEEDS = [
    ("/JRADB/accessS.html", "pw01sli00/AF"),        # レース結果（直近開催）
    ("/JRADB/accessS.html", "pw01skl00999999/B3"),  # 過去レース結果検索
    ("/JRADB/accessD.html", "pw01dli00/F3"),        # 出馬表
    ("/JRADB/accessU.html", "pw01uli00/03"),        # 競走馬検索
]
ACTION_RE = re.compile(r"doAction\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
HREF_RE = re.compile(r'href="(/JRADB/access\w\.html)\?CNAME=([^"&]+)"')


def fetch(sess, path, cname):
    r = sess.post(BASE + path, data={"cname": cname}, timeout=30)
    r.encoding = "shift_jis" if "shift" in (r.headers.get("content-type", "").lower()) or not r.encoding else r.encoding
    return r.status_code, r.content.decode(r.apparent_encoding or "shift_jis", errors="replace")


def main(limit=60, seeds=None):
    OUT.mkdir(parents=True, exist_ok=True)
    sess = requests.Session()
    sess.headers["User-Agent"] = UA
    top = sess.get(BASE + "/", timeout=30)
    (OUT / "000_top.html").write_bytes(top.content)
    index = [{"file": "000_top.html", "status": top.status_code, "path": "/", "cname": None}]
    q = deque((p, c, 0, "seed") for p, c in (seeds or SEEDS))
    seen = set()
    n = 1
    while q and n < limit:
        path, cname, depth, label = q.popleft()
        if (path, cname) in seen:
            continue
        seen.add((path, cname))
        try:
            st, html = fetch(sess, path, cname)
        except Exception as e:  # noqa: BLE001
            index.append({"path": path, "cname": cname, "error": str(e)})
            continue
        fn = f"{n:03d}_{re.sub(r'[^A-Za-z0-9]', '_', cname)}.html"
        (OUT / fn).write_text(html, encoding="utf-8")
        links = ACTION_RE.findall(html) + HREF_RE.findall(html)
        index.append({"file": fn, "status": st, "path": path, "cname": cname, "depth": depth,
                      "label": label, "n_links": len(links)})
        print(n, st, path, cname, len(links), flush=True)
        n += 1
        if depth < 3:
            # 同じ種類(cname の先頭8文字)は数件だけ辿る
            kinds = {}
            for p, c in links:
                k = c[:8]
                kinds[k] = kinds.get(k, 0) + 1
                if kinds[k] <= 2:
                    q.append((p, c, depth + 1, k))
        time.sleep(1.5)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    # 引数: 上限ページ数 [path|cname,path|cname,...]
    seeds = None
    if len(sys.argv) > 2 and sys.argv[2]:
        seeds = [tuple(x.split("|", 1)) for x in sys.argv[2].split(",")]
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 60, seeds)
