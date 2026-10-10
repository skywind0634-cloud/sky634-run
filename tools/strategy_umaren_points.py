import sys; sys.argv=["x","none"]
exec(open("tools/strategy_combo.py").read())
for n in (3,4,5,6,8):
    show(f"馬連EV1.2/2000円〜/妙味馬含む 14頭以下 {n}点", gen("馬連", ev=1.2, need_value=True, maxN=14, per_race=n))
for n in (4,5,6):
    show(f"馬連EV1.2/2000円〜/妙味馬含む 全 {n}点", gen("馬連", ev=1.2, need_value=True, per_race=n))
show("単複＋馬連5点(14頭以下)", both(tanpuku(), gen("馬連", ev=1.2, need_value=True, maxN=14, per_race=5)))
