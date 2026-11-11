"""調教師・騎手 × クラス（重賞/OP）× 単勝の倍率帯 の総当たり（2026-11-08 みやこS 1着 11ロードクロンヌ＝netkeibaの卍氏が「四位厩舎は重賞の単勝9.9倍以下で毎年複勝回収100%超」と挙げていたのに、
こちらは厩舎×クラス×倍率を材料にしていなかった反省。ユーザー「11は卍があげていた。よほどお前よりうまいな」）.
3期（2021-23 / 2024 / 2025-26/9）とも A/E（3着内の実数÷人気からの見込み）1.15以上、各期の見込み2以上の組を data/knowledge/conn_class_scan.json に入れ、keiba/digest.py が○の材料にする.
使い方: python3 tools/conn_class_scan.py"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cls(grade, name):
    if grade in ("G1", "G2", "G3"):
        return "重賞"
    if grade in ("OP", "L") or (name and ("ステークス" in name or name.endswith("S"))):
        return "OP"
    return None


def per(d):
    return 0 if d < "2024" else 1 if d < "2025" else 2


def main():
    c = sqlite3.connect(Path(__import__("os").environ.get("ANALYSIS_DB") or (ROOT / "data" / "keiba.db")))
    rows = c.execute("""select r.date,r.grade,r.name,x.trainer,x.jockey,x.popularity,x.finish,x.odds
        from results x join races r on r.race_id=x.race_id where x.finish>0 and x.popularity>0 and r.date<'2026-10-01'""").fetchall()
    base = defaultdict(lambda: [0, 0])
    for r in rows:
        k = min(r[5], 16); base[k][0] += 1; base[k][1] += r[6] <= 3
    e = {k: v[1] / v[0] for k, v in base.items()}
    agg = defaultdict(lambda: [[0, 0.0, 0] for _ in range(3)])
    for d, g, nm, tr, jk, p, f, o in rows:
        k = cls(g, nm)
        if not k or not o:
            continue
        band = "〜9.9倍" if o < 10 else "10倍〜"
        for who, name in (("調教師", tr), ("騎手", jk)):
            if not name:
                continue
            a = agg[(who, name, k, band)][per(d)]; a[0] += f <= 3; a[1] += e[min(p, 16)]; a[2] += 1
    out = []
    for (who, name, k, band), v in agg.items():
        if min(x[1] for x in v) < 2:
            continue
        ae = [x[0] / x[1] for x in v]
        if all(y >= 1.15 for y in ae):
            out.append(dict(who=who, name=name, cls=k, band=band, ae=[round(y, 2) for y in ae], n=[x[2] for x in v]))
    out.sort(key=lambda x: -min(x["ae"]))
    (ROOT / "data" / "knowledge" / "conn_class_scan.json").write_text(json.dumps(
        {"_meta": "調教師・騎手×クラス（重賞/OP）×単勝の倍率帯（tools/conn_class_scan.py）。3期とも3着内A/E≥1.15・各期の見込み2以上", "items": out},
        ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# 調教師・騎手 × クラス × 単勝の倍率帯（tools/conn_class_scan.py, 2026-11-08）", "",
         "3期（2021-23 / 2024 / 2025-26/9）とも3着内A/E≥1.15・各期の見込み2以上。", "",
         "| 調教師/騎手 | 名前 | クラス | 単勝 | A/E（3期） | 走数（3期） |", "|---|---|---|---|---|---|"]
    L += [f"| {x['who']} | {x['name']} | {x['cls']} | {x['band']} | {'/'.join(map(str, x['ae']))} | {'/'.join(map(str, x['n']))} |" for x in out]
    (ROOT / "docs" / "analysis" / "conn_class_scan.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
