"""5代血統表（ped-data ブランチの data/ped5_full.json）から、予想で使う祖先の有無だけを抜き出した小さな表を作る（2026-10-12）.
出力: data/knowledge/ped5_flags.json  {horse_id: [フラグ...]}（フラグのある馬だけ）
使い方: python3 tools/ped5_flags.py <ped5_full.json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS = {
    "サクラバクシンオー": {"サクラバクシンオー"},
    "カロ系": {"Caro", "カロ", "Cozzene", "コジーン", "Fortino", "フォルティノ"},
    "トニービン": {"Tony Bin", "トニービン"},
    "ノーザンテースト": {"Northern Taste", "ノーザンテースト"},
    "リボー": {"Ribot", "リボー"},
    "サドラーズウェルズ/ミルリーフ": {"Sadler's Wells", "サドラーズウェルズ", "Mill Reef", "ミルリーフ"},
    "ヌレイエフ": {"Nureyev", "ヌレイエフ"},
    "インリアリティ": {"In Reality", "インリアリティ"},
    "タイキシャトル": {"タイキシャトル"},
    "Chief's Crown": {"Chief's Crown", "チーフズクラウン"},
    "Affirmed": {"Affirmed", "アファームド"},
    # 2026-10-26 坂上氏の血統査定の「血の特徴」を検証して効いたもの（tools/ancestor_traits.py）
    "Storm Cat": {"Storm Cat", "ストームキャット"},
    "Seattle Slew": {"Seattle Slew", "シアトルスルー"},
    "Princequillo": {"Princequillo", "プリンスキロ"},
}


try:
    TRAIT_ENTS = sorted({t["entity"] for t in json.loads((ROOT / "data" / "knowledge" / "blood_traits.json").read_text(encoding="utf-8"))["traits"]})
except (OSError, ValueError, KeyError):
    TRAIT_ENTS = []


def main(path):
    P = json.loads(Path(path).read_text(encoding="utf-8"))
    H, pos = P["horses"], P["pos"]
    out = {}
    for hid, names in H.items():
        s = set(n for n in names if n)
        f = [k for k, v in FLAGS.items() if s & v]
        ss = [(len(p), p[0]) for p, a in zip(pos, names) if a == "サンデーサイレンス"]
        sg = [g for g, side in ss if side == "S"]; dg = [g for g, side in ss if side == "D"]
        if sg and dg and min(sg) <= 3 and min(dg) <= 3:
            f.append("サンデー3×3以内")
        # コラムの「血×条件」で裏付けのあった血（data/knowledge/blood_traits.json, tools/trait_check.py）→「血:名前」
        gen = [len(p) for p in pos]
        for ent in TRAIT_ENTS:
            if ent.startswith("父="):
                if names and names[0] == ent[2:]:
                    f.append("血:" + ent)
                continue
            b = ent.split("（")[0]
            gs = [g for g, a in zip(gen, names) if a == b]
            if gs and (ent == b or (ent.endswith("（3代以内）") and min(gs) <= 3) or (ent.endswith("（クロス）") and len(gs) >= 2)):
                f.append("血:" + ent)
        if f:
            out[hid] = f
    (ROOT / "data" / "knowledge" / "ped5_flags.json").write_text(json.dumps({"_meta": "tools/ped5_flags.py", "flags": out}, ensure_ascii=False), encoding="utf-8")
    print(len(H), "頭中", len(out), "頭にフラグ")


if __name__ == "__main__":
    main(sys.argv[1])
