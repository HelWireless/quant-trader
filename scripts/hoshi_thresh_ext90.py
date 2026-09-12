# -*- coding: utf-8 -*-
"""同窗口跨引擎验证：把外部 agent 的 90 个窗口喂进本机引擎（hoshi_backtest_exp5），
跑 t6(-6.0%) / t8(-8.2%) 两个配置，基座 = 方案B（9分/启用日5/R3关/广度20）。

目的：
  1) 校准 —— t8 应与外部 CSV 的 B_ret_pct 接近。若两引擎等价，
     则外部报告的「B 几何 +50.39%」「C 优于 B +12.86pp」就能在本机复现。
  2) 验证 —— t6 与 t8 在同一批窗口上的差，是否复现外部报告的阈值效应。

用法: python hoshi_thresh_ext90.py <t6|t8> [n] [workers]
  n = 采样窗口数（按持有期分层等距抽样）；省略或 0 = 全部 90
输出: hoshi_thr_ext90_<tag>.csv  (含外部 B 值参照列便于即时对拍)
"""
import csv
import importlib.util
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, 'ext90_windows_full.csv')

TAG = (sys.argv[1] if len(sys.argv) > 1 else 't8').lower()
N = int(sys.argv[2]) if len(sys.argv) > 2 else 0
WORKERS = int(sys.argv[3]) if len(sys.argv) > 3 else 5

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
    spec = importlib.util.spec_from_file_location(
        'hbe', os.path.join(HERE, 'hoshi_backtest_exp5.py'))
    hbe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hbe)
    hbe._log = lambda *a, **k: None
    hbe.DEBUG = False
    # 与外部报告对齐本金口径（外部用 30 万）
    hbe.TOTAL_CAPITAL = 300000.0
    hbe.load_market_features(os.path.join(HERE, 'hoshi_market_features.csv'))
    cb, nm, ad = hbe.load_data(os.path.join(HERE, 'hoshi_csv_long'))
    _D['hbe'], _D['cb'], _D['nm'], _D['ad'] = hbe, cb, nm, ad


def _work(task):
    idx, s, e, m, tag = task
    hbe = _D['hbe']
    for k, v in GLOBAL_DEFAULTS.items():
        setattr(hbe, k, v)
    for k, v in SCHEME_B.items():
        setattr(hbe, k, v)
    hbe.LOSS_HARD_PCT = THRESH[tag]
    r = hbe.run_backtest(_D['cb'], _D['nm'], _D['ad'], start=s, end=e)
    ret = (r['final_capital'] - 300000.0) / 300000.0 * 100.0
    return (idx, s, e, m, ret, len(r['closed']))


def load_windows():
    rows = []
    with open(EXT, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r.get('idx') is None or r.get('start') in (None, ''):
                continue
            rows.append(dict(idx=int(r['idx']), start=r['start'], end=r['end'],
                             months=int(r['months']),
                             B_ref=float(r['B_ret_pct']), p6_ref=float(r['p6_ret_pct'])))
    return rows


if __name__ == '__main__':
    wins = load_windows()
    if N and N < len(wins):
        # 按持有期分层等距抽样，保证各档都有
        srt = sorted(wins, key=lambda x: x['months'])
        step = len(srt) / float(N)
        wins = [srt[int(i * step)] for i in range(N)]
    print('窗口数 %d，配置 %s (LOSS_HARD_PCT=%+.1f%%)，并行度 %d'
          % (len(wins), TAG.upper(), THRESH[TAG], WORKERS), flush=True)

    out_path = os.path.join(HERE, 'hoshi_thr_ext90_%s.csv' % TAG)
    done = {}
    if os.path.exists(out_path):
        with open(out_path, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r.get('start'):
                    done[(r['start'], r['end'])] = (r['pct'], r.get('trades', ''))

    todo = [w for w in wins if (w['start'], w['end']) not in done]
    print('待跑 %d（已完成 %d）' % (len(todo), len(wins) - len(todo)), flush=True)
    todo.sort(key=lambda w: -w['months'])

    if todo:
        k = 0
        with ProcessPoolExecutor(max_workers=WORKERS, initializer=_init) as ex:
            futs = {ex.submit(_work, (w['idx'], w['start'], w['end'], w['months'], TAG)): w
                    for w in todo}
            for fu in as_completed(futs):
                idx, s, e, m, ret, nt = fu.result()
                done[(s, e)] = ('%.4f' % ret, str(nt))
                ref = next(w['B_ref'] for w in wins if w['idx'] == idx)
                k += 1
                print('[%3d/%d] #%02d %s~%s (%2d月) %s=%+.1f%% %+9.4f%% 笔%3d | 外部B %+9.4f%% 差 %+8.2fpp'
                      % (k, len(todo), idx, s, e, m, TAG.upper(), THRESH[TAG], ret, nt,
                         ref, ret - ref), flush=True)
                if k % 5 == 0:
                    with open(out_path, 'w', newline='', encoding='utf-8') as f:
                        w_ = csv.writer(f)
                        w_.writerow(['idx', 'start', 'end', 'len_months', 'pct', 'trades', 'B_ref'])
                        for ww in wins:
                            key = (ww['start'], ww['end'])
                            if key in done:
                                w_.writerow([ww['idx'], ww['start'], ww['end'], ww['months'],
                                             done[key][0], done[key][1], '%.4f' % ww['B_ref']])

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w_ = csv.writer(f)
        w_.writerow(['idx', 'start', 'end', 'len_months', 'pct', 'trades', 'B_ref'])
        for ww in wins:
            key = (ww['start'], ww['end'])
            if key in done:
                w_.writerow([ww['idx'], ww['start'], ww['end'], ww['months'],
                             done[key][0], done[key][1], '%.4f' % ww['B_ref']])
    print('DONE -> %s' % out_path, flush=True)
