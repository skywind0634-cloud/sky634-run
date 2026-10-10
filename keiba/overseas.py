"""JRAが発売する海外レースの買い目（日本のオッズの偏りを取る）.

考え方（2026年凱旋門賞の反省を反映）:
- 勝率は海外の市場（ブックメーカー等）のオッズから出す（控除分を除いて合計1に正規化）。
- 期待値 = 海外の勝率 × JRAの単勝オッズ。日本のお金は日本馬に集中しやすく、外国の有力馬が割安になる。
- 軸は「海外の勝率が最上位」の馬（期待値が1以上なら）。期待値が一番高い馬を軸にしない。
- 期待値1.3以上の馬は単勝・複勝、軸から期待値1.2以上の馬へ馬連。
- 海外の評価で勝率3%未満なのにJRAで1〜3番人気の馬は「危険な人気馬」。

入力: data/overseas/<name>.json
  {"race": "...", "runners": [{"num": JRA馬番, "name": "...", "global_odds": 6.0, "jra_odds": 12.4, "jra_pop": 5, "jp": false}, ...]}
  global_odds は小数オッズ（10-1 なら 11.0）。
"""
from __future__ import annotations

import json
from pathlib import Path

EV_TANPUKU = 1.3
EV_PARTNER = 1.2
MAX_PARTNERS = 5


def analyze(race: dict) -> dict:
    rs = [r for r in race["runners"] if r.get("global_odds") and r.get("jra_odds")]
    z = sum(1 / r["global_odds"] for r in rs)
    for r in rs:
        r["p"] = 1 / r["global_odds"] / z
        r["ev"] = r["p"] * r["jra_odds"]
    rs.sort(key=lambda r: -r["p"])
    axis = next((r for r in rs if r["ev"] >= 1.0), None)
    value = [r for r in rs if r["ev"] >= EV_TANPUKU]
    partners = [r for r in sorted(rs, key=lambda r: -r["ev"]) if r["ev"] >= EV_PARTNER and r is not axis][:MAX_PARTNERS]
    danger = [r for r in rs if (r.get("jra_pop") or 99) <= 3 and r["p"] < 0.03]
    tickets = []
    for r in value[:3]:
        tickets += [("単勝", (r["num"],)), ("複勝", (r["num"],))]
    if axis:
        tickets += [("馬連", tuple(sorted((axis["num"], r["num"])))) for r in partners]
    return {"runners": rs, "axis": axis, "value": value, "partners": partners, "danger": danger,
            "tickets": list(dict.fromkeys(tickets))[:10]}


def text(race: dict) -> str:
    a = analyze(race)
    L = [f"### {race.get('race', '')}", "", "| 馬番 | 馬名 | 海外の勝率 | JRA単勝 | 期待値 |", "|--:|---|--:|--:|--:|"]
    for r in a["runners"]:
        L.append(f"| {r['num']} | {r['name']}{'（日本）' if r.get('jp') else ''} | {r['p']:.1%} | {r['jra_odds']} | {r['ev']:.2f} |")
    if a["axis"]:
        L.append(f"\n- 軸（海外の勝率が最上位で期待値1以上）: {a['axis']['num']} {a['axis']['name']}")
    if a["danger"]:
        L.append("- 危険な人気馬: " + "、".join(f"{r['num']} {r['name']}（JRA{r.get('jra_pop')}人気・海外の勝率{r['p']:.1%}）" for r in a["danger"]))
    L.append("- 買い目: " + " / ".join(f"{k} {'-'.join(map(str, h))}" for k, h in a["tickets"]))
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    print(text(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))))
