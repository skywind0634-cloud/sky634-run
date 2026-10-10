"""地方競馬公式(keiba.go.jp)の構造調査: 指定URLの生HTMLを probe/ に保存（GitHub Actions 上で実行）."""
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (sky634 research; low-frequency)"}


def main(urls_file):
    out = Path("probe")
    out.mkdir(exist_ok=True)
    idx = []
    for u in [x.strip() for x in Path(urls_file).read_text().splitlines() if x.strip() and not x.startswith("#")]:
        time.sleep(2.0)
        try:
            r = requests.get(u, headers=UA, timeout=30)
            r.encoding = r.apparent_encoding
            fn = out / (hashlib.sha1(u.encode()).hexdigest()[:12] + ".html")
            fn.write_text(r.text, encoding="utf-8")
            idx.append({"url": u, "status": r.status_code, "file": str(fn), "len": len(r.text)})
            print(r.status_code, len(r.text), u, flush=True)
        except Exception as e:  # noqa: BLE001
            idx.append({"url": u, "error": str(e)})
            print("ERR", u, e, flush=True)
    (out / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
