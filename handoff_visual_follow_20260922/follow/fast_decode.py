"""Equivalent YOLO decode, but only dequantize candidates above the score gate.

Input order is stride 8/16/32, each box/class/keypoint NHWC INT8 tensor.
No confidence threshold or keypoint semantics are changed.
"""
import numpy as np

def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -80, 80)))

def decode_int8(outputs, fixes, transform, conf=.25, nms_iou=.45, max_det=10):
    boxes, scores, keypoints = [], [], []
    for index, stride in enumerate((8, 16, 32)):
        reg, cls, kp = outputs[index*3:index*3+3]
        rf, cf, kf = fixes[index*3:index*3+3]
        n = cls.shape[1]
        score = sigmoid(cls.reshape(-1).astype(np.float32) * (2. ** -cf))
        selected = np.flatnonzero(score >= conf)
        if not len(selected):
            continue
        dist = reg.reshape(-1, 4, 16)[selected].astype(np.float32) * (2. ** -rf)
        dist = np.exp(dist - dist.max(axis=2, keepdims=True))
        dist = (dist / dist.sum(axis=2, keepdims=True) * np.arange(16)[None, None, :]).sum(axis=2)
        grid = np.stack((selected % n, selected // n), axis=1).astype(np.float32)
        anchors = grid + .5
        boxes.append(np.concatenate((anchors-dist[:,:2], anchors+dist[:,2:]), axis=1)*stride)
        points = kp.reshape(-1, 9, 3)[selected].astype(np.float32) * (2. ** -kf)
        points[:,:,:2] = (points[:,:,:2]*2 + grid[:,None,:])*stride
        points[:,:,2] = sigmoid(points[:,:,2])
        scores.append(score[selected])
        keypoints.append(points)
    if not scores:
        return np.empty((0,4),np.float64), np.empty(0,np.float32), np.empty((0,9,3),np.float32)
    boxes, scores, points = map(np.concatenate, (boxes, scores, keypoints))
    order = np.argsort(-scores, kind='stable')[:3000]
    keep = []
    while len(order) and len(keep) < max_det:
        best = order[0]
        keep.append(best)
        other = order[1:]
        wh = np.maximum(0, np.minimum(boxes[best,2:],boxes[other,2:])-np.maximum(boxes[best,:2],boxes[other,:2]))
        inter = wh.prod(axis=1)
        area = np.maximum(0,boxes[best,2:]-boxes[best,:2]).prod()
        areas = np.maximum(0,boxes[other,2:]-boxes[other,:2]).prod(axis=1)
        order = other[inter / np.maximum(area+areas-inter,1e-8) <= nms_iou]
    boxes, scores, points = boxes[keep].copy(), scores[keep], points[keep].copy()
    scale, left, top, w, h = transform
    boxes[:,[0,2]] = np.clip((boxes[:,[0,2]]-left)/scale,0,w)
    boxes[:,[1,3]] = np.clip((boxes[:,[1,3]]-top)/scale,0,h)
    points[:,:,0] = (points[:,:,0]-left)/scale
    points[:,:,1] = (points[:,:,1]-top)/scale
    invalid = (points[:,:,0]<0)|(points[:,:,0]>w)|(points[:,:,1]<0)|(points[:,:,1]>h)
    points[:,:,2][invalid] = 0
    return boxes, scores, points
