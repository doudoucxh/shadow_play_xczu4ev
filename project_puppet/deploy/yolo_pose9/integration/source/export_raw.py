"""Export and numerically verify the portable nine-output DPU CNN."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from ultralytics import YOLO
from raw_model import RawPose, describe, load_raw
from postprocess import decode_dense


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--size', type=int, default=384)
    a = p.parse_args()
    torch.set_num_threads(8)
    model = YOLO(str(a.weights)).model.cpu().float().eval()
    layers, head = model.model[:-1], model.model[-1]
    assert head.nc == 1 and tuple(head.kpt_shape) == (9,3)
    spec = {'layers': [describe(m) for m in layers], 'routes': [m.f for m in layers],
            'sources': head.f, 'cv2': describe(head.cv2), 'cv3': describe(head.cv3),
            'cv4': describe(head.cv4), 'input_shape': [1,3,a.size,a.size],
            'strides': head.stride.tolist(), 'reg_max': head.reg_max, 'keypoint_shape': [9,3]}
    a.output.mkdir(parents=True, exist_ok=True)
    (a.output / 'architecture.json').write_text(json.dumps(spec, indent=2))
    tensors = {}
    for k,v in model.state_dict().items():
        prefix = f'model.{len(layers)}.'
        if k.startswith(prefix):
            k = k[len(prefix):]
            if not k.startswith(('cv2.', 'cv3.', 'cv4.')):
                continue
        tensors[k] = v.detach().cpu().numpy()
    np.savez(a.output / 'weights.npz', **tensors)
    raw = load_raw(a.output)
    captured = []
    def hook(_module, inputs):
        for i,x in enumerate(inputs[0]):
            captured.extend((head.cv2[i](x), head.cv3[i](x), head.cv4[i](x)))
    h = head.register_forward_pre_hook(hook)
    errors = []
    decode_errors = []
    with torch.no_grad():
        for seed in range(3):
            torch.manual_seed(seed)
            x = torch.rand(1,3,a.size,a.size)
            captured.clear()
            prediction = model(x)[0].numpy()
            actual = raw(x)
            for expected, value in zip(captured, actual):
                torch.testing.assert_close(expected, value, atol=1e-5, rtol=1e-5)
                errors.append(float((expected-value).abs().max()))
            boxes, scores, kpts = decode_dense([v.numpy() for v in actual])
            xywh = np.concatenate(((boxes[:,:2]+boxes[:,2:])/2, boxes[:,2:]-boxes[:,:2]),axis=1)
            decoded = np.concatenate((xywh,scores[:,None],kpts.reshape(-1,27)),axis=1).T[None]
            np.testing.assert_allclose(prediction,decoded,atol=0.001,rtol=1e-5)
            decode_errors.append(float(np.max(np.abs(prediction-decoded))))
    h.remove()
    result = {'raw_output_max_absolute_error': max(errors),
              'numpy_decode_max_absolute_error': max(decode_errors),
              'output_shapes': [list(v.shape) for v in actual],
              'status': 'FP32 raw CNN equivalence only; DPU compile and INT8 accuracy separate'}
    (a.output / 'equivalence.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
