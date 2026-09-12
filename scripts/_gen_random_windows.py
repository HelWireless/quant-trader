# -*- coding: utf-8 -*-
import random, datetime
# 固定种子可复现
random.seed(20260903)
# 可选开始月: 2010-01 .. 2025-01 (2025-01开始+最长5年=2030-01会截断到2026-09)
# 为让5年窗口也能完整, 开始月上限设为 2021-08 (2021-08+5年=2026-08)
def add_months(y,m,n):
    tot=m-1+n; return (y+tot//12, tot%12+1)
start_options=[]  # (year,month) 从 2010-01 起
y,m=2010,1
while (y,m) <= (2021,8):
    start_options.append((y,m)); y,m=add_months(y,m,1)
print("可选开始月数(2010-01..2021-08):", len(start_options))
wins=[]
for i in range(5):
    sy,sm=random.choice(start_options)
    dur=random.randint(12,60)  # 月
    ey,em=add_months(sy,sm,dur-1)
    # 截断到 2026-08
    if (ey,em)>(2026,8): ey,em=2026,8
    wins.append((sy,sm,dur,ey,em))
for i,(sy,sm,dur,ey,em) in enumerate(wins,1):
    s="%04d-%02d-01"%(sy,sm)
    e="%04d-%02d-01"%add_months(ey,em,0)
    # end用当月最后一天近似即可,回测会按实际交易日
    print("窗口%d: %04d-%02d 起, 时长%d月 -> %04d-%02d  (%s ~ %s)"%(i,sy,sm,dur,ey,em,s,e))
