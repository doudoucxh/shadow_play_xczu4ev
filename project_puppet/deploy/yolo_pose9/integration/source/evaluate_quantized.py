"""Evaluate the Vitis AI quantization simulation on the frozen val/test sets."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
import torch
from pytorch_nndct.apis import torch_quantizer
from raw_model import load_raw
from postprocess import preprocess, decode
from evaluate import summarize


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--quantized',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--split',choices=['val','test'],required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    torch.set_num_threads(4)
    size=json.loads((a.raw/'architecture.json').read_text())['input_shape'][-1]
    model=load_raw(a.raw)
    quantizer=torch_quantizer('test',model,(torch.zeros(1,3,size,size),),
                              output_dir=str(a.quantized),device=torch.device('cpu'))
    model=quantizer.quant_model.eval()
    records=json.loads((a.dataset/'records.json').read_text(encoding='utf-8'))[a.split]
    rows=[]
    with torch.no_grad():
        for i,r in enumerate(records):
            # records.json was frozen on Windows; split either path separator.
            filename=r['file'].replace('\\','/').rsplit('/',1)[-1]
            path=a.dataset/'images'/a.split/filename
            frame=cv2.imread(str(path))
            if frame is None: raise ValueError(path)
            x,transform=preprocess(frame,size)
            outputs=[o.numpy() for o in model(torch.from_numpy(x))]
            boxes,scores,kpts=decode(outputs,transform)
            detected=bool(len(scores))
            pred=kpts[0] if detected else np.zeros((9,3))
            rows.append({**r,'prediction':pred.tolist(),'detected':detected,
                         'gt':[[p['x'],p['y'],p['v']] for p in r['points']]})
            if i%50==0: print(f'{i+1}/{len(records)}',flush=True)
    report=summarize(rows)
    report.update(split=a.split,model='Vitis AI 3.0 quantization simulation',temporal_smoothing=False)
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'metrics.json').write_text(json.dumps(report,indent=2))
    (a.output/'predictions.json').write_text(json.dumps(rows))
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
