"""Offline pixel-change review of a fixed-camera gimbal closeup.

This is advisory evidence, not an angle sensor, collision detector, or motion
authorization. Images that changed are not automatically a valid calibration.
No hardware driver is imported and no motor/camera operation is performed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter


def patch(image, roi, dx=0, dy=0):
    x,y,w,h=roi
    if (any(type(v) is not int for v in roi) or w<16 or h<16 or
            min(x+dx,y+dy)<0 or x+dx+w>image.shape[1] or y+dy+h>image.shape[0]):
        raise ValueError('Bounded integer ROI of at least 16x16 required')
    return image[y+dy:y+dy+h,x+dx:x+dx+w]


def compare(before, after, fixed_roi, moving_roi, max_shift=6):
    if before.shape!=after.shape or before.ndim!=2 or not np.isfinite(before).all() or not np.isfinite(after).all():
        raise ValueError('Two finite grayscale images of the same shape required')
    if type(max_shift) is not int or not 0<=max_shift<=12:
        raise ValueError('Bounded camera-jitter search required')
    fixed=patch(before,fixed_roi);moving=patch(before,moving_roi)
    receipt={'angle_feedback':None,'automatic_motion_allowed':False,
             'fixed_roi':list(fixed_roi),'moving_roi':list(moving_roi)}
    if min(float(fixed.std()),float(moving.std()))<.025:
        return dict(receipt,verdict='unresolved',reason='Insufficient image texture or contrast')
    centered=fixed-fixed.mean();denominator=float(np.linalg.norm(centered))
    best=None
    for dy in range(-max_shift,max_shift+1):
        for dx in range(-max_shift,max_shift+1):
            try:candidate=patch(after,fixed_roi,dx,dy)
            except ValueError:continue
            c=candidate-candidate.mean();norm=float(np.linalg.norm(c))
            score=float(np.sum(centered*c)/(denominator*norm)) if norm>.0001 else -1
            if best is None or score>best[0]:best=(score,dx,dy,candidate)
    if best is None or best[0]<.90:
        return dict(receipt,verdict='unresolved',reason='Fixed reference did not register reliably')
    score,dx,dy,candidate=best
    if max_shift and max(abs(dx),abs(dy))==max_shift:
        return dict(receipt,verdict='unresolved',reason='Camera shift reached the search boundary')
    try:shifted=patch(after,moving_roi,dx,dy)
    except ValueError:return dict(receipt,verdict='unresolved',reason='Registered moving ROI outside image')
    variance=float(candidate.var())
    gain=float(np.mean((candidate-candidate.mean())*centered)/variance)
    offset=float(fixed.mean()-gain*candidate.mean())
    if not .7<=gain<=1.4:
        return dict(receipt,verdict='unresolved',reason='Illumination changed too much')
    noise=float(np.sqrt(np.mean((fixed-(gain*candidate+offset))**2)))
    change=float(np.sqrt(np.mean((moving-(gain*shifted+offset))**2)))
    threshold=max(.015,3*noise)
    return dict(receipt,verdict='visible_pixel_change' if change>threshold else 'no_clear_pixel_change',
                camera_shift_pixels=[dx,dy],fixed_correlation=score,
                fixed_noise_rms=noise,moving_change_rms=change,change_threshold=threshold,
                reason='Pixel comparison requires a human review of axis motion and linkage')


def read_image(path):
    with Image.open(path) as im:
        return np.asarray(im.convert('L').filter(ImageFilter.GaussianBlur(.8)),dtype=np.float64)/255


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('before',type=Path);p.add_argument('after',type=Path)
    p.add_argument('--fixed-roi',nargs=4,type=int,required=True)
    p.add_argument('--moving-roi',nargs=4,type=int,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=compare(read_image(a.before),read_image(a.after),a.fixed_roi,a.moving_roi)
    result['frame_sha256']=[hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.before,a.after)]
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
