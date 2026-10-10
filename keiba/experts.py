"""専門家（血統予想家）の見解の台帳と、実績データでの裏付け確認.

data/knowledge/expert_notes.json に「誰が・どの種牡馬/系統について・どの条件で・プラスかマイナスか」を出典付きで登録する。
コラム本文は転載せず、主張の要点のみを記録する。

各見解は、取り込み済みの実績で『その条件で、その父（系統）が自身の平均×全馬共通の条件効果よりどれだけ走っているか（父内z）』を
計算して検証する。ただし血統にはデータだけでは見えない本質（母数が少ない条件を含む）もあるため、有意でない見解も捨てない:
- 見解そのものを「事前の重み」として持つ（出典の信頼度 CREDIBILITY × 見解の向き）
- 実績の重み（強さ × 時期の安定度）と、出走数に応じて滑らかに合成する（n/(n+N_HALF)。データが少ないほど見解寄り）
- データがはっきり逆を示す場合だけ、データの向きが勝つ
条件に落とし込めない定性的な見解（気性・成長力など。condition に "qualitative": true）は、根拠欄に表示するだけ。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict

from . import knowledge as K
from .analysis import Cell
from .config import KNOWLEDGE_DIR, ROOT, distance_band, going_group, write_atomic

NOTES_PATH = KNOWLEDGE_DIR / "expert_notes.json"
CHECK_PATH = KNOWLEDGE_DIR / "expert_checks.json"

# 出典の信頼度（事前の重みの大きさ, 0〜1）。author の文字列に含まれる名前で判定。見解ごとに "credibility" で上書き可
CREDIBILITY = {"白井": 0.8, "亀谷": 0.8, "望田": 0.75, "水上": 0.6, "坂上": 0.6, "平出": 0.6, "JRA": 0.5,
               "ブログ": 0.35, "備忘録": 0.35, "AI": 0.3}
DEFAULT_CRED = 0.45
N_HALF = 150    # 該当走がこの数でデータと見解が半々
# データが大量にあっても見解を残す最低限の割合。白井寿昭氏（調教師として）・亀谷敬正氏（馬券師として）は
# 血統で実績を上げた2人で、データで見えない本質を捉えている可能性があるため、見解の比重を最低25%残す
PRIOR_FLOOR = {"白井": 0.25, "亀谷": 0.25, "望田": 0.15}   # 望田潤氏: 俯瞰的な見方・データで見えない血統のクセ
DEFAULT_FLOOR = 0.05


def prior_floor(note: dict) -> float:
    a = note.get("author", "")
    return max((v for k, v in PRIOR_FLOOR.items() if k in a), default=DEFAULT_FLOOR)


def credibility(note: dict) -> float:
    if "credibility" in note:
        return float(note["credibility"])
    a = note.get("author", "")
    return max((v for k, v in CREDIBILITY.items() if k in a), default=DEFAULT_CRED)


COND_KEYS = ("surface", "band", "going", "course", "straight_cat", "slope", "turn", "dchg", "pace", "sex",
             "age_min", "age_max", "distance_min", "distance_max", "style")


def load_notes() -> list[dict]:
    if not NOTES_PATH.exists():
        return []
    return json.loads(NOTES_PATH.read_text(encoding="utf-8")).get("notes", [])


def load_checks() -> dict:
    if not CHECK_PATH.exists():
        return {}
    try:
        return json.loads(CHECK_PATH.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def matches(cond: dict, ctx: dict) -> bool:
    """条件 cond に文脈 ctx（レース条件＋馬の属性）が合致するか."""
    for k, v in cond.items():
        if k == "qualitative":   # 定性的な見解の印（条件ではない）
            continue
        if k == "age_min":
            if (ctx.get("age") or 0) < v:
                return False
        elif k == "age_max":
            if (ctx.get("age") or 99) > v:
                return False
        elif k == "distance_min":
            if (ctx.get("distance") or 0) < v:
                return False
        elif k == "distance_max":
            if (ctx.get("distance") or 99999) > v:
                return False
        elif k == "gate_max":   # 枠（例: 内枠 → gate_max: 3）
            if not ctx.get("gate") or ctx["gate"] > v:
                return False
        elif k == "gate_min":
            if not ctx.get("gate") or ctx["gate"] < v:
                return False
        elif k == "pop_max":   # 人気の条件（例: 1〜3番人気で消し → pop_max: 3）
            if not ctx.get("popularity") or ctx["popularity"] > v:
                return False
        elif k == "pop_min":
            if not ctx.get("popularity") or ctx["popularity"] < v:
                return False
        elif isinstance(v, list):
            if ctx.get(k) not in v:
                return False
        elif ctx.get(k) != v:
            return False
    return True


def subject_match(note: dict, sire: str | None, sire_line: str | None, damsire: str | None,
                  damsire_line: str | None) -> bool:
    if note.get("sire") and note["sire"] != sire:
        return False
    if note.get("sire_line") and note["sire_line"] not in K.line_ancestry(sire_line):
        return False
    if note.get("damsire") and note["damsire"] != damsire:
        return False
    if note.get("damsire_line") and note["damsire_line"] not in K.line_ancestry(damsire_line):
        return False
    return True


def row_ctx(r: dict) -> dict:
    a = K.course_attrs(r["course"], r["surface"], r["distance"])
    return {"surface": r["surface"], "band": distance_band(r["distance"] or 0), "going": going_group(r["going"]),
            "course": r["course"], "straight_cat": a["straight_cat"], "slope": a["slope"], "turn": a["turn"],
            "dchg": r.get("dchg"), "pace": r.get("pace_type"), "sex": r.get("sex"), "age": r.get("age"),
            "distance": r.get("distance"), "style": r.get("style"), "popularity": r.get("popularity"),
            "interval": r.get("interval"), "grade": r.get("grade"), "gate": r.get("gate")}


def verify(conn) -> dict:
    """全見解を実績で検証 → expert_checks.json と docs/analysis/expert_check.md."""
    from .deep import load_rows
    rows = load_rows(conn)
    notes = load_notes()
    out = {}
    by_subject = defaultdict(list)
    for r in rows:
        by_subject[(r["sire"], r["sire_line"], r["damsire"], r["damsire_line"])].append(r)
    L = ["# 専門家見解の検証（自動生成）", "",
         "各見解を取り込み済みの実績で検証。父内z = その条件での複勝率が、同じ父（系統）の全体の複勝率 × "
         "**全馬に共通するその条件の上下（例: 4歳以上は全馬で複勝率が約0.9倍）** から期待される値からどれだけ離れているか。",
         "裏付け＝主張と同じ向きに |z|≥2。コラム本文は転載せず、要点と出典のみ。",
         "**時期によるブレ**: 年ごとの父内z（その年の同じ父の平均と比較）と、直近1年のz を出し、"
         "向きが揃っている年の割合（一貫性）と直近の向きから『安定度』(0〜1) を算出。予想への反映は 強さ(|z|/3, 上限1) × 安定度。", "",
         "**データで見えないものも捨てない**: 見解は出典の信頼度に応じた事前の重みを持ち、該当走が少ないほど見解寄り、"
         f"多いほどデータ寄りに合成する（該当{N_HALF}走で半々）。データがはっきり逆なら実績の向きが勝つ。", "",
         "| # | 出典 | 対象 | 条件 | 主張 | 該当走 | 複勝率(条件/全体) | 全馬の条件補正 | 父内z | 年別z | 直近1年z | 安定度 | 反映(見解→合成) | 判定 |",
         "|--:|---|---|---|:-:|--:|---|--:|--:|---|--:|--:|---|---|"]
    last = max((r["date"] for r in rows), default="2000-01-01")
    recent_cut = f"{int(last[:4]) - 1}{last[4:]}"

    def zval(c, a, adj=1.0):
        p = min(0.95, a.top3_rate * adj)
        return (c.t - c.n * p) / math.sqrt(c.n * p * (1 - p)) if c.n and 0 < p < 1 else 0.0

    ctxs = [(r, row_ctx(r)) for r in rows]

    def pop_adj(cond):
        """全馬で見た、その条件の複勝率 / 全体の複勝率（全期間・年別・直近）."""
        pa, pc = Cell(), Cell()
        ypa, ypc = defaultdict(Cell), defaultdict(Cell)
        rpa, rpc = Cell(), Cell()
        for r, cx in ctxs:
            hit = matches(cond, cx)
            y, rec = r["date"][:4], r["date"] >= recent_cut
            for a, c in ((pa, pc), (ypa[y], ypc[y])) + (((rpa, rpc),) if rec else ()):
                a.add(r["finish"], r["odds"])
                if hit:
                    c.add(r["finish"], r["odds"])
        f = lambda a, c: (c.top3_rate / a.top3_rate) if c.n >= 30 and a.top3_rate else 1.0
        return f(pa, pc), {y: f(ypa[y], ypc[y]) for y in ypa}, f(rpa, rpc)

    for i, n in enumerate(notes):
        adj, yadj, radj = pop_adj(n.get("condition", {}))
        allc, cc = Cell(), Cell()
        ya, yc = defaultdict(Cell), defaultdict(Cell)
        ra, rc = Cell(), Cell()
        for key, rs in by_subject.items():
            if not subject_match(n, *key):
                continue
            for r in rs:
                y = r["date"][:4]
                allc.add(r["finish"], r["odds"])
                ya[y].add(r["finish"], r["odds"])
                rec = r["date"] >= recent_cut
                if rec:
                    ra.add(r["finish"], r["odds"])
                if matches(n.get("condition", {}), row_ctx(r)):
                    cc.add(r["finish"], r["odds"])
                    yc[y].add(r["finish"], r["odds"])
                    if rec:
                        rc.add(r["finish"], r["odds"])
        p0 = allc.top3_rate
        z = zval(cc, allc, adj)
        sign = 1 if n.get("direction", "+") == "+" else -1
        verdict = "裏付けあり" if z * sign >= 2 else ("逆の傾向" if z * sign <= -2 else "データでは確認できず")
        if cc.n < 30:
            verdict = "データ不足"
        by_year = {y: (round(zval(yc[y], ya[y], yadj.get(y, 1.0)), 2), yc[y].n) for y in sorted(yc) if yc[y].n >= 15}
        zr = zval(rc, ra, radj) if rc.n >= 15 else None
        dz = 1 if z > 0 else -1
        agree = [1 if v[0] * dz > 0 else 0 for v in by_year.values()]
        consistency = sum(agree) / len(agree) if agree else 0.5
        recent_term = 0.4 if zr is None else (1.0 if zr * dz >= 1 else 0.6 if zr * dz > 0 else 0.0)
        stability = round(0.5 * consistency + 0.5 * recent_term, 2)
        if verdict in ("裏付けあり", "逆の傾向") and zr is not None and zr * dz <= -1:
            verdict += "（直近は反転）"
        nid = n.get("id") or f"note{i}"
        # 見解（事前）とデータの合成
        prior = sign * credibility(n) * 0.5                     # 見解だけの場合の強さ（最大 ±0.4）
        data_w = dz * min(abs(z) / 3, 1.0) * stability if cc.n >= 10 else 0.0
        r = min(cc.n / (cc.n + N_HALF), 1 - prior_floor(n))
        weight = (1 - r) * prior + r * data_w
        if n.get("condition", {}).get("qualitative"):
            weight, verdict = 0.0, "定性的な見解（表示のみ）"
        elif verdict in ("データでは確認できず", "データ不足"):
            verdict += "→見解の向きで反映" if weight * sign > 0 else "→データ寄りで反映"
        out[nid] = {"z": round(z, 2), "n": cc.n, "prior": round(prior, 3), "data_weight": round(data_w, 3), "data_share": round(r, 2), "rate": round(cc.top3_rate, 4), "base": round(p0, 4), "pop_adj": round(adj, 3),
                    "verdict": verdict, "by_year": by_year, "recent_z": None if zr is None else round(zr, 2),
                    "recent_n": rc.n, "stability": stability,
                    "weight": round(weight, 3)}
        subj = n.get("sire") or n.get("sire_line") or ""
        if n.get("damsire") or n.get("damsire_line"):
            subj += f" × 母父{n.get('damsire') or n.get('damsire_line')}"
        cond = "・".join(f"{k}={v}" for k, v in n.get("condition", {}).items())
        L.append(f"| {i+1} | [{n.get('author','')}]({n.get('url','')}) | {subj} | {cond} | {n.get('direction','+')} | "
                 f"{cc.n} | {cc.top3_rate:.1%}/{p0:.1%} | ×{adj:.2f} | {z:+.1f} | "
                 f"{' '.join(f'{y[2:]}:{v[0]:+.1f}' for y, v in by_year.items()) or '-'} | "
                 f"{'-' if zr is None else f'{zr:+.1f}'} | {stability:.2f} | {prior:+.2f}→{weight:+.2f} | {verdict} |")
    write_atomic(CHECK_PATH, json.dumps(out, ensure_ascii=False, indent=1))
    (ROOT / "docs" / "analysis").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "analysis" / "expert_check.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def applicable(card: dict, entry: dict, sire, sire_line, damsire, damsire_line, hist: list) -> list[tuple[dict, dict]]:
    """この馬・このレースに当てはまる見解と、その検証結果."""
    notes = load_notes()
    if not notes:
        return []
    checks = load_checks()
    a = K.course_attrs(card.get("course"), card.get("surface"), card.get("distance"))
    prev_d = hist[0].get("distance") if hist else None
    dchg = ("延長" if prev_d and card.get("distance") and card["distance"] - prev_d >= 100 else
            "短縮" if prev_d and card.get("distance") and card["distance"] - prev_d <= -100 else "同" if prev_d else "初")
    ctx = {"surface": card.get("surface"), "band": distance_band(card.get("distance") or 1600),
           "going": going_group(card.get("going")), "course": card.get("course"), "straight_cat": a["straight_cat"],
           "slope": a["slope"], "turn": a["turn"], "dchg": dchg, "pace": card.get("expected_pace"),
           "sex": entry.get("sex"), "age": entry.get("age"), "distance": card.get("distance"),
           "popularity": entry.get("popularity"), "grade": card.get("grade"), "gate": entry.get("gate")}
    out = []
    for i, n in enumerate(notes):
        if subject_match(n, sire, sire_line, damsire, damsire_line) and matches(n.get("condition", {}), ctx):
            out.append((n, checks.get(n.get("id") or f"note{i}", {})))
    return out
