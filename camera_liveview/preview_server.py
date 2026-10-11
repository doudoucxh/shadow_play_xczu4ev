"""Local browser preview of the running Sony SDK session; no camera/motor commands."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] /
                       'shadow_play' / 'integrations' / 'calibration'))
from camera_bridge import SonySource


PAGE = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sony 正面实时取景</title>
<style>
body{margin:0;background:#10151c;color:#ecf2fa;font:16px system-ui,sans-serif}
header{padding:18px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
h1{font-size:20px;margin:0}button{font:inherit;border:1px solid #566272;border-radius:6px;
padding:7px 14px;background:#242d39;color:inherit;cursor:pointer}
#status{color:#ffca80}#status.live{color:#86e4b0}
main{position:relative;background:#070a0e;height:calc(100vh - 145px);min-height:240px;
display:flex;align-items:center;justify-content:center}
img{width:100%;height:100%;object-fit:contain}img[hidden]{display:none}
#notice{position:absolute;background:#202936;padding:16px;border-radius:8px}
footer{padding:12px 24px;font-size:14px;color:#a9b9cb}
</style>
<header><h1>Sony 正面实时取景</h1><span id="status">正在读取…</span>
<button id="pause">暂停显示</button><button id="full">全屏</button></header>
<main id="screen"><img id="view" alt="Sony 实时画面" hidden>
<div id="notice">等待新画面…</div></main>
<footer id="detail">读取现有 SDK 取景 · 约 5 帧/秒 · 不控制舵机</footer>
<script>
const view=document.querySelector('#view'),status=document.querySelector('#status'),
notice=document.querySelector('#notice'),detail=document.querySelector('#detail');
let paused=false,previous='',lastAdvance=0,freshUntil=0,objectURL=null;
function unavailable(message){status.textContent=message;status.className='';
 view.hidden=true;notice.hidden=false;notice.textContent=message;}
document.querySelector('#pause').onclick=()=>{paused=!paused;
 document.querySelector('#pause').textContent=paused?'继续显示':'暂停显示';
 if(paused)unavailable('已暂停显示');};
document.querySelector('#full').onclick=()=>document.querySelector('#screen').requestFullscreen();
setInterval(()=>{if(!paused&&performance.now()>freshUntil)unavailable('等待新画面 / 画面已过期');},100);
async function poll(){const started=performance.now();let nextURL=null;
 try{
  if(paused)return;
  const response=await fetch('/front.jpg',{cache:'no-store',signal:AbortSignal.timeout(2000)});
  if(!response.ok)throw new Error('暂时无法读取新画面');
  const id=response.headers.get('X-Frame-Id'),age=Number(response.headers.get('X-Frame-Age-Ms'));
  if(!id||!Number.isFinite(age)||age<0||age>1500)throw new Error('画面时间戳无效');
  const blob=await response.blob();nextURL=URL.createObjectURL(blob);
  const decoded=new Image();decoded.src=nextURL;await decoded.decode();
  if(paused)return;
  const now=performance.now(),elapsed=now-started;
  if(id!==previous){previous=id;lastAdvance=now;}
  if(now-lastAdvance>1500||age+elapsed>1500)throw new Error('画面已过期');
  view.src=nextURL;if(objectURL)URL.revokeObjectURL(objectURL);
  objectURL=nextURL;nextURL=null;freshUntil=now+1500-age-elapsed;
  view.hidden=false;notice.hidden=true;status.textContent='实时更新';status.className='live';
  detail.textContent=`${decoded.naturalWidth} × ${decoded.naturalHeight} · 帧龄约 ${Math.round(age+elapsed)} ms · ${id} · 不控制舵机`;
 }catch(error){if(!paused)unavailable(error.message);}
 finally{if(nextURL)URL.revokeObjectURL(nextURL);setTimeout(poll,Math.max(0,200-(performance.now()-started)));}
}
poll();
</script></html>'''.encode('utf-8')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/':
                self.reply(200, 'text/html; charset=utf-8', PAGE)
            elif self.path == '/front.jpg':
                try:
                    data, identity, age, stamp = self.server.source.read()
                except Exception:
                    self.reply(503, 'text/plain', b'Waiting for a fresh Sony frame')
                    return
                self.reply(200, 'image/jpeg', data, {
                    'X-Frame-Id': identity, 'X-Frame-Age-Ms': str(age),
                    'X-Frame-Read-At': stamp})
            else:
                self.reply(404, 'text/plain', b'Not found')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def reply(self, code, kind, data, headers=None):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--sony-output', type=Path,
                        default=Path(__file__).resolve().parent / 'output')
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        server.source = SonySource(args.sony_output)
        print('SONY PREVIEW http://127.0.0.1:{}/'.format(args.port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
