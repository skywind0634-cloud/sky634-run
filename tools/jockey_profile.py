"""騎手の腕前と乗り方の癖（2026-11-08 ユーザー「騎手のうまさでレース結果は変わる。騎手ごとの逃げ・先行・差し・追い込み、乗り替わり初戦も、芝ダ別に分析しろ」）.
騎手×芝ダごとに、その年より前の2年間の 3着内A/E（腕前）と 1角で前25%にいた割合（先行率）を年ごとに作る（未来を見ない）.
出力: data/knowledge/jockey_profile.json {年: {騎手|芝ダ: [A/E, 先行率, 騎乗数]}}（keiba/multi_angles.py の騎手の切り口と tools/multi_angle_scan.py が使う）
使い方: python3 tools/jockey_profile.py"""
import json, sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIN_RIDES = 60


def main():
    c = sqlite3.connect(ROOT / "data" / "keiba.db")
    home = defaultdict(lambda: defaultdict(int))
    for y, jk, co, cnt in c.execute("""select substr(r.date,1,4),x.jockey,r.course,count(*) from results x join races r on r.race_id=x.race_id
                                      where x.jockey is not null group by 1,2,3"""):
        home[(int(y), jk)]["東" if co in ("東京", "中山", "新潟", "福島", "札幌", "函館") else "西"] += cnt
    rows = c.execute("""select substr(r.date,1,4),r.surface,x.jockey,x.popularity,x.finish,x.passing,
        (select count(*) from results y where y.race_id=r.race_id),x.horse_id from results x join races r on r.race_id=x.race_id
        where x.finish>0 and x.popularity>0 and r.surface in ('芝','ダ') order by r.date""").fetchall()
    base = defaultdict(lambda: [0, 0])
    for y, su, jk, p, f, pas, n, hid in rows:
        k = (su, min(p, 16)); base[k][0] += 1; base[k][1] += f <= 3
    e = {k: v[1] / v[0] for k, v in base.items()}
    by = defaultdict(lambda: [0, 0.0, 0, 0, 0.0, 0])  # (year, jockey, surf) -> obs, exp, front, known, drop_sum, drop_n
    hist = defaultdict(list)
    for y, su, jk, p, f, pas, n, hid in rows:
        try:
            pos = int(str(pas).split("-")[0]) / max(n, 1)
        except (ValueError, TypeError):
            pos = None
        prior = hist[hid][-3:]
        if pos is not None:
            hist[hid].append(pos)
        if not jk:
            continue
        a = by[(int(y), jk, su)]; a[0] += f <= 3; a[1] += e[(su, min(p, 16))]
        if pos is not None:
            a[3] += 1; a[2] += pos <= 0.25
            if prior:
                a[4] += pos - sum(prior) / len(prior); a[5] += 1
    years = sorted({k[0] for k in by})
    out = {}
    for Y in range(years[0] + 1, years[-1] + 2):
        prof = {}
        acc = defaultdict(lambda: [0, 0.0, 0, 0, 0.0, 0])
        for (y, jk, su), a in by.items():
            if Y - 2 <= y <= Y - 1:
                b = acc[(jk, su)]
                for i in range(6):
                    b[i] += a[i]
        for (jk, su), b in acc.items():
            if b[1] and b[3] >= MIN_RIDES:
                # [腕前A/E, 先行率, 騎乗数, 下げ度（その騎手が乗ると馬の近3走平均より1角で何%後ろか）]
                prof[f"{jk}|{su}"] = [round(b[0] / b[1], 3), round(b[2] / b[3], 3), b[3], round(b[4] / b[5], 3) if b[5] else 0.0]
        # 騎手の本拠（前2年で騎乗の6割以上が東か西）: "@騎手" → "東"/"西"
        for (y, jk), hv in list(home.items()):
            pass
        hh = defaultdict(lambda: [0, 0])
        for (y, jk), hv in home.items():
            if Y - 2 <= y <= Y - 1:
                hh[jk][0] += hv["東"]; hh[jk][1] += hv["西"]
        for jk, (a, b) in hh.items():
            if a + b >= 100 and max(a, b) / (a + b) >= 0.6:
                prof[f"@{jk}"] = "東" if a > b else "西"
        out[str(Y)] = prof
    (ROOT / "data" / "knowledge" / "jockey_profile.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print({k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()
