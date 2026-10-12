#!/usr/bin/env python3
"""Offline torso texture rotation/translation diagnostic, not joint feedback."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def rigid_match(before, after, center=(221,184), half_size=(7,14), search=28,
                angles=range(-36,37,3)):
    x,y=center;rx,ry=half_size
    side=2*(max(rx,ry)+5)+1;mid=side//2
    tile=Image.new('L',(side,side),0)
    tile.paste(Image.fromarray(before[y-ry:y+ry+1,x-rx:x+rx+1]),(mid-rx,mid-ry))
    mask=Image.new('L',(side,side),0)
    mask.paste(255,(mid-rx,mid-ry,mid+rx+1,mid+ry+1))
    region=after[y-mid-search:y+mid+search+1,x-mid-search:x+mid+search+1].astype(np.float64)
    if region.shape != (side+2*search,)*2:
        raise ValueError('Search crosses image edge')
    windows=np.lib.stride_tricks.sliding_window_view(region,(side,side))
    best=None
    for angle in angles:
        w=np.asarray(mask.rotate(angle,resample=Image.Resampling.BILINEAR,center=(mid,mid)),dtype=np.float64)/255
        t=np.asarray(tile.rotate(angle,resample=Image.Resampling.BILINEAR,center=(mid,mid)),dtype=np.float64)
        # Avoid dark interpolation outside the source patch at rotated edges.
        w=(w>.99).astype(np.float64)
        n=w.sum();mean=(t*w).sum()/n;target=(t-mean)*w
        norm=float(np.sqrt((target*target).sum()))
        if norm<1e-6:raise ValueError('Flat torso texture')
        sums=np.einsum('ijab,ab->ij',windows,w,optimize=True)
        squares=np.einsum('ijab,ab->ij',windows*windows,w,optimize=True)
        variance=np.maximum(squares-sums*sums/n,0)
        numerator=np.einsum('ijab,ab->ij',windows,target,optimize=True)
        # A nearly flat candidate has no meaningful correlation. Reject it;
        # cancellation in variance must never produce a spurious huge score.
        score=np.divide(numerator,np.sqrt(variance)*norm,
                        out=np.full_like(numerator,-1),where=variance>n)
        iy,ix=np.unravel_index(np.argmax(score),score.shape)
        row=dict(rotation_ccw_deg=int(angle),dx=int(ix-search),dy=int(iy-search),
                 ncc=round(float(score[iy,ix]),4))
        if best is None or row['ncc']>best['ncc']:best=row
    best['search_boundary_reached']=abs(best['dx'])==search or abs(best['dy'])==search
    best['angle_boundary_reached']=best['rotation_ccw_deg'] in (min(angles),max(angles))
    best['usable_texture_match']=best['ncc']>=.8 and not best['search_boundary_reached'] and not best['angle_boundary_reached']
    return best


def analyze(selection_path):
    selection=json.loads(selection_path.read_text(encoding='utf-8-sig'))
    root=selection_path.parent.parent
    images=[np.asarray(Image.open(root/r['file']).convert('L'))
            for r in selection['views']['front']['frames']]
    if any(im.shape!=(360,640) for im in images):raise ValueError('Requires inspected 640x360 view')
    parts={}
    for name,center,half in [('upper_torso',(221,184),(7,14)),('waist_clothing',(221,211),(10,8))]:
        parts[name]={'center_pixel':list(center),
                     'peak':rigid_match(images[0],images[1],center,half),
                     'return':rigid_match(images[0],images[2],center,half)}
    return {'selection':str(selection_path),'stage_id':selection['axis'],
            'vector_us':selection['events'][1].get('vector_us'),'parts':parts,
            'interpretation':'Rigid appearance change only; fabric/depth/joint motion may break this model',
            'verified_joint_angles':False,'metric_calibration':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('selection',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();result=analyze(args.selection)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
