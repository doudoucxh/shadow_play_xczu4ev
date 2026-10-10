"""Portable YOLO CNN, no Ultralytics dependency in Vitis AI 3.0.

Network topology/weights are imported from the trained Ultralytics model.
YOLOv8 architecture attribution: https://github.com/ultralytics/ultralytics
Derived architecture is subject to its AGPL-3.0 license.
"""
import json
from pathlib import Path
import numpy as np
import torch
from torch import nn


class Block(nn.Module):
    def __init__(self, spec):
        super().__init__()
        self.kind = spec['type']
        self.c = spec.get('c', 0)
        self.add = spec.get('add', False)
        self.d = spec.get('d', 1)
        for name, child in spec.get('children', {}).items():
            self.add_module(name, build(child))

    def forward(self, x):
        if self.kind == 'Conv':
            return self.act(self.bn(self.conv(x)))
        if self.kind == 'Bottleneck':
            y = self.cv2(self.cv1(x))
            return x + y if self.add else y
        if self.kind == 'C2f':
            z = self.cv1(x)
            ys = [z[:, :self.c, :, :], z[:, self.c:, :, :]]
            for m in self.m:
                ys.append(m(ys[-1]))
            return self.cv2(torch.cat(ys, 1))
        if self.kind == 'SPPF':
            a = self.cv1(x)
            b = self.m(a)
            c = self.m(b)
            return self.cv2(torch.cat((a, b, c, self.m(c)), 1))
        if self.kind == 'Concat':
            return torch.cat(x, self.d)
        raise RuntimeError(self.kind)


def build(spec):
    t = spec['type']
    if t in ('Sequential', 'ModuleList'):
        return getattr(nn, t)(*[build(s) for s in spec['items']]) if t == 'Sequential' else nn.ModuleList([build(s) for s in spec['items']])
    if t in ('Conv2d', 'BatchNorm2d', 'ReLU', 'SiLU', 'MaxPool2d', 'Upsample', 'Identity'):
        return getattr(nn, t)(**spec['args'])
    return Block(spec)


class RawPose(nn.Module):
    def __init__(self, spec):
        super().__init__()
        self.routes = spec['routes']
        self.model = nn.ModuleList([build(s) for s in spec['layers']])
        self.cv2 = build(spec['cv2'])
        self.cv3 = build(spec['cv3'])
        self.cv4 = build(spec['cv4'])
        self.sources = spec['sources']

    def forward(self, x):
        values = []
        for i, layer in enumerate(self.model):
            route = self.routes[i]
            if isinstance(route, list):
                z = [x if j == -1 else values[j] for j in route]
            else:
                z = x if route == -1 else values[route]
            x = layer(z)
            values.append(x)
        outputs = []
        for i, source in enumerate(self.sources):
            x = values[source]
            # Separate box, person score, keypoints avoid cross-branch quantization scales.
            outputs.extend((self.cv2[i](x), self.cv3[i](x), self.cv4[i](x)))
        return tuple(outputs)


def load_raw(directory):
    directory = Path(directory)
    model = RawPose(json.loads((directory / 'architecture.json').read_text()))
    with np.load(directory / 'weights.npz') as weights:
        model.load_state_dict({k: torch.from_numpy(weights[k].copy()) for k in weights.files}, strict=True)
    return model.eval()


def describe(m):
    name = type(m).__name__
    if name in ('Sequential', 'ModuleList'):
        return {'type': name, 'items': [describe(c) for c in m]}
    fields = {
        'Conv2d': ['in_channels','out_channels','kernel_size','stride','padding','dilation','groups','padding_mode'],
        'BatchNorm2d': ['num_features','eps','momentum','affine','track_running_stats'],
        'ReLU': ['inplace'], 'SiLU': ['inplace'],
        'MaxPool2d': ['kernel_size','stride','padding','dilation','return_indices','ceil_mode'],
        'Upsample': ['size','scale_factor','mode','align_corners'], 'Identity': []}
    if name in fields:
        args = {k: getattr(m, k) for k in fields[name]}
        if name == 'Conv2d':
            args['bias'] = m.bias is not None
        return {'type': name, 'args': args}
    if name not in ('Conv','C2f','Bottleneck','SPPF','Concat'):
        raise ValueError(f'Unsupported portable block: {name}')
    return {'type': name, 'children': {k: describe(c) for k,c in m.named_children()},
            **{k: getattr(m,k) for k in ('c','add','d') if hasattr(m,k)}}
