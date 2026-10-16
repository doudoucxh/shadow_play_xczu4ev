/* Offline safety/lifecycle contract tests. No network or hardware calls. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../source', name), 'utf8');
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
async function until(predicate) {
  const deadline = Date.now() + 2000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('Timed out waiting for lifecycle event');
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}
function element() {
  return {dataset:{},append(){},setAttribute(){},addEventListener(){},querySelector(){return this;}};
}
function boardHarness(fetch) {
  const context = {window:{},document:{createElement:element},AbortController,setTimeout,clearTimeout,fetch};
  vm.runInNewContext(source('board-client.js'), context);
  return context.window.ShadowBoardClient.create({root:element()});
}
const response = data => ({ok:true,json:async()=>data});
const status = ready => ({app:'shadow-theatre-board',token:'test-token',camera:{configured:true},motion:{ready,rails:ready,reason:'未标定'}});

test('startup/check never sends movement, unavailable motion stays local', async () => {
  const calls=[];
  const client=boardHarness(async (url,options)=>{calls.push({url,options});return response(status(false));});
  assert.equal(calls.length,0);
  await client.check();
  assert.equal(await client.control({kind:'rail',actor:'wusong',position:.5}),false);
  assert.deepEqual(calls.map(call=>[call.url,call.options.method]),[['/api/status','GET']]);
});

test('failed control is authenticated once and is not replayed by reconnect', async () => {
  const calls=[];
  const client=boardHarness(async (url,options)=>{
    calls.push({url,options});
    if(url==='/api/control')throw new Error('connection lost');
    return response(status(true));
  });
  await client.check();
  assert.equal(await client.control({kind:'rail',actor:'wusong',position:.5}),false);
  await client.check();
  const sent=calls.filter(call=>call.url==='/api/control');
  assert.equal(sent.length,1);
  assert.equal(sent[0].options.headers['X-Shadow-Token'],'test-token');
  assert.deepEqual(JSON.parse(sent[0].options.body),{kind:'rail',actor:'wusong',position:.5});
});

test('camera stop follows an outstanding start rather than racing it', async () => {
  const calls=[],startResponse=deferred();
  const client=boardHarness(async (url,options)=>{
    calls.push({url,options});
    if(url==='/api/status')return response(status(false));
    if(url==='/api/camera/start')await startResponse.promise;
    return response({ok:true});
  });
  const start=client.startCamera();
  await until(()=>calls.some(call=>call.url==='/api/camera/start'));
  const stop=client.stopCamera();
  assert.equal(calls.filter(call=>call.url==='/api/camera/stop').length,0);
  startResponse.resolve();await Promise.all([start,stop]);
  assert.deepEqual(calls.filter(call=>call.options.method==='POST').map(call=>call.url),['/api/camera/start','/api/camera/stop']);
});

function cameraHarness(board) {
  const events={poses:[],states:[]},view={dataset:{}},screen={hidden:false,closest:()=>null};
  const image={hidden:true,removeAttribute(key){delete this[key];},remove(){}};
  const ctx=new Proxy({},{get:()=>()=>{},set:()=>true});
  const doc={hidden:false,createElement:()=>image,addEventListener(){},removeEventListener(){}};
  const win={setTimeout,clearTimeout,devicePixelRatio:1,addEventListener(){},removeEventListener(){},getComputedStyle:()=>({objectFit:'contain'}),Image:class{
    constructor(){this.naturalWidth=640;this.naturalHeight=360;}
    async decode(){}
  }};
  doc.defaultView=win;
  const video={ownerDocument:doc,closest:selector=>selector==='.shadow-camera-view'?view:screen,after(){},pause(){},addEventListener(){},removeEventListener(){}};
  const canvas={style:{},width:640,height:360,setAttribute(){},getContext:()=>ctx,getBoundingClientRect:()=>({width:640,height:360})};
  vm.runInNewContext(source('camera-preview.js'),{window:win,document:doc,performance});
  const camera=win.ShadowCameraPreview.create({video,canvas,board,onPose:pose=>events.poses.push(pose),onState:state=>events.states.push(state)});
  return {camera,video,image,events};
}

test('cancelled camera startup cannot publish a late frame', async () => {
  const start=deferred();let polls=0,stops=0;
  const h=cameraHarness({startCamera:()=>start.promise,stopCamera:async()=>{stops++;},frame:async()=>{polls++;},message(){}});
  try {
    const pending=h.camera.start();
    h.camera.stop();start.resolve();await pending;
    assert.equal(stops,1);assert.equal(polls,0);
    assert.equal(h.camera.state,'off');assert.equal(h.image.hidden,true);
    assert.equal(h.events.states.includes('live'),false);
  } finally {h.camera.destroy();}
});

test('same-frame landmarks clear when absent and stale JPEG clears too', async () => {
  let sequence=0,stops=0;
  const second=deferred(),third=deferred();
  const h=cameraHarness({startCamera:async()=>{},stopCamera:async()=>{stops++;},message(){},frame:async()=>{
    const n=++sequence;
    if(n===2)await second.promise;
    if(n>=3)await third.promise;
    return {sequence:n,session_id:'s1',width:640,height:360,captured_age_ms:n>=3?2000:5,jpeg_base64:'test-jpeg',
      pose:n===1?{head:[.5,.2],leftWrist:[.2,.6],rightWrist:[.8,.6]}:null};
  }});
  try {
    assert.equal(sequence,0);await h.camera.start();
    await until(()=>h.events.poses.some(Boolean));
    assert.equal(h.events.poses.at(-1).head[0],.5);
    assert.equal(h.video.hidden,true);assert.equal(h.image.hidden,false);
    second.resolve();await until(()=>sequence>=2&&h.events.poses.at(-1)===null);
    assert.equal(h.camera.state,'live');
    third.resolve();await until(()=>h.camera.state==='waiting');
    assert.equal(h.image.hidden,true);assert.equal(h.image.src,undefined);
    h.camera.stop();assert.equal(stops,1);
    const count=sequence;await new Promise(resolve=>setTimeout(resolve,160));assert.equal(sequence,count);
  } finally {second.resolve();third.resolve();h.camera.destroy();}
});
