# -*- coding: utf-8 -*-
"""验证 R3 门控的序列风险：F窗口(2014-06~2015-05)市场等权+215%但原版-43%。
对比 R3 开/关 下原版与h5s9的收益，以及各自的R3停手段数。"""
import importlib.util, os
spec = importlib.util.spec_from_file_location('hbe', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hoshi_backtest_exp.py'))
hbe = importlib.util.module_from_spec(spec); spec.loader.exec_module(hbe)
hbe._log=lambda *a,**k:None; hbe.DEBUG=False; hbe.TOTAL_CAPITAL=500000.0
code_bars,names,all_dates = hbe.load_data(os.path.join(os.path.dirname(os.path.abspath(__file__)),'hoshi_csv_long'))
W = [('F 2014-06~2015-05','2014-06-01','2015-05-31'),
     ('A 2014-12~2016-11','2014-12-01','2016-11-30'),
     ('C 2018-10~2019-09','2018-10-01','2019-09-30')]
for tag,s,e in W:
    for label,score,hard,r3 in [('原版 R3开',8.0,15,True),('原版 R3关',8.0,15,False),
                                ('h5s9 R3开',9.0,5,True),('h5s9 R3关',9.0,5,False)]:
        hbe.MAX_BUY_PER_DAY=0; hbe.LOSS_START_DAY=15; hbe.LOSS_HARD_START_DAY=hard
        hbe.MIN_SCORE=score; hbe.MAX_SLOTS=10; hbe.EXIT_MODE='AUTO'; hbe.USE_R3_GATE=r3
        r = hbe.run_backtest(code_bars,names,all_dates,start=s,end=e)
        ret = (r['final_capital']-500000.0)/500000.0*100
        print('%-14s %-12s 收益%+9.2f%% 笔数=%3d R3停手=%d段' % (tag,label,ret,len(r['closed']),len(r['stops'])), flush=True)
print('完成')
