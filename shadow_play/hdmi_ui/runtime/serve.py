#!/usr/bin/env python3
"""Local UI plus explicit USB/DPU capture bridge; no motor output API."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import hashlib
import hmac
import signal
from urllib.parse import urlsplit
from board_service import BoardBridge, BoardCamera, Unavailable

APP = "shadow-theatre-hdmi"
ROOT = Path(__file__).resolve().parent / "web"

class Handler(SimpleHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def allowed_host(self):
        port = self.server.server_address[1]
        return self.headers.get('Host') in ('127.0.0.1:%d' % port, 'localhost:%d' % port)

    def send_json(self, data, status=200):
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        super().end_headers()

    def do_GET(self):
        if not self.allowed_host():
            return self.send_json({'error': 'invalid host'}, 403)
        route = urlsplit(self.path).path
        if route == '/api/status':
            return self.send_json(self.server.bridge.status())
        if route == '/api/camera/frame':
            try:
                return self.send_json(self.server.bridge.camera.frame())
            except Unavailable as error:
                return self.send_json({'error': str(error)}, 503)
        if route.startswith('/api/'):
            return self.send_json({'error': 'unknown API'}, 404)
        if self.path.split("?", 1)[0] == "/health.json":
            data = json.dumps({"app": APP, "ui": "1024x600", "ok": True,
                               "ui_sha256": hashlib.sha256((ROOT / 'index.html').read_bytes()).hexdigest()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self):
        origin = self.headers.get('Origin')
        expected = 'http://' + self.headers.get('Host', '')
        token = self.headers.get('X-Shadow-Token', '')
        if (not self.allowed_host() or origin != expected or
                not hmac.compare_digest(token, self.server.bridge.token)):
            return self.send_json({'error': '同源校验失败，请重新打开板端页面'}, 403)
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, TypeError):
            return self.send_json({'error': '无效请求'}, 400)
        route = urlsplit(self.path).path
        try:
            if route == '/api/camera/start':
                self.server.bridge.camera.start()
            elif route == '/api/camera/stop':
                self.server.bridge.camera.stop()
            elif route == '/api/control':
                self.server.bridge.control(body)
            else:
                return self.send_json({'error': 'unknown API'}, 404)
            return self.send_json({'ok': True})
        except Unavailable as error:
            return self.send_json({'ok': False, 'error': str(error)}, 409)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", choices=['127.0.0.1'])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument('--camera-runner', type=Path,
                        default=Path(__file__).resolve().parents[2] / 'tools/run_usb_follow.sh')
    args = parser.parse_args()
    if not (ROOT / "index.html").is_file():
        parser.error("Missing runtime/web/index.html; extract the complete package first.")
    server = ThreadingHTTPServer((args.bind, args.port), partial(Handler, directory=str(ROOT)))
    server.bridge = BoardBridge(BoardCamera(args.camera_runner))
    def terminate(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    print("Shadow theatre: http://%s:%s/" % (args.bind, args.port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.bridge.close()

if __name__ == "__main__":
    main()
