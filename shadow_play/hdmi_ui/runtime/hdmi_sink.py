"""Display fresh browser packets through the existing reviewed HDMI driver.

No browser, network, camera, PWM, or rail commands in this process.
"""
import argparse
from pathlib import Path
import signal
import sys
import time

from browser_display import PacketReader, decode_frame, VIEW, OUTPUT


def main():
    import cv2
    import numpy as np
    cv2.setNumThreads(2)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'integrations/follow'))
    from usb_hdmi import UsbHdmiDisplay
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, default=Path('/run/shadow-ui/frame.bin'))
    args = parser.parse_args()
    stopping = False

    def stop(*unused):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    display = UsbHdmiDisplay()  # Rejects an unreviewed/missing PL image marker.
    blank = np.full((OUTPUT[1], OUTPUT[0], 3), (15, 20, 25), dtype=np.uint8)
    cv2.putText(blank, 'Waiting for theatre UI...', (340, 360), cv2.FONT_HERSHEY_SIMPLEX, 1, (170, 190, 210), 2)
    current = previous = None
    reader = PacketReader(args.packet)
    width = round(VIEW[0]*OUTPUT[1]/VIEW[1])
    left = (OUTPUT[0]-width)//2
    output = np.zeros_like(blank)
    frames, report, decode_ms, present_ms = 0, time.monotonic(), 0., 0.
    try:
        display.start(blank)
        while not stopping:
            try:
                captured, jpeg = reader.read()
                if jpeg is not None:
                    if jpeg != previous:
                        began = time.monotonic()
                        frame = decode_frame(jpeg)
                        if frame is None or frame.shape != (VIEW[1], VIEW[0], 3):
                            raise ValueError('Unexpected browser viewport')
                        cv2.resize(frame, (width, OUTPUT[1]), dst=output[:,left:left+width])
                        prepared = time.monotonic()
                        display.present(output)
                        shown = time.monotonic()
                        decode_ms += (prepared-began)*1000
                        present_ms += (shown-prepared)*1000
                        frames += 1
                        previous = jpeg
                    current = captured
            except (OSError, ValueError):
                if current is not None:
                    display.present(blank)
                    current = previous = None
            now = time.monotonic()
            if now-report >= 10:
                import json
                print(json.dumps(dict(event='hdmi_frames', fps=round(frames/(now-report),2),
                    prepare_ms=round(decode_ms/max(frames,1),2), present_ms=round(present_ms/max(frames,1),2))),flush=True)
                frames, report, decode_ms, present_ms = 0, now, 0., 0.
            time.sleep(.003)
    finally:
        try: display.restore()
        finally: display.close()


if __name__ == '__main__':
    main()
