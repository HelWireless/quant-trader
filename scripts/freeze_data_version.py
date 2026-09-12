# -*- coding: utf-8 -*-
"""冻结回测数据版本 —— 记录 hoshi 研究依赖的全部输入数据的指纹。

动机（2026-09-12 事故）：
  hoshi_market_features.csv 直接由 data/tdx.duckdb 实时计算，而 TDX 增量刷新会
  改动历史 K 线/名称表，导致「重算后历史广度值漂移」→ 回测数值变化 →
  9-11 生成的锚点文件（hoshi_abl*_b.csv）在 9-12 全部对不上。
  更糟的是这些输入文件**未被 git 跟踪**，无法追溯。

本脚本产出 scripts/hoshi_data_version.json，作为后续所有回测的版本指纹；
每次刷新数据后重跑，并 diff 上一次的 json 即可发现漂移。
"""
import csv
import hashlib
import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..'))
OUT = os.path.join(HERE, 'hoshi_data_version.json')


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


v = {'frozen_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# 1) 市场特征表（广度门控的唯一输入）
feat = os.path.join(HERE, 'hoshi_market_features.csv')
if os.path.exists(feat):
    d = list(csv.DictReader(open(feat, encoding='utf-8')))
    v['market_features'] = {
        'path': 'scripts/hoshi_market_features.csv',
        'sha256': sha256_file(feat),
        'rows': len(d),
        'range': '%s ~ %s' % (d[0]['date'], d[-1]['date']) if d else None,
        'size': os.path.getsize(feat),
    }

# 2) K 线长表（清单指纹：文件数 + 总字节 + 逐文件 name/size 的哈希）
cdir = os.path.join(HERE, 'hoshi_csv_long')
if os.path.isdir(cdir):
    items = []
    total = 0
    for name in sorted(os.listdir(cdir)):
        p = os.path.join(cdir, name)
        if not os.path.isfile(p):
            continue
        sz = os.path.getsize(p)
        total += sz
        items.append('%s:%d' % (name, sz))
    h = hashlib.sha256('\n'.join(items).encode()).hexdigest()
    v['hoshi_csv_long'] = {
        'path': 'scripts/hoshi_csv_long/',
        'files': len(items),
        'total_bytes': total,
        'manifest_sha256': h,
    }

# 3) duckdb 原始库状态
try:
    import duckdb
    db = os.path.join(REPO, 'data', 'tdx.duckdb')
    con = duckdb.connect(db, read_only=True)
    r1 = con.execute('SELECT COUNT(*), MIN(date), MAX(date) FROM raw_kline_daily').fetchone()
    r2 = con.execute('SELECT COUNT(*) FROM raw_symbol_name').fetchone()
    con.close()
    v['duckdb'] = {
        'path': 'data/tdx.duckdb',
        'raw_kline_daily': {'rows': r1[0], 'min_date': str(r1[1]), 'max_date': str(r1[2])},
        'raw_symbol_name_rows': r2[0],
        'size': os.path.getsize(db),
    }
except Exception as ex:
    v['duckdb'] = {'error': str(ex)}

# 4) 关键锚点文件（现有结果，供后续 diff）
anchors = {}
for fn in ('hoshi_abl1_b.csv', 'hoshi_abl2_b.csv', 'hoshi_fix1_base.csv', 'hoshi_fix2_base.csv'):
    p = os.path.join(HERE, fn)
    if os.path.exists(p):
        anchors[fn] = sha256_file(p)[:16]
v['anchor_files'] = anchors

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(v, f, ensure_ascii=False, indent=2)

print(json.dumps(v, ensure_ascii=False, indent=2))
print('\n已写出: %s' % OUT)
