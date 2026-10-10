"""Board runtime: two DPU V2 models plus the complete NumPy ARM-CHAIN decoder."""

from __future__ import annotations

import argparse
import mmap
import os
import struct
import time
from pathlib import Path

import cv2
import numpy as np
try:
    import vart
    import xir
except ImportError:  # Allows host-side decoder equivalence tests without VART.
    vart = None
    xir = None


INPUT_W, INPUT_H = 256, 144
VIDEO_W, VIDEO_H = 1280, 720
VIDEO_FRAME_BYTES = VIDEO_W * VIDEO_H * 3
POSE_FRAME_BYTES = INPUT_W * INPUT_H * 3
VIDEO_CAPTURE_BASE = 0x70000000
VIDEO_DISPLAY_BASE = 0x71000000
POSE_CAPTURE_BASE = 0x72000000
VIDEO_VDMA_BASE = 0xA0000000
POSE_VDMA_BASE = 0xA0010000
VDMA_PARKPTR = 0x28
SKELETON = [(0, 1), (0, 2), (1, 2), (1, 3), (3, 5), (2, 4), (4, 6), (1, 7), (2, 8), (7, 8)]
COLORS = [(0,255,255),(0,255,0),(255,255,0),(0,220,0),(220,220,0),(0,180,0),(180,180,0),(0,140,0),(140,140,0)]


def dpu_subgraph(model_path):
    if xir is None:
        raise RuntimeError("VART/XIR are required on the target for DPU execution")
    graph = xir.Graph.deserialize(str(model_path))
    roots = graph.get_root_subgraph().toposort_child_subgraph()
    subgraphs = [s for s in roots if s.has_attr("device") and s.get_attr("device").upper() == "DPU"]
    if len(subgraphs) != 1:
        raise RuntimeError(f"expected one DPU subgraph in {model_path}, got {len(subgraphs)}")
    return graph, subgraphs[0]


class DpuPoseModel:
    def __init__(self, path):
        self.graph, subgraph = dpu_subgraph(path)
        self.runner = vart.Runner.create_runner(subgraph, "run")
        self.input_tensor = self.runner.get_input_tensors()[0]
        self.output_tensor = self.runner.get_output_tensors()[0]
        self.input_dims = tuple(self.input_tensor.dims)
        self.output_dims = tuple(self.output_tensor.dims)
        self.input_fix = self.input_tensor.get_attr("fix_point") if self.input_tensor.has_attr("fix_point") else None
        self.output_fix = self.output_tensor.get_attr("fix_point") if self.output_tensor.has_attr("fix_point") else None

    def __call__(self, nchw):
        if self.input_dims == (1, INPUT_H, INPUT_W, 3):
            value = nchw.transpose(0, 2, 3, 1)
        elif self.input_dims == (1, 3, INPUT_H, INPUT_W):
            value = nchw
        else:
            raise RuntimeError(f"unsupported DPU input shape: {self.input_dims}")
        if self.input_fix is not None:
            value = np.clip(np.rint(value * (2.0 ** self.input_fix)), -128, 127).astype(np.int8)
        else:
            value = value.astype(np.float32)
        output_dtype = np.int8 if self.output_fix is not None else np.float32
        output = np.empty(self.output_dims, dtype=output_dtype)
        job = self.runner.execute_async([np.ascontiguousarray(value)], [output])
        self.runner.wait(job)
        if self.output_fix is not None:
            output = output.astype(np.float32) * (2.0 ** -self.output_fix)
        if output.shape == (1, 36, 64, 9):
            output = output.transpose(0, 3, 1, 2)
        if output.shape != (1, 9, 36, 64):
            raise RuntimeError(f"unsupported DPU output shape: {output.shape}")
        return output


class Ranker:
    def __init__(self, path):
        state = np.load(path)
        self.layers = [(state[f"{index}.weight"].astype(np.float32), state[f"{index}.bias"].astype(np.float32)) for index in (0, 2, 4)]

    def __call__(self, features):
        value = features
        for layer, (weight, bias) in enumerate(self.layers):
            value = value @ weight.T + bias
            if layer < 2:
                value = np.maximum(value, 0.0)
        return value[..., 0]


def argmax_xy(logits):
    _, channels, _, width = logits.shape
    index = logits.reshape(1, channels, -1).argmax(axis=2)
    return np.stack((index % width, index // width), axis=-1).astype(np.float32)


def local_topk(logits, k=3):
    batch, channels, _, width = logits.shape
    points = np.empty((batch, channels, k, 2), np.float32)
    for b in range(batch):
        for c in range(channels):
            heatmap = logits[b, c]
            pooled = cv2.dilate(heatmap, np.ones((5, 5), np.uint8))
            flat = np.where(heatmap >= pooled, heatmap, -np.inf).reshape(-1)
            choice = np.argpartition(flat, -k)[-k:]
            choice = choice[np.argsort(flat[choice])[::-1]]
            points[b, c, :, 0] = choice % width
            points[b, c, :, 1] = choice // width
    return points


def standardize(logits):
    flat = logits.reshape(*logits.shape[:2], -1)
    mean = flat.mean(axis=2, keepdims=True)
    std = np.maximum(flat.std(axis=2, ddof=1, keepdims=True), 1e-4)
    return ((flat - mean) / std).reshape(logits.shape)


def gather(maps, points):
    # Batch 1: S points x C heatmaps.
    p = points[0].astype(np.int64)
    return maps[0, :, p[:, 1], p[:, 0]][None]


def build_arm_chains(baseline, specialist, peaks=3):
    elbow_pool = local_topk(baseline[:, 3:5], peaks).reshape(1, -1, 2)
    wrist_pool = np.concatenate((
        local_topk(baseline[:, 5:7], peaks).reshape(1, -1, 2),
        local_topk(specialist[:, 5:7], peaks).reshape(1, -1, 2),
    ), axis=1)
    elbows = np.repeat(elbow_pool[:, :, None, :], wrist_pool.shape[1], axis=2)
    wrists = np.repeat(wrist_pool[:, None, :, :], elbow_pool.shape[1], axis=1)
    chain = np.stack((elbows, wrists), axis=3).reshape(1, -1, 2, 2)
    chains = np.repeat(chain[:, None], 2, axis=1)
    anchors = argmax_xy(baseline)
    body_scale = max(float(np.linalg.norm(anchors[0, 1] - anchors[0, 2])), 4.0)
    h, w = baseline.shape[-2:]
    base_elbow_z, specialist_elbow_z = standardize(baseline[:, 3:5]), standardize(specialist[:, 3:5])
    base_wrist_z, specialist_wrist_z = standardize(baseline[:, 5:7]), standardize(specialist[:, 5:7])
    side_features = []
    count = chain.shape[1]
    elbow_count, wrist_count = elbow_pool.shape[1], wrist_pool.shape[1]
    elbow_source_channel = np.repeat(np.arange(2), peaks)
    wrist_source_model = np.repeat(np.arange(2), 2 * peaks)
    wrist_source_channel = np.tile(np.repeat(np.arange(2), peaks), 2)
    for side, (shoulder, other_shoulder) in enumerate(((1, 2), (2, 1))):
        elbow, wrist = chain[0, :, 0], chain[0, :, 1]
        upper_vector = (elbow - anchors[0, shoulder]) / body_scale
        fore_vector = (wrist - elbow) / body_scale
        full_vector = (wrist - anchors[0, shoulder]) / body_scale
        upper_length = np.linalg.norm(upper_vector, axis=1)
        fore_length = np.linalg.norm(fore_vector, axis=1)
        full_length = np.linalg.norm(full_vector, axis=1)
        ratio = fore_length / np.maximum(upper_length, 0.05)
        other_distance = np.linalg.norm(elbow - anchors[0, other_shoulder], axis=1) / body_scale
        angle = np.sum(upper_vector * fore_vector, axis=1) / np.maximum(upper_length * fore_length, 0.01)
        coordinate = np.concatenate((elbow / [w - 1, h - 1], wrist / [w - 1, h - 1]), axis=1)
        lengths = np.stack((upper_length, fore_length, ratio, full_length, other_distance, angle), axis=1)
        elbow_evidence = np.concatenate((gather(base_elbow_z, elbow[None])[0], gather(specialist_elbow_z, elbow[None])[0]), axis=1)
        wrist_evidence = np.concatenate((gather(base_wrist_z, wrist[None])[0], gather(specialist_wrist_z, wrist[None])[0]), axis=1)
        evidence_delta = np.stack((
            elbow_evidence[:, side] - elbow_evidence[:, 1-side],
            elbow_evidence[:, 2+side] - elbow_evidence[:, 3-side],
            wrist_evidence[:, side] - wrist_evidence[:, 1-side],
            wrist_evidence[:, 2+side] - wrist_evidence[:, 3-side],
        ), axis=1)
        elbow_own = np.repeat(elbow_source_channel == side, wrist_count).astype(np.float32)
        wrist_model = np.tile(wrist_source_model, elbow_count).astype(np.float32)
        wrist_own = np.tile(wrist_source_channel == side, elbow_count).astype(np.float32)
        sources = np.stack((elbow_own, wrist_model, wrist_own), axis=1)
        side_column = np.full((count, 1), side, np.float32)
        side_features.append(np.concatenate((coordinate, upper_vector, fore_vector, full_vector, lengths, elbow_evidence, wrist_evidence, evidence_delta, sources, side_column), axis=1).astype(np.float32))
    return chains, np.stack(side_features, axis=0)[None], anchors


def softmax_confidence(logits):
    flat = logits[0].reshape(9, -1)
    shifted = flat - flat.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return (exp.max(axis=1) / exp.sum(axis=1)).astype(np.float32)


class ArmChainDecoder:
    def __init__(self, ranker_path, temporal_weight=.35, min_forearm_ratio=.45, down_pose_weight=.5):
        self.ranker = Ranker(ranker_path)
        self.temporal_weight = temporal_weight
        self.min_forearm_ratio = min_forearm_ratio
        self.down_pose_weight = down_pose_weight
        self.previous_arms = None
        self.velocity = None
        self.previous_pose = None

    def reset(self):
        self.previous_arms = self.velocity = self.previous_pose = None

    def decode(self, baseline, specialist):
        chains, features, anchors = build_arm_chains(baseline, specialist)
        candidates = chains[0]
        scores = self.ranker(features)[0]
        shoulder_span = max(float(np.linalg.norm(anchors[0,1] - anchors[0,2])), 4.0)
        shoulder = anchors[0, [1,2]]
        hip = anchors[0, [7,8]]
        elbow, wrist = candidates[...,0,:], candidates[...,1,:]
        upper = elbow - shoulder[:,None]
        fore = wrist - elbow
        ratio = np.maximum(np.linalg.norm(fore, axis=2), 1.0) / np.maximum(np.linalg.norm(upper, axis=2), 1.0)
        scores -= 8.0 * np.maximum(self.min_forearm_ratio - ratio, 0.0)
        scores -= 2.0 * np.maximum(ratio - 1.9, 0.0)
        base_upper = np.stack((anchors[0,3]-anchors[0,1], anchors[0,4]-anchors[0,2]))
        downness = base_upper[:,1] / np.maximum(np.linalg.norm(base_upper, axis=1), 1.0)
        down_activation = float(np.clip((downness.min() - .72) / .16, 0.0, 1.0))
        hip_distance = np.linalg.norm(wrist - hip[:,None], axis=2) / shoulder_span
        scores -= self.down_pose_weight * down_activation * 4.0 * np.maximum(hip_distance - 1.10, 0.0)
        if self.previous_arms is not None:
            predicted = self.previous_arms.copy()
            if self.velocity is not None:
                length = np.maximum(np.linalg.norm(self.velocity, axis=2, keepdims=True), 1e-6)
                predicted += self.velocity * np.minimum(.35 * shoulder_span / length, 1.0)
            distance = np.linalg.norm(candidates - predicted[:,None], axis=3) / shoulder_span
            scores -= self.temporal_weight * np.minimum(np.sum(distance ** 2, axis=2), 6.0)
        pair = scores[0,:,None] + scores[1,None,:]
        separation = np.linalg.norm(candidates[0,:,None,0] - candidates[1,None,:,0], axis=2) / shoulder_span
        pair -= 10.0 * np.maximum(.18 - separation, 0.0)
        left_choice, right_choice = np.unravel_index(pair.argmax(), pair.shape)
        choices = np.array((left_choice, right_choice))
        selected = np.stack((candidates[0,left_choice], candidates[1,right_choice]))
        if self.previous_arms is None:
            new_velocity = np.zeros_like(selected)
        else:
            measured = selected - self.previous_arms
            new_velocity = measured if self.velocity is None else .65*self.velocity + .35*measured
            length = np.maximum(np.linalg.norm(new_velocity, axis=2, keepdims=True), 1e-6)
            new_velocity *= np.minimum(.35 * shoulder_span / length, 1.0)
        self.previous_arms, self.velocity = selected.copy(), new_velocity
        points = anchors[0].copy()
        points[3], points[5], points[4], points[6] = selected[0,0], selected[0,1], selected[1,0], selected[1,1]
        points *= np.array((INPUT_W/64.0, INPUT_H/36.0), np.float32)
        confidence = softmax_confidence(baseline)
        confidence[5:7] = np.maximum(confidence[5:7], softmax_confidence(specialist)[5:7])
        forearm_ratio = ratio[np.arange(2), choices]
        return points, confidence, forearm_ratio, down_activation > 0.0

    def stabilize(self, current):
        if self.previous_pose is None:
            self.previous_pose = current.copy()
            return current
        scale = max(float(np.linalg.norm(current[1]-current[2])), 24.0)
        displacement = np.linalg.norm(current-self.previous_pose, axis=1) / scale
        alpha = np.full(9, .58, np.float32); alpha[3:7] = .72
        stable = np.array([1,1,1,0,0,0,0,1,1], dtype=bool)
        alpha[stable & (displacement > .35)] = .16
        alpha[5:7] = np.where(displacement[5:7] > 1.0, .42, alpha[5:7])
        self.previous_pose += alpha[:,None] * (current-self.previous_pose)
        return self.previous_pose.copy()


def preprocess(frame):
    resized = cv2.resize(frame, (INPUT_W, INPUT_H), interpolation=cv2.INTER_NEAREST)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    return (rgb.transpose(2,0,1)[None].astype(np.float32) / 127.5 - 1.0)


def center_crop(frame):
    h,w = frame.shape[:2]
    if w/h > 16/9:
        cw,ch = round(h*16/9),h; x,y=(w-round(h*16/9))//2,0
    else:
        cw,ch=w,round(w*9/16); x,y=0,(h-round(w*9/16))//2
    return frame[y:y+ch,x:x+cw], (x,y,cw,ch)


def map_frame(points, box):
    x,y,w,h=box
    return points * np.array((w/INPUT_W,h/INPUT_H),np.float32) + np.array((x,y),np.float32)


def draw(frame, points, confidence, minimum):
    pts=[tuple(np.rint(p).astype(int)) for p in points]
    for a,b in SKELETON:
        if confidence[a]>=minimum and confidence[b]>=minimum: cv2.line(frame,pts[a],pts[b],(255,255,255),2,cv2.LINE_AA)
    for index,point in enumerate(pts):
        if confidence[index]>=minimum:
            cv2.circle(frame,point,5,COLORS[index],-1,cv2.LINE_AA)


class VdmaCamera:
    """Read the PL pose buffer and present annotated frames through HDMI."""

    def __init__(self, device="/dev/mem"):
        self.fd = os.open(device, os.O_RDWR | os.O_SYNC)
        self.video_regs = mmap.mmap(
            self.fd, 0x10000, flags=mmap.MAP_SHARED,
            prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=VIDEO_VDMA_BASE)
        self.pose_regs = mmap.mmap(
            self.fd, 0x10000, flags=mmap.MAP_SHARED,
            prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=POSE_VDMA_BASE)
        self.video_capture = mmap.mmap(
            self.fd, VIDEO_FRAME_BYTES * 3, flags=mmap.MAP_SHARED,
            prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=VIDEO_CAPTURE_BASE)
        self.video_display = mmap.mmap(
            self.fd, VIDEO_FRAME_BYTES * 3, flags=mmap.MAP_SHARED,
            prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=VIDEO_DISPLAY_BASE)
        self.pose_capture = mmap.mmap(
            self.fd, POSE_FRAME_BYTES * 3, flags=mmap.MAP_SHARED,
            prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=POSE_CAPTURE_BASE)
        self.display_views = [
            np.ndarray((VIDEO_H, VIDEO_W, 3), np.uint8,
                       buffer=self.video_display, offset=index * VIDEO_FRAME_BYTES)
            for index in range(3)
        ]

    @staticmethod
    def _current_write(regs):
        return (struct.unpack_from("<I", regs, VDMA_PARKPTR)[0] >> 24) & 0x1f

    @staticmethod
    def _current_read(regs):
        return (struct.unpack_from("<I", regs, VDMA_PARKPTR)[0] >> 16) & 0x1f

    def read(self):
        pose_current = self._current_write(self.pose_regs) % 3
        pose_completed = (pose_current + 2) % 3
        pose = np.ndarray(
            (INPUT_H, INPUT_W, 3), np.uint8, buffer=self.pose_capture,
            offset=pose_completed * POSE_FRAME_BYTES).copy()

        video_current = self._current_write(self.video_regs) % 3
        video_completed = (video_current + 2) % 3
        active_display = self._current_read(self.video_regs) % 3
        display_target = (active_display + 1) % 3
        capture = np.ndarray(
            (VIDEO_H, VIDEO_W, 3), np.uint8, buffer=self.video_capture,
            offset=video_completed * VIDEO_FRAME_BYTES)
        display = self.display_views[display_target]
        np.copyto(display, capture)
        return True, pose, display, display_target

    def present(self, display_target):
        # Switch MM2S to park mode only after the complete overlay is ready.
        control = struct.unpack_from("<I", self.video_regs, 0x00)[0]
        struct.pack_into("<I", self.video_regs, 0x00, control & ~0x2)
        park = struct.unpack_from("<I", self.video_regs, VDMA_PARKPTR)[0]
        struct.pack_into("<I", self.video_regs, VDMA_PARKPTR,
                         (park & ~0x1f) | (display_target & 0x1f))

    def release(self):
        self.display_views.clear()
        for region in (self.pose_capture, self.video_display, self.video_capture,
                       self.pose_regs, self.video_regs):
            try:
                region.close()
            except BufferError:
                pass
        os.close(self.fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-xmodel",type=Path,required=True)
    parser.add_argument("--wrist-xmodel",type=Path,required=True)
    parser.add_argument("--arm-decoder",type=Path,required=True)
    parser.add_argument("--camera",default="0")
    parser.add_argument("--temporal-weight",type=float,default=.35)
    parser.add_argument("--min-forearm-ratio",type=float,default=.45)
    parser.add_argument("--down-pose-weight",type=float,default=.5)
    parser.add_argument("--min-confidence",type=float,default=0.0)
    parser.add_argument("--headless",action="store_true")
    args=parser.parse_args()
    baseline,wrist=DpuPoseModel(args.baseline_xmodel),DpuPoseModel(args.wrist_xmodel)
    decoder=ArmChainDecoder(args.arm_decoder,args.temporal_weight,args.min_forearm_ratio,args.down_pose_weight)
    use_vdma=args.camera.lower()=="vdma"
    if use_vdma:
        camera=VdmaCamera()
        args.headless=True
    else:
        source=int(args.camera) if args.camera.isdigit() else args.camera
        camera=cv2.VideoCapture(source)
        if not camera.isOpened(): raise RuntimeError(f"cannot open camera/source {source}")
    fps=0.0; last=time.perf_counter()
    report=last
    while True:
        if use_vdma:
            ok,model_frame,frame,display_target=camera.read()
            box=(0,0,VIDEO_W,VIDEO_H)
        else:
            ok,frame=camera.read()
            model_frame,box=center_crop(frame)
        if not ok: break
        image=preprocess(model_frame)
        base_logits=baseline(image); wrist_logits=wrist(image)
        points,confidence,ratios,down=decoder.decode(base_logits,wrist_logits)
        points=map_frame(points,box); points=decoder.stabilize(points)
        draw(frame,points,confidence,args.min_confidence)
        now=time.perf_counter(); fps=.9*fps+.1/(now-last); last=now
        mode="ARM-CHAIN+DOWN" if down else "ARM-CHAIN"
        cv2.putText(frame,f"{mode} {fps:.1f} FPS",(12,28),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,255,0),2,cv2.LINE_AA)
        cv2.putText(frame,f"forearm L/R {ratios[0]:.2f}/{ratios[1]:.2f}",(12,54),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,255,255),1,cv2.LINE_AA)
        if use_vdma:
            camera.present(display_target)
        if args.headless:
            if now-report>=1.0:
                print(f"{mode} {fps:.1f} FPS forearm={ratios[0]:.2f}/{ratios[1]:.2f}",flush=True)
                report=now
        else:
            cv2.imshow("DPU ARM-CHAIN",frame)
            key=cv2.waitKey(1)&0xff
            if key in (27,ord('q')): break
            if key==ord('r'): decoder.reset()
    camera.release(); cv2.destroyAllWindows()


if __name__ == "__main__": main()
