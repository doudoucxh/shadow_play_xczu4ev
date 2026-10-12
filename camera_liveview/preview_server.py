"""Local browser preview of the running Sony SDK session; no camera/motor commands."""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import sys
import threading
import time
import uuid
from PIL import Image

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
canvas{position:absolute;cursor:crosshair}canvas[hidden]{display:none}
button:disabled{opacity:.45;cursor:default}
#notice{position:absolute;background:#202936;padding:16px;border-radius:8px}
footer{padding:12px 24px;font-size:14px;color:#a9b9cb}
</style>
<header><h1>Sony 正面实时取景</h1><span id="status">正在读取…</span>
<button id="pause">暂停显示</button><button id="mark">点选五个连接点</button>
<button onclick="location.href='/coordinates'">查看五点坐标</button>
<button id="undo" hidden>撤销上一点</button><button id="save" hidden disabled>保存五点</button>
<button id="cancel" hidden>返回实时画面</button><button id="full">全屏</button></header>
<main id="screen"><img id="view" alt="Sony 实时画面" hidden>
<canvas id="overlay" hidden></canvas><div id="notice">等待新画面…</div></main>
<footer id="detail">读取现有 SDK 取景 · 约 5 帧/秒 · 不控制舵机</footer>
<script>
const view=document.querySelector('#view'),status=document.querySelector('#status'),
notice=document.querySelector('#notice'),detail=document.querySelector('#detail');
const overlay=document.querySelector('#overlay'),mark=document.querySelector('#mark'),
undo=document.querySelector('#undo'),save=document.querySelector('#save'),cancel=document.querySelector('#cancel'),
pause=document.querySelector('#pause'),screen=document.querySelector('#screen');
const names=['人物左手','人物头','人物右手','虎头','虎脚控制杆'];
let paused=false,marking=false,previous='',lastAdvance=0,freshUntil=0,objectURL=null,
selectionId=null,points=[],saving=false;
function unavailable(message){status.textContent=message;status.className='';
 view.hidden=true;notice.hidden=false;notice.textContent=message;}
pause.onclick=()=>{paused=!paused;
 pause.textContent=paused?'继续显示':'暂停显示';
 if(paused)unavailable('已暂停显示');};
document.querySelector('#full').onclick=()=>screen.requestFullscreen();
function draw(){
 const w=screen.clientWidth,h=screen.clientHeight,scale=Math.min(w/overlay.width,h/overlay.height);
 overlay.style.width=`${overlay.width*scale}px`;overlay.style.height=`${overlay.height*scale}px`;
 overlay.style.left=`${(w-overlay.width*scale)/2}px`;overlay.style.top=`${(h-overlay.height*scale)/2}px`;
 const ctx=overlay.getContext('2d');ctx.clearRect(0,0,overlay.width,overlay.height);
 points.forEach((p,i)=>{ctx.lineWidth=2;ctx.strokeStyle='#ffed70';ctx.fillStyle='#ffed70';
  ctx.beginPath();ctx.arc(p[0],p[1],5,0,2*Math.PI);ctx.stroke();
  ctx.font='bold 16px sans-serif';ctx.strokeStyle='#000';ctx.lineWidth=3;
  const x=Math.min(overlay.width-18,p[0]+8),y=Math.max(18,p[1]-8);
  ctx.strokeText(String(i+1),x,y);ctx.fillText(String(i+1),x,y);});
 save.disabled=saving||!selectionId||points.length!==5;undo.disabled=saving||!selectionId||points.length===0;
 if(!saving&&selectionId){status.textContent=points.length===5?'五点已选，请核对编号后保存':`请点击 ${points.length+1}：${names[points.length]}`;
  status.className='';}
}
new ResizeObserver(()=>{if(marking&&!overlay.hidden)draw();}).observe(screen);
mark.onclick=async()=>{
 paused=true;marking=true;mark.disabled=true;pause.disabled=true;points=[];selectionId=null;
 cancel.hidden=false;unavailable('正在冻结新画面…');let nextURL=null;
 try{
  const r=await fetch('/freeze.jpg',{cache:'no-store',signal:AbortSignal.timeout(3000)});
  if(!r.ok)throw new Error('无法冻结新画面，请返回实时画面后重试');
  const token=r.headers.get('X-Selection-Id');if(!token)throw new Error('缺少冻结画面编号');
  nextURL=URL.createObjectURL(await r.blob());const img=new Image();img.src=nextURL;await img.decode();
  if(!marking)return;
  selectionId=token;view.src=nextURL;if(objectURL)URL.revokeObjectURL(objectURL);
  objectURL=nextURL;nextURL=null;overlay.width=img.naturalWidth;overlay.height=img.naturalHeight;
  overlay.hidden=false;view.hidden=false;notice.hidden=true;undo.hidden=false;save.hidden=false;
  detail.textContent=`已冻结 ${img.naturalWidth} × ${img.naturalHeight} 画面 · 按顺序点击实际杆件连接点 · 只记录位置`;
  draw();
 }catch(error){if(marking)unavailable(error.message);}
 finally{if(nextURL)URL.revokeObjectURL(nextURL);}
};
overlay.onclick=event=>{
 if(saving||points.length===5||!selectionId)return;
 const rect=overlay.getBoundingClientRect(),x=(event.clientX-rect.left)*overlay.width/rect.width,
 y=(event.clientY-rect.top)*overlay.height/rect.height;
 if(x>=0&&x<overlay.width&&y>=0&&y<overlay.height){points.push([x,y]);draw();}
};
undo.onclick=()=>{if(!saving){points.pop();draw();}};
cancel.onclick=()=>{if(saving)return;marking=false;paused=false;selectionId=null;points=[];
 overlay.hidden=true;undo.hidden=true;save.hidden=true;cancel.hidden=true;mark.disabled=false;pause.disabled=false;
 pause.textContent='暂停显示';previous='';freshUntil=0;unavailable('正在恢复实时画面…');};
save.onclick=async()=>{
 if(saving||points.length!==5||!selectionId)return;
 saving=true;save.disabled=true;undo.disabled=true;cancel.disabled=true;status.textContent='正在保存…';
 try{
  const r=await fetch('/annotations',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({selection_id:selectionId,points:points.map((pixel,i)=>({label:i+1,pixel}))}),
   signal:AbortSignal.timeout(5000)});
  const result=await r.json();if(!r.ok)throw new Error(result.error||'保存失败');
  status.textContent='五个连接点已保存';detail.textContent=`${result.record} · 请告诉助手“已点好”`;
  selectionId=null;
 }catch(error){status.textContent=error.message;}
 finally{saving=false;cancel.disabled=false;save.disabled=!selectionId;undo.disabled=!selectionId;}
};
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
 finally{if(nextURL)URL.revokeObjectURL(nextURL);setTimeout(poll,Math.max(0,50-(performance.now()-started)));}
}
poll();
</script></html>'''.encode('utf-8')


COORDINATE_PAGE = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>五点静态坐标</title><style>
body{margin:24px;background:#10151c;color:#ecf2fa;font:16px system-ui,sans-serif}
h1{font-size:22px}a{color:#86caff}p{line-height:1.6}img{max-width:100%;height:auto}
table{border-collapse:collapse;width:100%;max-width:760px;margin:20px 0}
th,td{padding:10px;text-align:left;border-bottom:1px solid #455262}
.note{color:#ffca80}#stamp{color:#a9b9cb}
</style><a href="/">返回实时取景</a><h1>五点静态坐标</h1>
<p id="stamp">正在读取坐标记录…</p>
<p>原点：幕布左下角。X 向右，Y 向上。有效幕面 740 × 500 mm。</p>
<p class="note">这是一帧静态记录，不随当前画面更新。数值为杆端在幕布平面的近似投影；
四角贴标偏差和镜头畸变尚未测量。坐标不代表舵机角度，也不用于启动电机。</p>
<table><thead><tr><th>点</th><th>部位</th><th>舵机</th><th>X / mm（约）</th><th>Y / mm（约）</th></tr></thead>
<tbody id="rows"></tbody></table>
<p>黄色编号是本次记录的五个杆端。</p><img src="/coordinate-overlay.png" alt="五点及幕布四角标注">
<p>透视校正预览：</p><img src="/coordinate-stage.png" alt="幕布平面坐标预览">
<script>
const names=['人物左手','人物头部控制杆','人物右手','虎头控制杆','虎脚控制杆'];
fetch('/coordinate-result.json',{cache:'no-store'}).then(r=>{
 if(!r.ok)throw new Error('尚未加载坐标记录');return r.json();
}).then(r=>{
 if(!Array.isArray(r.points)||r.points.length!==5)throw new Error('坐标记录不完整');
 document.querySelector('#stamp').textContent=`静态采集时间：${r.reference_selection.reference_capture_at}`;
 for(let i=0;i<5;i++){
  const p=r.points[i],tr=document.createElement('tr');
  for(const value of [i+1,names[i],`${2*i+1}、${2*i+2}`,Math.round(p.stage_mm[0]),Math.round(p.stage_mm[1])]){
   const td=document.createElement('td');td.textContent=value;tr.append(td);
  }document.querySelector('#rows').append(tr);
 }
}).catch(e=>{document.querySelector('#stamp').textContent=e.message;});
</script></html>'''.encode('utf-8')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/':
                self.reply(200, 'text/html; charset=utf-8', PAGE)
            elif self.path == '/coordinates':
                self.reply(200, 'text/html; charset=utf-8', COORDINATE_PAGE)
            elif self.path in ('/coordinate-result.json', '/coordinate-overlay.png', '/coordinate-stage.png'):
                files = {'/coordinate-result.json': ('geometry.json', 'application/json'),
                         '/coordinate-overlay.png': ('numbered_reference.png', 'image/png'),
                         '/coordinate-stage.png': ('numbered_stage.png', 'image/png')}
                folder = getattr(self.server, 'coordinates_dir', None)
                if folder is None:
                    self.reply(503, 'text/plain', b'No coordinate record loaded')
                    return
                filename, kind = files[self.path]
                try:
                    data = (folder / filename).read_bytes()
                except OSError:
                    self.reply(503, 'text/plain', b'Coordinate record unavailable')
                    return
                self.reply(200, kind, data)
            elif self.path in ('/front.jpg', '/freeze.jpg'):
                try:
                    data, identity, age, stamp = self.server.source.read()
                except Exception:
                    self.reply(503, 'text/plain', b'Waiting for a fresh Sony frame')
                    return
                headers = {
                    'X-Frame-Id': identity, 'X-Frame-Age-Ms': str(age),
                    'X-Frame-Read-At': stamp}
                if self.path == '/freeze.jpg':
                    with Image.open(io.BytesIO(data)) as image:
                        width, height = image.size
                    token = uuid.uuid4().hex
                    with self.server.selection_lock:
                        now = time.monotonic()
                        self.server.selections = {k: v for k, v in self.server.selections.items()
                                                  if now-v['created'] < 1800}
                        if len(self.server.selections) >= 8:
                            oldest = min(self.server.selections,
                                         key=lambda k: self.server.selections[k]['created'])
                            del self.server.selections[oldest]
                        self.server.selections[token] = {
                            'created': now, 'data': data, 'frame_id': identity,
                            'frame_read_at': stamp, 'frame_age_ms_at_freeze': age,
                            'width': width, 'height': height}
                    headers['X-Selection-Id'] = token
                self.reply(200, 'image/jpeg', data, headers)
            else:
                self.reply(404, 'text/plain', b'Not found')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if self.path != '/annotations':
            self.reply(404, 'application/json', b'{"error":"Not found"}')
            return
        try:
            # JSON-only requests; no CORS, path input, frame upload or hardware commands.
            origin = self.headers.get('Origin')
            if origin is not None and origin != 'http://127.0.0.1:{}'.format(self.server.server_port):
                raise ValueError('Unexpected request origin')
            if self.headers.get('Content-Type') != 'application/json':
                raise ValueError('JSON required')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid request size')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('JSON object required')
            token = payload.get('selection_id')
            if not isinstance(token, str) or len(token) != 32:
                raise ValueError('Invalid selection ID')
            with self.server.selection_lock:
                snapshot = self.server.selections.get(token)
                if not snapshot or time.monotonic()-snapshot['created'] >= 1800:
                    raise ValueError('Frozen picture expired; freeze a new picture')
                points = validate_points(payload.get('points'), snapshot['width'], snapshot['height'])
                folder = self.server.annotation_root / token
                folder.mkdir(parents=True, exist_ok=False)
                record = {
                    'version': 1, 'purpose': 'operator-selected image attachment locations',
                    'selection_id': token, 'frame_id': snapshot['frame_id'],
                    'frame_read_at': snapshot['frame_read_at'],
                    'frame_age_ms_at_freeze': snapshot['frame_age_ms_at_freeze'],
                    'saved_at': datetime.now(timezone.utc).isoformat(),
                    'image_width': snapshot['width'], 'image_height': snapshot['height'],
                    'image_sha256': hashlib.sha256(snapshot['data']).hexdigest(),
                    'points': points, 'actual_servo_position_known': False,
                    'motion_permission': False, 'metric_accuracy_verified': False,
                    'stage_coordinates': None}
                (folder/'frame.jpg').write_bytes(snapshot['data'])
                (folder/'points.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
                del self.server.selections[token]
            self.reply(200, 'application/json', json.dumps({'record': str(folder/'points.json')}).encode('utf-8'))
        except (ValueError, TypeError, KeyError) as error:
            self.reply(400, 'application/json', json.dumps({'error': str(error)}).encode('utf-8'))
        except OSError:
            self.reply(503, 'application/json', b'{"error":"Could not save annotation"}')


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


def validate_points(points, width, height):
    if not isinstance(points, list) or len(points) != 5:
        raise ValueError('Exactly five points required')
    names = ('wusong_left', 'wusong_neck', 'wusong_right', 'tiger_head', 'tiger_leg')
    result = []
    for i, p in enumerate(points):
        if not isinstance(p, dict) or type(p.get('label')) is not int or p['label'] != i+1:
            raise ValueError('Point labels must be 1 through 5 in order')
        pixel = p.get('pixel')
        if not isinstance(pixel, list) or len(pixel) != 2 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in pixel):
            raise ValueError('Two finite pixel coordinates required')
        x, y = pixel
        if not 0 <= x < width or not 0 <= y < height:
            raise ValueError('Point outside picture')
        if any(math.hypot(x-q['pixel'][0], y-q['pixel'][1]) < 2 for q in result):
            raise ValueError('Two connection points overlap; check the selection')
        result.append({'label': i+1, 'rod': names[i], 'servos': [2*i+1, 2*i+2],
                       'pixel': pixel, 'selection_method': 'operator_click'})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--sony-output', type=Path,
                        default=Path(__file__).resolve().parent / 'output')
    parser.add_argument('--coordinates-dir', type=Path,
                        help='Saved geometry.json and numbered PNGs; static display only')
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        server.source = SonySource(args.sony_output)
        server.coordinates_dir = args.coordinates_dir.resolve() if args.coordinates_dir else None
        server.annotation_root = args.sony_output.resolve() / 'annotations'
        server.selections = {}
        server.selection_lock = threading.Lock()
        print('SONY PREVIEW http://127.0.0.1:{}/'.format(args.port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
