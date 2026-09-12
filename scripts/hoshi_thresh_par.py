# -*- coding: utf-8 -*-
"""硬止损阈值对照 —— 多进程并行跑批（LOSS_HARD_PCT: -6.0% vs -8.2%）

基线 = 方案 B：评分9 + LOSS_START_DAY=15 + LOSS_HARD_START_DAY=5 + R3关 + 广度20
任务：组1×t6 + 组2×t6 + 锚点复核(组1×t8 前2窗, 组2×t8 前2窗)

用法: python hoshi_thresh_par.py [workers]     workers 默认 5
输出: hoshi_thr<group>_<tag>.csv   （每 (group,tag) 一个文件，支持断点续跑）

锚点（hoshi_abl1_b.csv / hoshi_abl2_b.csv，同为方案B+默认-8.2%）：
  t8 结果必须与 abl*_b.csv 逐位相同，否则框架有问题。
"""
import csv
import importlib.util
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
WORKERS = int(sys.argv[1]) if len(sys.argv) > 1 else 5

GLOBAL_DEFAULTS = dict(MAX_BUY_PER_DAY=0, LOSS_START_DAY=15, MAX_SLOTS=10, EXIT_MODE='AUTO',
                       ADAPTIVE_SCORE=False, ADAPTIVE_STOP=False, RS_FILTER=False,
                       SCORE_TIER_SIZING=False, SCORE_TIER_ADAPTIVE=False,
                       USE_R3_GATE=True, BREADTH_THRESH=20.0, USE_BREADTH_GATE=True,
                       MIN_SCORE=8.0, LOSS_HARD_START_DAY=15, LOSS_HARD_PCT=-8.2)
SCHEME_B = dict(MIN_SCORE=9.0, LOSS_HARD_START_DAY=5, SCORE_TIER_SIZING=False,
                USE_R3_GATE=False, BREADTH_THRESH=20.0)
THRESH = {'t6': -6.0, 't8': -8.2}

_D = {}


def _init():
    """每个 worker 进程各加载一次数据（进程内常驻复用）。"""
    spec = importlib.util.spec_from_file_location(
        'hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
    hbe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hbe)
    hbe._log = lambda *a, **k: None
    hbe.DEBUG = False
    hbe.TOTAL_CAPITAL = 500000.0
    hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
    cb, nm, ad = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))
    _D['hbe'] = hbe
    _D['cb'] = cb
    _D['nm'] = nm
    _D['ad'] = ad


def _work(task):
    group, tag, s, e, m = task
    hbe = _D['hbe']
    for k, v in GLOBAL_DEFAULTS.items():
        setattr(hbe, k, v)
    for k, v in SCHEME_B.items():
        setattr(hbe, k, v)
    hbe.LOSS_HARD_PCT = THRESH[tag]
    assert hbe.LOSS_HARD_PCT == THRESH[tag]
    assert hbe.USE_R3_GATE is False and hbe.MIN_SCORE == 9.0 and hbe.LOSS_HARD_START_DAY == 5
    r = hbe.run_backtest(_D['cb'], _D['nm'], _D['ad'], start=s, end=e)
    ret = (r['final_capital'] - 500000.0) / 500000.0 * 100.0
    return (group, tag, s, e, m, ret, len(r['closed']))


def _read_done():
    done = {}
    for g in ('1', '2'):
        for tag in ('t6', 't8'):
            p = os.path.join(HERE, 'hoshi_thr%s_%s.csv' % (g, tag))
            d = {}
            if os.path.exists(p):
                with open(p, encoding='utf-8') as f:
                    for r in csv.DictReader(f):
                        if r.get('start'):
                            d[(r['start'], r['end'])] = (r['pct'], r.get('trades', ''))
            done[(g, tag)] = d
    return done


def _write_done(done, windows):
    for g in ('1', '2'):
        for tag in ('t6', 't8'):
            d = done[(g, tag)]
            if not d:
                continue
            p = os.path.join(HERE, 'hoshi_thr%s_%s.csv' % (g, tag))
            with open(p, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['start', 'end', 'len_months', 'pct', 'trades'])
                for (s, e, m) in windows[g]:
                    if (s, e) in d:
                        w.writerow([s, e, m, d[(s, e)][0], d[(s, e)][1]])


if __name__ == '__main__':
    windows = {}
    for g, fn in (('1', 'hoshi_time_corr_windows.csv'), ('2', 'hoshi_oos2_windows.csv')):
        rows = []
        with open(os.path.join(HERE, fn), encoding='utf-8') as f:
            for r in csv.DictReader(f):
                rows.append((r['start'], r['end'], int(r['len_months'])))
        windows[g] = rows
        print('组%s: %d 窗' % (g, len(rows)), flush=True)

    tasks = []
    for g in ('1', '2'):
        for (s, e, m) in windows[g]:
            tasks.append((g, 't6', s, e, m))
    # 锚点复核：前后各取 2 窗（与 abl*_b.csv 对拍）
    for g in ('1', '2'):
        for (s, e, m) in (windows[g][:2] + windows[g][-2:]):
            tasks.append((g, 't8', s, e, m))

    done = _read_done()
    todo = [t for t in tasks if (t[2], t[3]) not in done[(t[0], t[1])]]
    # 长窗口优先提交（LPT 调度，减少尾部等待）
    todo.sort(key=lambda t: -t[4])
    print('任务 %d 项：已完成 %d，待跑 %d，并行度 %d'
          % (len(tasks), len(tasks) - len(todo), len(todo), WORKERS), flush=True)

    if todo:
        n_done = 0
        with ProcessPoolExecutor(max_workers=WORKERS, initializer=_init) as ex:
            futs = {ex.submit(_work, t): t for t in todo}
            for fu in as_completed(futs):
                g, tag, s, e, m, ret, nt = fu.result()
                done[(g, tag)][(s, e)] = ('%.4f' % ret, str(nt))
                n_done += 1
                print('[%3d/%d] 组%s %s(%+.1f%%) %s~%s (%2d月) %+9.4f%% 笔%3d'
                      % (n_done, len(todo), g, tag.upper(), THRESH[tag], s[:7], e[:7], m, ret, nt),
                      flush=True)
                if n_done % 5 == 0:
                    _write_done(done, windows)

    _write_done(done, windows)
    print('ALL DONE', flush=True)
