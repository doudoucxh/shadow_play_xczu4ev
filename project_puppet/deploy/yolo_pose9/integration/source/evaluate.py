"""Common full-frame evaluation; missing detections/keypoints count as failures."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
import cv2
import numpy as np
import torch
from raw_model import load_raw
from postprocess import preprocess, decode


def load_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summarize(rows):
    gt=np.array([r['gt'] for r in rows])
    pred=np.array([r['prediction'] for r in rows])
    dims=np.array([[r['width'],r['height']] for r in rows])
    vis=gt[:,:,2]>0
    valid=pred[:,:,2]>=0.25
    err=np.linalg.norm((pred[:,:,:2]-gt[:,:,:2])/dims[:,None,:]*[256,144],axis=2)
    success=(err<=12)&valid
    shoulder=np.linalg.norm(gt[:,1,:2]-gt[:,2,:2],axis=1)
    normerr=np.linalg.norm(pred[:,:,:2]-gt[:,:,:2],axis=2)/np.maximum(shoulder[:,None],1)
    result={'frames':len(rows),'metric_definition':'PCK12 on full-frame coordinates scaled to 256x144; differs from old GT-crop PCK12.',
            'detected_frames':sum(r['detected'] for r in rows),
            'keypoint_confidence_threshold':0.25,
            'all_pck12':float(success[vis].mean()),
            'valid_keypoint_coverage':float(valid[vis].mean())}
    for name,indices in [('elbow',[3,4]),('wrist',[5,6]),('all',list(range(9)))]:
        mask=vis[:,indices]
        result[name+'_pck12']=float(success[:,indices][mask].mean())
        both=mask&valid[:,indices]
        result[name+'_mean_error_detected_256x144_px']=float(err[:,indices][both].mean()) if both.any() else None
    chain=[]
    for indices in ([3,5],[4,6]):
        eligible=vis[:,indices].all(axis=1)
        chain.extend(success[:,indices].all(axis=1)[eligible].tolist())
    result['arm_chain_pck12']=float(np.mean(chain)) if chain else None
    eligible=vis[:,[3,4,5,6]].all(axis=1)
    result['both_arms_pck12']=float(success[:,[3,4,5,6]].all(axis=1)[eligible].mean()) if eligible.any() else None
    smask=vis & vis[:,1:2]&vis[:,2:3]&(shoulder[:,None]>=10)
    result['pck_at_0_2_shoulder_span']=float(((normerr<=0.2)&valid)[smask].mean()) if smask.any() else None
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',type=Path,default=Path(__file__).parent/'dataset')
    p.add_argument('--raw',type=Path)
    p.add_argument('--legacy',action='store_true')
    p.add_argument('--split',choices=['val','test'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--device',default='cpu')
    p.add_argument('--legacy-root',type=Path,default=Path('D:/xilinx_project/ZYNQ_project/project_puppet/project_puppet/deploy/dpu_arm_chain'))
    a=p.parse_args()
    torch.set_num_threads(4)
    records=json.loads((a.dataset/'records.json').read_text(encoding='utf-8'))[a.split]
    if a.legacy:
        m=load_file('legacy_model',a.legacy_root/'reference_source/model.py')
        rt=load_file('legacy_runtime',a.legacy_root/'runtime/arm_chain_dpu.py')
        nets=[]
        for weight in ('D:/pytorch_work/pose_model/runs/Data_004_baseline_40/best.pt',
                       'D:/pytorch_work/pose_model/runs/Data_004_wrist_repair/candidate_best.pt'):
            net=m.make_pose_model('v2')
            net.load_state_dict(torch.load(weight,map_location='cpu',weights_only=True)['model'])
            nets.append(net.eval())
        decoder=rt.ArmChainDecoder(a.legacy_root/'decoder/arm_chain_ranker.npz')
    else:
        model=load_raw(a.raw).to(a.device)
        size=json.loads((a.raw/'architecture.json').read_text())['input_shape'][-1]
    rows=[]
    for i,r in enumerate(records):
        # cv2.imread uses the active ANSI code page on some Windows builds.
        frame=cv2.imdecode(np.fromfile(r['file'],dtype=np.uint8),cv2.IMREAD_COLOR)
        if frame is None: raise ValueError(r['file'])
        with torch.no_grad():
            if a.legacy:
                decoder.reset()  # Independent stills: no false temporal adjacency.
                x=torch.from_numpy(rt.preprocess(frame))
                logits=[net(x).numpy() for net in nets]
                xy,confidence,_,_=decoder.decode(*logits)
                xy=xy*np.array([r['width']/256,r['height']/144])
                # Old heatmap-peak probabilities are not calibrated keypoint scores.
                # Evaluate its always-output geometry, matching old default min-confidence=0.
                pred=np.concatenate((xy,np.ones((9,1))),axis=1)
                detected=True
            else:
                x,trans=preprocess(frame,size)
                outputs=[o.cpu().numpy() for o in model(torch.from_numpy(x).to(a.device))]
                boxes,scores,kpts=decode(outputs,trans)
                detected=bool(len(scores))
                pred=kpts[0] if detected else np.zeros((9,3))
        row={**r,'prediction':pred.tolist(),'detected':detected,
             'gt':[[p['x'],p['y'],p['v']] for p in r['points']]}
        rows.append(row)
        if i%50==0: print(f'{i+1}/{len(records)}',flush=True)
    report=summarize(rows)
    report.update(split=a.split,model='legacy_dual_v2' if a.legacy else str(a.raw),
                  temporal_smoothing=False,
                  legacy_confidence_policy='always-output geometry (legacy deployment default)' if a.legacy else None)
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'metrics.json').write_text(json.dumps(report,indent=2))
    (a.output/'predictions.json').write_text(json.dumps(rows),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
