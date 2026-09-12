import os
HERE = os.path.dirname(os.path.abspath(__file__))
out = []
for fn in sorted(os.listdir(HERE)):
    if fn.startswith('hoshi_oos') and fn.endswith('.csv'):
        with open(os.path.join(HERE, fn), encoding='utf-8') as f:
            lines = f.read().strip().split('\n')
        out.append('%-32s rows=%-4d header=%s' % (fn, len(lines) - 1, lines[0]))
with open(os.path.join(HERE, '_check_oos.txt'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
