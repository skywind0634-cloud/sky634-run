"""JRA公式サイトの実ページ(tests/fixtures/jra)を使ったパーサーのテスト."""
from pathlib import Path

from keiba.scraper import jra

FX = Path(__file__).parent / "fixtures" / "jra"


def read(name):
    return (FX / name).read_text(encoding="utf-8")


def test_parse_result():
    race, res = jra.parse_result(read("result.html"), "pw01sde1006202604081120260926/C5")
    assert race["race_id"] == "202606040811" and race["course"] == "中山" and race["date"] == "2026-09-26"
    assert race["name"] == "秋風ステークス" and race["grade"] == "3勝"
    assert (race["surface"], race["distance"], race["going"], race["weather"]) == ("芝", 1600, "重", "雨")
    assert len(race["laps"]) == 8 and race["pace_type"]
    assert race["payouts"]["単勝"] == [["2", 340]] and race["payouts"]["3連複"] == [["2-3-8", 1770]]
    assert len(res) == 14
    w = res[0]
    assert (w["horse_id"], w["finish"], w["number"], w["gate"]) == ("2023101449", 1, 2, 2)
    assert (w["jockey"], w["trainer"], w["time_sec"], w["last3f"]) == ("津村明秀", "斉藤崇史", 96.1, 35.8)
    assert w["passing"] == "2-3-3" and w["body_weight_diff"] == -6 and w["odds"] == 3.4
    assert res[-1]["sex"] == "セ"


def test_parse_horse():
    h = jra.parse_horse(read("horse.html"), "pw01dud102023101449/47")
    assert h["horse_id"] == "2023101449" and h["birth"] == "2023-02-23"
    assert h["pedigree"] == {"S": "リアルスティール", "D": "サウンドルチア", "DS": "スクリーンヒーロー", "DD": "サウンドリアーナ"}


def test_parse_shutuba_with_recent_runs():
    c = jra.parse_shutuba(read("shutuba.html"), "pw01dde1006202604091120260927/39")
    assert c["race_id"] == "202606040911" and c["grade"] == "G1" and c["distance"] == 1200
    assert len(c["entries"]) == 16
    e = c["entries"][0]
    assert (e["name"], e["sire"], e["dam"], e["damsire"]) == ("レッドモンレーヴ", "ロードカナロア", "ラストグルーヴ", "ディープインパクト")
    assert e["odds"] == 52.3 and e["jockey"] == "酒井学" and e["weight"] == 58.0
    r = e["recent"][0]
    assert r["race_id"] == "202609040211" and r["grade"] == "G2" and r["finish"] == 16
    assert r["distance"] == 1200 and r["surface"] == "芝" and r["passing"] == "16-16" and r["time_sec"] == 69.5


def test_month_cnames():
    m = jra.month_cnames(read("search.html"))
    assert m["202409"] == "pw01skl10202409/23" and len(m) > 60


def test_extend_pedigree_from_knowledge():
    from keiba.pipeline import _extend_pedigree
    ped = _extend_pedigree({"S": "リアルスティール", "DS": "スクリーンヒーロー"})
    assert ped["SS"] == "ディープインパクト" and ped["SSS"] == "サンデーサイレンス"
    assert ped["DSS"] == "グラスワンダー"
