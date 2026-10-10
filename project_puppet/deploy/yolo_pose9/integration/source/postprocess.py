"""Shared host/A53 preprocessing and YOLOv8 box/keypoint decode (NumPy)."""
import cv2
import numpy as np


def preprocess(bgr, size=384):
    h,w = bgr.shape[:2]
    scale = min(size / w, size / h)
    nw,nh = round(w*scale), round(h*scale)
    left,top = round((size-nw)/2-0.1), round((size-nh)/2-0.1)
    canvas = np.full((size,size,3),114,np.uint8)
    canvas[top:top+nh,left:left+nw] = cv2.resize(bgr,(nw,nh),interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(canvas,cv2.COLOR_BGR2RGB)
    return rgb.transpose(2,0,1)[None].astype(np.float32)/255, (scale,left,top,w,h)


def sigmoid(x):
    return 1/(1+np.exp(-np.clip(x,-80,80)))


def decode_dense(outputs, strides=(8,16,32)):
    boxes, scores, keypoints = [], [], []
    for i,stride in enumerate(strides):
        reg,cls,kpt = [np.asarray(o,dtype=np.float32) for o in outputs[i*3:i*3+3]]
        _,_,h,w = reg.shape
        dist = reg[0].reshape(4,16,h*w)
        dist = np.exp(dist-dist.max(axis=1,keepdims=True))
        dist = (dist/dist.sum(axis=1,keepdims=True)*np.arange(16)[None,:,None]).sum(axis=1)
        yy,xx = np.meshgrid(np.arange(h),np.arange(w),indexing='ij')
        grid = np.stack((xx.ravel(),yy.ravel())).astype(np.float32)
        anchors = grid+0.5
        box = np.concatenate((anchors-dist[:2],anchors+dist[2:]),axis=0).T*stride
        kp = kpt[0].reshape(9,3,h*w).transpose(2,0,1).copy()
        kp[:,:,:2] = (kp[:,:,:2]*2+grid.T[:,None,:])*stride
        kp[:,:,2] = sigmoid(kp[:,:,2])
        boxes.append(box)
        scores.append(sigmoid(cls).reshape(-1))
        keypoints.append(kp)
    return np.concatenate(boxes),np.concatenate(scores),np.concatenate(keypoints)


def iou(box, others):
    wh = np.maximum(0,np.minimum(box[2:],others[:,2:])-np.maximum(box[:2],others[:,:2]))
    inter = wh.prod(axis=1)
    area = np.maximum(0,box[2:]-box[:2]).prod()
    areas = np.maximum(0,others[:,2:]-others[:,:2]).prod(axis=1)
    return inter / np.maximum(area+areas-inter,1e-8)


def decode(outputs, transform, conf=0.25, nms_iou=0.45, max_det=10):
    boxes,scores,kpts = decode_dense(outputs)
    order = np.flatnonzero(scores>=conf)
    order = order[np.argsort(-scores[order],kind='stable')][:3000]
    keep = []
    while len(order) and len(keep)<max_det:
        best = order[0]
        keep.append(best)
        order = order[1:][iou(boxes[best],boxes[order[1:]])<=nms_iou]
    scale,left,top,w,h = transform
    boxes,scores,kpts = boxes[keep].copy(),scores[keep],kpts[keep].copy()
    boxes[:,[0,2]] = np.clip((boxes[:,[0,2]]-left)/scale,0,w)
    boxes[:,[1,3]] = np.clip((boxes[:,[1,3]]-top)/scale,0,h)
    kpts[:,:,0] = (kpts[:,:,0]-left)/scale
    kpts[:,:,1] = (kpts[:,:,1]-top)/scale
    # Out-of-view points are invalid rather than clamped into the border.
    invalid = (kpts[:,:,0]<0)|(kpts[:,:,0]>w)|(kpts[:,:,1]<0)|(kpts[:,:,1]>h)
    kpts[:,:,2][invalid] = 0
    return boxes,scores,kpts
