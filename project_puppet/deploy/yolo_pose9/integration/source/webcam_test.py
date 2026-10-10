"""Live PC camera test with the release CNN and shared OV5640 preprocessing."""
import argparse
import json
import time
from pathlib import Path
import cv2
import numpy as np
import torch
from raw_model import load_raw
from postprocess import preprocess, decode

ROOT = Path(__file__).resolve().parent
TITLE = 'YOLO Pose 9 | OV5640 pipeline preview | Q/ESC exit'
EDGES = [(0,1),(0,2),(1,2),(1,3),(3,5),(2,4),(4,6),(1,7),(2,8),(7,8)]
LABELS = ['Head','L shoulder','R shoulder','L elbow','R elbow','L wrist','R wrist','L hip','R hip']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--camera',type=int,default=0)
    p.add_argument('--raw',type=Path,default=ROOT/'release/raw')
    a = p.parse_args()
    torch.set_num_threads(4)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = load_raw(a.raw).to(device).eval()
    size = json.loads((a.raw/'architecture.json').read_text())['input_shape'][-1]
    with torch.inference_mode():
        model(torch.zeros(1,3,size,size,device=device))
    cap = None
    for backend in (cv2.CAP_DSHOW,cv2.CAP_MSMF):
        trial = cv2.VideoCapture(a.camera,backend)
        trial.set(cv2.CAP_PROP_FRAME_WIDTH,1280)
        trial.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
        trial.set(cv2.CAP_PROP_FPS,30)
        ok,frame = trial.read()
        if ok:
            cap = trial
            break
        trial.release()
    if cap is None:
        raise RuntimeError('Cannot read webcam. Close other camera applications and retry.')
    cv2.namedWindow(TITLE,cv2.WINDOW_NORMAL)
    cv2.resizeWindow(TITLE,1152,648)
    print(json.dumps({'status':'camera_open','camera':a.camera,'resolution':[frame.shape[1],frame.shape[0]],'device':device,'model':'trained YOLOv8n ReLU pose9 FP32','recording':False}),flush=True)
    count,missing = 0,0
    start=last_report=time.perf_counter()
    mirror=False
    try:
        with torch.inference_mode():
            while True:
                tick=time.perf_counter()
                ok,frame=cap.read()
                if not ok:
                    raise RuntimeError('Camera stopped returning frames')
                x,transform=preprocess(frame,size)
                outputs=[o.cpu().numpy() for o in model(torch.from_numpy(x).to(device))]
                boxes,scores,points=decode(outputs,transform)
                count+=1
                missing+=int(not len(scores))
                if len(scores):
                    pose=points[0]
                    good=pose[:,2]>=0.25
                    box=boxes[0].astype(int)
                    cv2.rectangle(frame,tuple(box[:2]),tuple(box[2:]),(80,220,80),2)
                    for i,j in EDGES:
                        if good[i] and good[j]:
                            cv2.line(frame,tuple(pose[i,:2].astype(int)),tuple(pose[j,:2].astype(int)),(0,240,100),3,cv2.LINE_AA)
                    for i in np.flatnonzero(good):
                        xy=tuple(pose[i,:2].astype(int))
                        cv2.circle(frame,xy,5,(0,230,255),-1,cv2.LINE_AA)
                        cv2.putText(frame,LABELS[i],(xy[0]+7,xy[1]-7),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1,cv2.LINE_AA)
                if mirror:
                    frame=cv2.flip(frame,1)
                elapsed=time.perf_counter()-tick
                text=f'YOLO9 FP32 | {1/max(elapsed,1e-6):.1f} PC FPS | person {float(scores[0]) if len(scores) else 0:.2f}'
                cv2.rectangle(frame,(0,0),(frame.shape[1],64),(30,30,30),-1)
                cv2.putText(frame,text,(12,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),1,cv2.LINE_AA)
                cv2.putText(frame,'Full frame -> RGB letterbox 384 | M: mirror | Q/ESC: quit | No recording',(12,51),cv2.FONT_HERSHEY_SIMPLEX,.48,(220,220,220),1,cv2.LINE_AA)
                cv2.imshow(TITLE,frame)
                now=time.perf_counter()
                if now-last_report>=2:
                    print(json.dumps({'status':'running','frames':count,'fps_average':count/(now-start),
                        'missing_frames':missing,'person_confidence':float(scores[0]) if len(scores) else 0,
                        'visible_keypoints':int((points[0,:,2]>=.25).sum()) if len(scores) else 0}),flush=True)
                    last_report=now
                key=cv2.waitKey(1)&255
                if key in (27,ord('q')) or cv2.getWindowProperty(TITLE,cv2.WND_PROP_VISIBLE)<1:
                    break
                if key==ord('m'): mirror=not mirror
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(json.dumps({'status':'closed','frames':count}),flush=True)


if __name__=='__main__': main()
