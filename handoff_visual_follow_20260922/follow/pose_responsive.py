"""Responsive pose filtering: preserve tracking/outlier protection, bypass history for motion."""
from collections import deque
import math
import numpy as np

class PoseStabilizer:
    def __init__(self):
        self.box=None;self.last_seen=None;self.last_time=None
        self.filtered=np.zeros((9,2),np.float32)
        self.ready=np.zeros(9,bool)
        self.history=[deque(maxlen=3) for _ in range(9)]
        self.pending=[None]*9
        self.fast_until=np.zeros(9,np.float64)
        self.selected=None;self.track_id=0

    def reset_points(self):
        self.ready[:]=False
        for history in self.history:history.clear()
        self.pending=[None]*9
        self.fast_until[:]=0

    def update(self,boxes,scores,points,now):
        self.selected=None
        boxes=np.asarray(boxes,dtype=np.float32).reshape(-1,4)
        scores=np.asarray(scores,dtype=np.float32)
        points=np.asarray(points,dtype=np.float32).reshape(-1,9,3)
        if not (len(boxes)==len(scores)==len(points)):raise ValueError('Detection shape mismatch')
        if not len(scores):
            if self.last_seen is not None and now-self.last_seen>.35:
                self.box=None;self.reset_points()
            return None
        finite=np.isfinite(boxes).all(axis=1)&np.isfinite(scores)&np.isfinite(points).all(axis=(1,2))
        candidates=np.flatnonzero(finite)
        if not len(candidates):return None
        if self.last_seen is not None and now-self.last_seen>.35:
            self.box=None;self.reset_points()
        if self.box is None:
            index=int(candidates[np.argmax(scores[candidates])])
            self.track_id+=1
            self.reset_points()
        else:
            b=boxes[candidates]
            wh=np.maximum(0,np.minimum(b[:,2:],self.box[2:])-np.maximum(b[:,:2],self.box[:2]))
            inter=wh.prod(axis=1)
            area=np.maximum(0,b[:,2:]-b[:,:2]).prod(axis=1)
            old_area=np.maximum(0,self.box[2:]-self.box[:2]).prod()
            iou=inter/np.maximum(area+old_area-inter,1e-8)
            best=int(np.argmax(iou+.03*scores[candidates]))
            if iou[best]<.20:return None  # Don't jump to an unrelated background person.
            index=int(candidates[best])
        self.selected=index
        self.box=boxes[index].copy()
        gap=now-self.last_time if self.last_time is not None else 1/28.6
        if gap>.25:self.reset_points()
        dt=min(max(gap,.001),.1)
        self.last_time=now;self.last_seen=now
        out=points[index].copy()
        for j in range(9):
            z=out[j,:2].copy()
            if out[j,2]<.25:
                self.ready[j]=False;self.history[j].clear();self.pending[j]=None
                out[j,2]=0
                continue
            if not self.ready[j]:
                self.filtered[j]=z;self.ready[j]=True
                self.history[j].append(z)
                continue
            dx=float(z[0]-self.filtered[j,0]);dy=float(z[1]-self.filtered[j,1])
            delta_norm=math.hypot(dx,dy)
            limb=j in (3,4,5,6)
            if delta_norm>(180 if limb else 120):
                pending=self.pending[j]
                accepted=False
                if pending is not None:
                    ox=float(pending[0]-self.filtered[j,0]);oy=float(pending[1]-self.filtered[j,1])
                    cosine=(dx*ox+dy*oy)/(delta_norm*math.hypot(ox,oy)+1e-6)
                    accepted=math.hypot(float(z[0]-pending[0]),float(z[1]-pending[1]))<50 or cosine>.8
                if not accepted:
                    self.pending[j]=z
                    out[j,:2]=self.filtered[j]
                    out[j,2]=0  # Hide an unconfirmed jump, don't draw a made-up location.
                    continue
                self.history[j].clear()
            self.pending[j]=None
            self.history[j].append(z)
            history=list(self.history[j])
            moving=delta_norm>80
            if len(history)>=2:
                previous=history[-2]
                recent=math.hypot(float(z[0]-previous[0]),float(z[1]-previous[1]))
                if recent<8 and delta_norm>24:moving=True
            if len(history)>=3:
                ax=float(history[-2][0]-history[-3][0]);ay=float(history[-2][1]-history[-3][1])
                bx=float(z[0]-history[-2][0]);by=float(z[1]-history[-2][1])
                na=math.hypot(ax,ay);nb=math.hypot(bx,by)
                if na>4 and nb>4 and (ax*bx+ay*by)/(na*nb)>.7:moving=True
            if moving:self.fast_until[j]=now+.10
            if now<self.fast_until[j]:
                # Use the current measurement during movement, not a trailing median.
                tx,ty=float(z[0]),float(z[1])
                tau=.015 if limb else .025
                deadband=1.5
            else:
                xs=sorted(float(v[0]) for v in history);ys=sorted(float(v[1]) for v in history)
                n=len(xs)
                tx=(xs[0]+xs[1])*.5 if n==2 else xs[n//2]
                ty=(ys[0]+ys[1])*.5 if n==2 else ys[n//2]
                tau=.08 if limb else .12
                deadband=2.
            distance=math.hypot(tx-float(self.filtered[j,0]),ty-float(self.filtered[j,1]))
            alpha=1-math.exp(-dt/tau)
            if distance>deadband:
                self.filtered[j,0]+=alpha*(tx-self.filtered[j,0])
                self.filtered[j,1]+=alpha*(ty-self.filtered[j,1])
            out[j,:2]=self.filtered[j]
        return out
