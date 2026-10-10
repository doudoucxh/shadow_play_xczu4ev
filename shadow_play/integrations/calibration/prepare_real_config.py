#!/usr/bin/env python3
"""Generate an intentionally incomplete real configuration; no motion is performed."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
data = json.loads((root/'config/capture.demo.json').read_text(encoding='utf-8'))
data['simulation_only'] = False
data['reference_view'] = 'front'
data['stage'] = {'width_mm': None, 'height_mm': None}
data.pop('reference_points_mm', None)
data['points'] = []
for axis in data['axes']:
    axis['unit'] = 'UNCONFIRMED'
    for key in ('min', 'max', 'initial', 'jog_step', 'max_step'):
        axis[key] = None
for slide in data['slides']:
    slide['unit'] = 'UNCONFIRMED'
    for key in ('min', 'max', 'value', 'jog_step', 'max_step'):
        slide[key] = None
with args.output.open('x', encoding='utf-8') as out:
    json.dump(data, out, ensure_ascii=False, indent=2)
    out.write('\n')
print('Fill ALL null/UNCONFIRMED fields using verified hardware information: ' + str(args.output))
