"""Fine-tune YOLOv8n pose with a ReLU CNN and project nine-point labels."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ['YOLO_CONFIG_DIR'] = str(ROOT / '.ultralytics')
os.environ['MPLCONFIGDIR'] = str(ROOT / '.matplotlib')


def main():
    import torch
    import yaml
    import ultralytics
    from ultralytics import YOLO
    p = argparse.ArgumentParser()
    p.add_argument('--epochs', type=int, default=60)
    p.add_argument('--imgsz', type=int, default=384)
    p.add_argument('--batch', type=int, default=16)
    p.add_argument('--name', default='yolov8n_relu_pose9')
    p.add_argument('--init-only', action='store_true')
    p.add_argument('--resume', type=Path)
    a = p.parse_args()
    torch.set_num_threads(8)
    if a.resume:
        YOLO(str(a.resume)).train(resume=True, workers=0, cache='ram')
        return
    cfg = yaml.safe_load((Path(ultralytics.__file__).parent / 'cfg/models/v8/yolov8-pose.yaml').read_text())
    cfg.update(kpt_shape=[9, 3], scale='n', activation='nn.ReLU()')
    config = ROOT / 'yolov8n-pose9-relu.yaml'
    config.write_text(yaml.safe_dump(cfg), encoding='utf-8')
    model = YOLO(str(config), task='pose').load(str(ROOT / 'weights/yolov8n-pose.pt'))
    model.save(str(ROOT / 'weights/initialized_pose9_relu.pt'))
    (ROOT / 'environment.json').write_text(json.dumps({
        'torch': torch.__version__, 'ultralytics': ultralytics.__version__,
        'gpu': torch.cuda.get_device_name(0), 'activation': 'ReLU',
        'source': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt',
        'status': 'Adapted Ultralytics YOLOv8n; not an AMD official pose model.'}, indent=2))
    if a.init_only:
        return
    model.train(data=str(ROOT / 'dataset/data.yaml'), epochs=a.epochs,
        imgsz=a.imgsz, batch=a.batch, device=0, workers=0,
        project=str(ROOT / 'runs'), name=a.name, exist_ok=False,
        optimizer='AdamW', lr0=0.001, lrf=0.05, weight_decay=0.0005,
        warmup_epochs=3, patience=20, seed=20260922, deterministic=True,
        amp=True, cache='ram', rect=False, mosaic=0.0, mixup=0.0,
        degrees=8, translate=0.1, scale=0.3, fliplr=0.5, flipud=0.0,
        hsv_h=0.015, hsv_s=0.3, hsv_v=0.3, close_mosaic=0,
        plots=True, save_period=10)


if __name__ == '__main__':
    main()
