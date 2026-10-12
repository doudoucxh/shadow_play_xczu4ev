"""Read-only Sony SDK / Camo snapshot gateway for the Ubuntu capture GUI.

No shutter or motor APIs. Bind to the VMware host-only/NAT interface for the VM;
the default is loopback. A producer timestamp and identity accompany each JPEG.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid
from PIL import Image, ImageStat


def utc_ms(value):
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec='milliseconds')


def check_jpeg(data):
    if not 4 <= len(data) <= 8 * 1024 * 1024:
        raise ValueError('Invalid JPEG size')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'JPEG':
            raise ValueError('Expected JPEG')
        image.load()
        thumbnail = image.convert('RGB'); thumbnail.thumbnail((64, 64))
        if max(ImageStat.Stat(thumbnail).stddev) < 2:
            raise ValueError('Camera returned a blank/uniform frame; check the actual preview')
    return data


class SonySource:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def read(self):
        pointer = json.loads((self.root / 'current.json').read_text(encoding='utf-8-sig'))
        folder = Path(pointer['directory']).resolve()
        if folder.parent != self.root:
            raise ValueError('Unexpected Sony session path')
        # A changing status indicates a concurrent SDK frame update: retry later.
        before = (folder / 'status.json').read_bytes()
        state = json.loads(before)
        data = (folder / 'latest.jpg').read_bytes()
        if (folder / 'status.json').read_bytes() != before:
            raise ValueError('Sony frame changed while reading; retry on the next poll')
        age = time.time() * 1000 - state['updated_unix_ms']
        if state['state'] != 'streaming' or not 0 <= age <= 1500:
            raise ValueError('Sony SDK stream stopped or stale; restart start_liveview.ps1')
        return check_jpeg(data), folder.name + '-' + str(state['frames']), int(age), utc_ms(state['updated_unix_ms'])


class CamoSource:
    def __init__(self, ffmpeg, device, log_path):
        self.lock = threading.Lock()
        self.frame = None
        self.error = 'Waiting for the first Camo frame'
        self.identity = uuid.uuid4().hex
        self.log = Path(log_path).open('ab')
        command = [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-f', 'dshow',
                   '-pixel_format', 'yuyv422', '-video_size', '1280x720', '-framerate', '30',
                   '-i', 'video=' + device, '-an', '-vf', 'fps=15,scale=960:-2',
                   '-c:v', 'mjpeg', '-q:v', '4', '-f', 'image2pipe', 'pipe:1']
        self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=self.log,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        buffer = bytearray(); number = 0
        try:
            while True:
                chunk = self.process.stdout.read1(65536)
                if not chunk:
                    raise ValueError('Camo capture process stopped; inspect camo-ffmpeg.log')
                buffer.extend(chunk)
                if len(buffer) > 8 * 1024 * 1024:
                    raise ValueError('Camo frame stream exceeds size limit')
                while True:
                    start = buffer.find(b'\xff\xd8'); end = buffer.find(b'\xff\xd9', max(start, 0))
                    if start < 0 or end < 0:
                        break
                    data = bytes(buffer[start:end+2]); del buffer[:end+2]
                    try:
                        check_jpeg(data)
                        number += 1; captured = time.time()*1000
                        with self.lock:
                            self.frame = (data, self.identity+'-'+str(number), time.monotonic(), utc_ms(captured))
                            self.error = ''
                    except Exception as error:
                        with self.lock:
                            self.error = str(error)
        except Exception as error:
            with self.lock:
                self.error = str(error)

    def read(self):
        with self.lock:
            if self.error or self.frame is None:
                raise ValueError(self.error)
            data, identity, stamp, utc = self.frame
        age = int((time.monotonic()-stamp)*1000)
        if age > 1500:
            raise ValueError('Camo producer stopped updating')
        return data, identity, age, utc

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=3)
        self.thread.join(timeout=2)
        self.log.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        source = self.server.sources.get(self.path)
        if source is None:
            self.send_error(404); return
        try:
            data, identity, age, utc = source.read()
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Frame-Id', identity)
            self.send_header('X-Frame-Age-Ms', str(age))
            self.send_header('X-Frame-Read-At', utc)
            self.end_headers(); self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            self.send_error(503, str(error))

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sony-output', required=True, type=Path)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--camo-device', default='Camo')
    parser.add_argument('--no-camo', action='store_true')
    parser.add_argument('--log-dir', type=Path, required=True)
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)
    camo = None
    with ThreadingHTTPServer((args.bind, args.port), Handler) as server:
        server.sources = {'/front.jpg': SonySource(args.sony_output)}
        if not args.no_camo:
            camo = CamoSource(args.ffmpeg, args.camo_device, args.log_dir/'camo-ffmpeg.log')
            server.sources['/top.jpg'] = camo
        print('FRAME GATEWAY READY http://{}:{}/front.jpg'.format(args.bind,args.port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            if camo:
                camo.close()


if __name__ == '__main__':
    main()
