"""Assemble a deterministic reviewable training/deployment handoff."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'release/package'
FILES={
    'model/yolo_pose9_b4096.xmodel':'release/int8/compiled/yolo_pose9.xmodel',
    'model/graph_audit.json':'release/int8/compiled/graph_audit.json',
    'model/compiler_meta.json':'release/int8/compiled/meta.json',
    'model/quant_info.json':'release/int8/quant_info.json',
    'model/calibration_images.json':'release/int8/calibration_images.json',
    'model/raw_architecture.json':'release/raw/architecture.json',
    'model/raw_weights.npz':'release/raw/weights.npz',
    'model/fp32_equivalence.json':'release/raw/equivalence.json',
    'training/best.pt':'runs/yolov8n_relu_pose9/weights/best.pt',
    'training/data_audit.json':'dataset/audit.json',
    'training/environment.json':'environment.json',
    'runtime/runtime.py':'runtime.py',
    'runtime/postprocess.py':'postprocess.py',
    'runtime/requirements-target.txt':'requirements-target.txt',
    'evaluation/legacy_val.json':'evaluation/legacy_val/metrics.json',
    'evaluation/legacy_test.json':'evaluation/legacy_test/metrics.json',
    'evaluation/fp32_val.json':'evaluation/fp32_val/metrics.json',
    'evaluation/fp32_test.json':'evaluation/fp32_test/metrics.json',
    'evaluation/int8_val.json':'evaluation/int8_val/metrics.json',
    'evaluation/int8_test.json':'evaluation/int8_test/metrics.json',
    'REPORT.md':'REPORT.md',
    'THIRD_PARTY.md':'THIRD_PARTY.md',
}
manifest={'release':'yolov8n-pose9-relu-v1-b4096','files':{}}
for dest,source in FILES.items():
    src=ROOT/source
    if not src.is_file(): raise FileNotFoundError(src)
    dst=OUT/dest
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
    data=dst.read_bytes()
    manifest['files'][dest]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
