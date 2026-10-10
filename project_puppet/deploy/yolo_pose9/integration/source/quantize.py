"""Vitis AI 3.0 quantization, using training images only for calibration."""
import argparse
import json
import random
from pathlib import Path
import cv2
import numpy as np
import torch
from pytorch_nndct.apis import torch_quantizer
from raw_model import load_raw


def letterbox(image, size):
    h,w = image.shape[:2]
    r = min(size/h, size/w)
    nw,nh = round(w*r), round(h*r)
    image = cv2.resize(image, (nw,nh), interpolation=cv2.INTER_LINEAR)
    left, top = round((size-nw)/2-0.1), round((size-nh)/2-0.1)
    out = np.full((size,size,3),114,np.uint8)
    out[top:top+nh,left:left+nw] = image
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--dataset', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--mode', choices=['calib','test'], required=True)
    p.add_argument('--samples', type=int, default=128)
    a = p.parse_args()
    torch.set_num_threads(4)
    spec = json.loads((a.raw/'architecture.json').read_text())
    size = spec['input_shape'][-1]
    model = load_raw(a.raw)
    quantizer = torch_quantizer(a.mode, model, (torch.zeros(1,3,size,size),),
                               output_dir=str(a.output), device=torch.device('cpu'))
    qm = quantizer.quant_model.eval()
    paths = sorted((a.dataset/'images/train').glob('*.png'))
    random.Random(20260922).shuffle(paths)
    paths = paths[:a.samples]
    if not paths:
        raise ValueError('No calibration images')
    with torch.no_grad():
        for i,path in enumerate(paths):
            im = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
            x = letterbox(im,size).transpose(2,0,1)[None].astype(np.float32)/255.0
            qm(torch.from_numpy(x))
            print(f'{a.mode} {i+1}/{len(paths)}', flush=True)
    if a.mode == 'calib':
        quantizer.export_quant_config()
        (a.output/'calibration_images.json').write_text(json.dumps([p.name for p in paths], indent=2))
    else:
        quantizer.export_xmodel(output_dir=str(a.output), deploy_check=True)


if __name__ == '__main__':
    main()
