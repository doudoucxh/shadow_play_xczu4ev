"""Display fresh browser packets through the existing reviewed HDMI driver.

No browser, network, camera, PWM, or rail commands in this process.
"""
import argparse
from pathlib import Path
import signal
import sys
import time

from browser_display import read_packet, VIEW, OUTPUT


def main():
    import cv2
    import numpy as np
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
    current = None
    try:
        display.start(blank)
        while not stopping:
            try:
                captured, jpeg = read_packet(args.packet, time.monotonic())
                if captured != current:
                    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                    if frame is None or frame.shape != (VIEW[1], VIEW[0], 3):
                        raise ValueError('Unexpected browser viewport')
                    width = round(VIEW[0]*OUTPUT[1]/VIEW[1])
                    output = np.zeros_like(blank)
                    left = (OUTPUT[0]-width)//2
                    output[:, left:left+width] = cv2.resize(frame, (width, OUTPUT[1]))
                    display.present(output)
                    current = captured
            except (OSError, ValueError):
                if current is not None:
                    display.present(blank)
                    current = None
            time.sleep(.015)
    finally:
        try: display.restore()
        finally: display.close()


if __name__ == '__main__':
    main()
