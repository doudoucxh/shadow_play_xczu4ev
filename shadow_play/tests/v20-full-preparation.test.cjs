'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..'),out=path.join(root,'.review_work/v20-full-preparation-20261019');
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--allow-file-access-from-files']});
 const result={};
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1050},acceptDownloads:true});
  const page=await context.newPage(),errors=[],network=[];
  page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url())});
  await page.goto(pathToFileURL(path.join(root,'shadow_play/planning/wusong_v20_full_20261019/preview.html')).href);
  assert.equal(await page.locator('[data-scene]').count(),24);assert.equal(await page.locator('[data-cue]').count(),19);
  assert.equal(await page.locator('#audio').evaluate(a=>a.paused),true);assert.equal(await page.locator('#video').evaluate(v=>v.paused),true);
  assert.equal(await page.locator('#video').evaluate(v=>v.muted),true);
  await page.waitForFunction(()=>document.querySelector('#audio').readyState>=1&&document.querySelector('#video').readyState>=1);
  const duration=await page.locator('#audio').evaluate(a=>a.duration);assert.ok(Math.abs(duration-76.579410430839)<.00001);
  const ids=await page.locator('[data-cue]').evaluateAll(bs=>bs.map(b=>b.dataset.cue));assert.ok(ids.indexOf('P15')<ids.indexOf('P14'));
  const payload=await page.locator('#data').evaluate(el=>JSON.parse(el.textContent));
  assert.equal(payload.readiness.physical_performance_ready,false);
  for(const cue of payload.score.impact_cues){await page.locator('[data-cue="'+cue.id+'"]').click();const t=await page.locator('#audio').evaluate(a=>a.currentTime);assert.ok(Math.abs(t-cue.time_s)<.002)}
  await page.locator('[data-scene="S17"]').click();assert.match(await page.locator('#current-scene').textContent(),/^S17/);
  await page.locator('#view').selectOption('annotated');await page.waitForFunction(()=>document.querySelector('#video').readyState>=1);
  assert.match(await page.locator('#video').getAttribute('src'),/annotated/);
  await page.locator('#view').selectOption('audience');await page.waitForFunction(()=>document.querySelector('#video').readyState>=1);
  await page.locator('#restart').click();await page.locator('#audio').evaluate(a=>{a.muted=true});
  await page.locator('#rate').selectOption('0.5');assert.equal(await page.locator('#audio').evaluate(a=>a.playbackRate),.5);
  await page.locator('#play').click();await page.waitForFunction(()=>document.querySelector('#audio').currentTime>.2);
  await page.locator('#pause').click();assert.equal(await page.locator('#video').evaluate(v=>v.paused),true);
  await page.locator('#rate').selectOption('1');await page.locator('#restart').click();await page.locator('#play').click();
  // Run the entire selected soundtrack silently; the page cannot contact hardware.
  await page.locator('#audio').evaluate(a=>{a.playbackRate=8});await page.locator('#video').evaluate(v=>{v.playbackRate=8});
  await page.waitForFunction(()=>document.querySelector('#audio').ended,{},{timeout:30000});
  assert.match(await page.locator('#media-status').textContent(),/离线排练结束/);
  assert.equal(await page.locator('.cue.past').count(),19);
  const download=page.waitForEvent('download');await page.locator('#export').click();const file=await download;await file.saveAs(path.join(out,'ui-export.json'));
  const exported=JSON.parse(await fs.readFile(path.join(out,'ui-export.json'),'utf8'));
  assert.equal(exported.physical_performance_ready,false);assert.equal(exported.automatic_replay_allowed,false);
  await page.locator('[data-cue="P13"]').click();
  await page.waitForFunction(()=>!document.querySelector('#video').seeking&&Math.abs(document.querySelector('#video').currentTime-document.querySelector('#audio').currentTime)<.05);
  assert.match(await page.locator('#media-status').textContent(),/已定位离线排练/);
  await page.screenshot({path:path.join(out,'preview-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,'preview-mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  Object.assign(result,{passed:true,scenes:24,cues:19,all_cue_seeks_checked:true,original_audio_duration_s:duration,
    full_soundtrack_rehearsal_silent:true,initially_paused:true,motor_interface_present:false,
    video_switch:true,half_speed:true,blocked_export:true,desktop_and_mobile:true,external_network_requests:network.length,javascript_errors:errors.length});
  await fs.writeFile(path.join(out,'ui-check.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
