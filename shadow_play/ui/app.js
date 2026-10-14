/* UI-only prototype: no device APIs, camera capture, network calls or motion data. */
(() => {
  const {stage, setPose, icon} = window.TheatreArt;
  const {rods, humanIds, resolveHuman, projectHuman} = window.TheatreRig;
  const main = document.querySelector('#main');
  const DURATION = 67.10566893424036;
  const chapters = [
    {time: 0, name: '虎啸山林', line: '山风起，猛虎现。景阳冈上，一出好戏将启。'},
    {time: 10, name: '武松上冈', line: '酒意未消，英雄踏入山林，忽闻一声虎啸。'},
    {time: 29, name: '腾跃扑咬', line: '猛虎腾身扑下，武松举手相迎。'},
    {time: 40, name: '双方交锋', line: '一扑一闪，一攻一挡，方寸幕布尽是锋芒。'},
    {time: 46, name: '连拳制虎', line: '双拳起落，力挽猛虎，英雄气概尽显。'},
    {time: 61, name: '英雄收势', line: '山林渐静，好汉收势，一段传奇留在光影里。'}
  ];
  const presets = [
    {name: '起势', wusong_right: [65, 184], wusong_left: [235, 184], wusong_neck: [150, 136]},
    {name: '双手举起', wusong_right: [63, 66], wusong_left: [237, 66], wusong_neck: [150, 128]},
    {name: '抱拳', wusong_right: [138, 194], wusong_left: [164, 194], wusong_neck: [150, 136]},
    {name: '侧身', wusong_right: [59, 133], wusong_left: [233, 99], wusong_neck: [168, 134]}
  ];
  let route = 'home', play = false, elapsed = 0, lastTime = 0, posePlaying = false, poseTime = 0, poseStep = -1;
  let motionPaused = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let touch = structuredClone(presets[0]), dragging = null, toastTimer;
  const fmt = n => `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(Math.floor(n % 60)).padStart(2, '0')}`;
  function announce(message) {
    const toast = document.querySelector('#toast'); toast.textContent = message; toast.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
  }
  function modeHeading(n, title, sub) {
    return `<div class="workspace-top"><a class="back-link" href="#home">← <span>返回戏台</span></a><nav class="mode-tabs" aria-label="体验模式">${[['classic','经典传唱'],['touch','指尖皮影'],['pose','以身入戏']].map(([key,label])=>`<a href="#${key}" ${route===key?'aria-current="page"':''}>${label}</a>`).join('')}</nav><span class="workspace-mark">光影实验室 / ${n}</span></div><div class="page-heading"><div><span class="eyebrow">ACT ${n} / ${route==='classic'?'THE CLASSICS':route==='touch'?'AT YOUR FINGERTIPS':'BECOME THE STORY'}</span><h1>${title}<span class="heading-dot">。</span></h1><p>${sub}</p></div><span class="demo-label"><i></i> ${route==='pose'?'示范姿态 · 非实时识别':'屏幕动画预览'}</span></div>`;
  }
  function home() {
    main.innerHTML = `<section class="hero"><div class="hero-copy"><div class="eyebrow"><span class="small-line"></span>光影流转 · 非遗新生</div><h1>一方幕布，<br><em>万般人间。</em></h1><p>让一束光，唤醒千年的故事。<br>从看戏到入戏，找到属于你的皮影时刻。</p><a class="primary-button" href="#modes">选一种方式，入戏 ${icon('arrow')}</a><div class="hero-footnote"><span class="red-dot"></span>传统皮影 × 数字交互 <span class="mini-line"></span> 每个人，都可以是执影人</div></div><div class="hero-visual"><div class="visual-topline"><span>今 日 好 戏</span><span>壹 / 武松打虎</span></div><div class="hero-stage">${stage({hero:true})}<span class="stage-seal">好戏<br>开场</span></div><div class="visual-caption"><span>一口道尽千古事，双手对舞百万兵。</span><span>LIGHT · SHADOW · YOU</span></div></div></section><section class="modes-section" id="modes" aria-labelledby="modes-title"><div class="section-heading"><div><span class="section-number">叁</span><h2 id="modes-title">三种方式，同一份热爱</h2></div><span>选一个入口，让故事因你而动 <span>↙</span></span></div><div class="mode-cards"><a class="mode-card classic-card" href="#classic"><div class="card-top"><span class="mode-kicker">01 / 赏一出好戏</span><span class="card-icon">${icon('book')}</span></div><div class="card-title"><h3>经典传唱</h3><span>THE CLASSICS</span></div><p>景阳冈上，一场人与虎的交锋。<br>跟随《武松打虎》，重温经典光影。</p><div class="card-bottom"><span>经典剧目 · 沉浸观演</span><span class="round-arrow">↗</span></div><span class="card-watermark" aria-hidden="true">戏</span></a><a class="mode-card touch-card" href="#touch"><div class="card-top"><span class="mode-kicker">02 / 做一回执影人</span><span class="card-icon">${icon('touch')}</span></div><div class="card-title"><h3>指尖皮影</h3><span>AT YOUR FINGERTIPS</span></div><p>轻点、拖动，让火柴人成为你的提线。<br>一抬手，一转身，指尖也能演好戏。</p><div class="card-bottom"><span>触屏操偶 · 自由创作</span><span class="round-arrow">↗</span></div><span class="card-watermark" aria-hidden="true">手</span></a><a class="mode-card pose-card" href="#pose"><div class="card-top"><span class="mode-kicker">03 / 亲自走进故事</span><span class="card-icon">${icon('pose')}</span></div><div class="card-title"><h3>以身入戏</h3><span>BECOME THE STORY</span></div><p>以身体为笔，以光影为墨。<br>让皮影跟随你的姿态，共演一段故事。</p><div class="card-bottom"><span>姿态映射 · 身临其境</span><span class="round-arrow">↗</span></div><span class="card-watermark" aria-hidden="true">身</span></a></div></section><div class="home-note"><span>✳</span> 观看，是故事的开始；参与，让传统有了新的生命。<span class="note-line"></span><span class="note-en">A LIVING TRADITION</span></div>`;
    setPose(main);
  }
  function classic() {
    main.innerHTML = `${modeHeading('01','经典传唱','灯影照山林，好汉上景阳。一起看一出《武松打虎》。')}<div class="classic-layout"><section class="screen-panel"><div class="panel-bar"><span><i class="red-dot"></i>光影戏台</span><span>《武松打虎》 / 动画概念预演</span></div><div class="performance-stage" id="performance-stage">${stage({points:true})}<div class="stage-subtitle" id="stage-subtitle">山风起，猛虎现。</div><button class="stage-play" id="stage-play" aria-label="开始动画预演">${icon('play')}</button></div><div class="player"><div class="seek-row"><span id="current-time">00:00</span><input id="timeline" aria-label="剧情进度" type="range" min="0" max="${DURATION}" step="any" value="0"><span>01:07</span></div><div class="player-bottom"><div class="player-buttons"><button type="button" class="primary-button compact" id="play-button">${icon('play')}<span>开始预演</span></button><button type="button" class="text-button" id="restart-button">${icon('reset')}从头开始</button></div><span class="audio-note">动画演示 · 音轨待接入</span></div></div></section><aside class="story-panel"><span class="eyebrow">本日剧目 / REPERTOIRE</span><h2>武松打虎</h2><p class="story-intro">一段景阳冈上的英雄传奇，<br>一场皮影幕后的匠心演绎。</p><div class="story-meta"><span>传统经典</span><span>时长 01:07</span></div><div class="chapter-title"><span>剧情篇章</span><span>六幕光影</span></div><ol class="chapters">${chapters.map((c,i)=>`<li><button type="button" data-chapter="${i}" class="${i===0?'active':''}" ${i===0?'aria-current="step"':''}><span class="chapter-index">${String(i+1).padStart(2,'0')}</span><span>${c.name}</span><time>${fmt(c.time)}</time><span class="chapter-dot"></span></button></li>`).join('')}</ol><div class="story-quote">武松：双手 · 颈部主杆<br>老虎：耳部头杆 · 尾部后端杆</div></aside></div>`;
    document.querySelector('#play-button').onclick = togglePlay;
    document.querySelector('#stage-play').onclick = togglePlay;
    document.querySelector('#restart-button').onclick = () => { elapsed = 0; play = false; updatePlayer(); };
    document.querySelector('#timeline').oninput = e => { elapsed = Number(e.target.value); updatePlayer(); };
    main.querySelectorAll('[data-chapter]').forEach(b => b.onclick = () => { elapsed = chapters[Number(b.dataset.chapter)].time; updatePlayer(); });
    updatePlayer();
  }
  function togglePlay() { if (elapsed >= DURATION) elapsed = 0; play = !play; updatePlayer(); }
  function updatePlayer() {
    const i = Math.max(0, chapters.findLastIndex(c => elapsed >= c.time));
    document.querySelector('#current-time').textContent = fmt(elapsed);
    const timeline = document.querySelector('#timeline'); timeline.value = elapsed; timeline.style.setProperty('--progress', `${elapsed/DURATION*100}%`);
    document.querySelector('#play-button').innerHTML = `${play ? '<span class="pause-glyph">Ⅱ</span>' : icon('play')}<span>${play ? '暂停预演' : elapsed >= DURATION ? '再看一次' : elapsed > 0 ? '继续预演' : '开始预演'}</span>`;
    document.querySelector('#stage-play').hidden = play || elapsed > 0;
    document.querySelector('#stage-subtitle').textContent = elapsed >= DURATION ? '好戏落幕，余韵悠长。' : chapters[i].line;
    main.querySelectorAll('[data-chapter]').forEach((b,j) => { b.classList.toggle('active', i===j); if(i===j) b.setAttribute('aria-current','step'); else b.removeAttribute('aria-current'); });
    const t = elapsed, intensity = i >= 2 && i <= 4 ? 1 : .35;
    setPose(main, [-72+Math.sin(t*2)*28*intensity,-42-Math.sin(t*2)*45*intensity], [84+Math.cos(t*2)*20*intensity,-24-Math.cos(t*2)*72*intensity], Math.sin(t*2)*5*intensity);
    const tiger = main.querySelector('.puppet-tiger'); tiger.setAttribute('transform', `translate(0 ${-Math.abs(Math.sin(t*1.8))*32*intensity}) rotate(${Math.sin(t*1.8)*8*intensity})`);
  }
  function stickman(id, interactive = false) {
    return `<svg id="${id}" class="stickman ${interactive?'interactive-stickman':''}" viewBox="0 0 300 330" ${interactive?'aria-label="火柴人操控区，武松右手、左手和颈部主杆三个控制点"':'role="img" aria-label="示范人体骨架，双腕与双肩中点对应武松三根杆"'}>
      <defs><pattern id="${id}-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="currentColor" opacity=".12"/></pattern></defs>
      <rect width="300" height="330" fill="url(#${id}-grid)"/><ellipse cx="150" cy="301" rx="69" ry="8" class="body-shadow"/>
      <g class="skeleton-lines" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle class="skeleton-head" cx="150" cy="80" r="24"/><path class="body-line"/><path class="left-line"/><path class="right-line"/></g>
      <g class="skeleton-joints"><circle class="shoulder-left" r="5"/><circle class="shoulder-right" r="5"/></g>
      ${humanIds.map(key=>`<g class="handle-group" data-control="${key}"><circle class="handle-halo" data-halo="${key}" r="22"/><circle class="joint-handle" data-joint="${key}" r="${interactive?12:7}" ${interactive?`tabindex="0" role="slider" aria-label="武松${rods[key].label}位置" aria-valuemin="0" aria-valuemax="300" aria-valuenow="150"`:''}/><text class="joint-label" data-joint-label="${key}" text-anchor="${key==='wusong_neck'?'start':'middle'}">${rods[key].label}</text></g>`).join('')}
      ${interactive?'<text x="26" y="25" class="control-label">正面示意 · 左右按角色自身</text>':''}
    </svg>`;
  }
  function drawStick(svg, points) {
    const [nx,ny] = points.wusong_neck, by = ny + 102;
    svg.querySelector('.skeleton-head').setAttribute('cx',nx);
    svg.querySelector('.skeleton-head').setAttribute('cy',ny-56);
    svg.querySelector('.body-line').setAttribute('d', `M${nx} ${ny-29}V${by}M${nx-30} ${ny}H${nx+30}M${nx} ${by}L${nx-39} 291M${nx} ${by}L${nx+39} 291`);
    for (const key of humanIds.slice(0,2)) {
      const side = rods[key].side, sx = nx + (side==='left'?-30:30);
      const [x,y] = points[key], ex = (sx+x)/2+(side==='left'?-14:14), ey = (ny+y)/2+20;
      svg.querySelector('.'+side+'-line').setAttribute('d', `M${sx} ${ny}L${ex} ${ey}L${x} ${y}`);
      const shoulder = svg.querySelector('.shoulder-'+side); shoulder.setAttribute('cx',sx); shoulder.setAttribute('cy',ny);
    }
    for (const key of humanIds) {
      const [x,y] = points[key];
      for(const selector of [`[data-joint="${key}"]`,`[data-halo="${key}"]`]) { const el=svg.querySelector(selector);el.setAttribute('cx',x);el.setAttribute('cy',y); }
      const label=svg.querySelector(`[data-joint-label="${key}"]`);label.setAttribute('x',x+(key==='wusong_neck'?25:0));label.setAttribute('y',y+(key==='wusong_neck'?-10:-24));
      const el=svg.querySelector(`[data-joint="${key}"]`);
      if(el.getAttribute('role')==='slider') {el.setAttribute('aria-valuenow',Math.round(x));el.setAttribute('aria-valuetext',`水平 ${Math.round(x)}，垂直 ${Math.round(y)}；方向键调整`);}
    }
  }
  function mapPuppet(root, points) {
    const {offset,hands}=projectHuman(points);
    setPose(root,hands.left,hands.right,0);
    root.querySelectorAll('.puppet-person').forEach(p=>p.setAttribute('transform',`translate(${offset[0]} ${offset[1]})`));
  }
  function touchPage() {
    touch = resolveHuman(presets[0]);
    main.innerHTML = `${modeHeading('02','指尖皮影','不必熟悉操偶的技法。轻轻拖动，让皮影听懂你的指尖。')}<div class="touch-layout"><section class="screen-panel touch-preview"><div class="panel-bar"><span><i class="red-dot"></i>你的光影舞台</span><span>角色 · 武松</span></div><div class="puppet-preview">${stage({single:true,points:true})}<span class="preview-corner">指尖一动，光影相随</span></div><div class="preview-bottom"><span>${icon('spark')}每一个姿态，都是你的创作。</span><span class="small-pill">屏幕内同步</span></div></section><section class="controller-panel"><div class="controller-heading"><div><h2>指尖操偶台</h2><p>拖动双手与颈部主杆的圆点</p></div><span class="touch-symbol">${icon('touch')}</span></div>${stickman('touch-controller',true)}<div class="joint-legend"><span><i></i>双手</span><span><i></i>颈部主杆</span><small>支持触摸 / 鼠标 / 方向键</small></div><div class="preset-heading">从一个姿态开始</div><div class="preset-buttons">${presets.map((p,i)=>`<button type="button" data-preset="${i}" aria-pressed="${i===0}" class="${i===0?'selected':''}">${p.name}</button>`).join('')}</div><button type="button" class="reset-pose text-button" id="reset-pose">${icon('reset')}恢复初始姿态</button></section></div><div class="interaction-tip"><span class="tip-index">小 窍 门</span><span>武松以双手和颈部三点操偶。左右按角色自身命名；腰部和双脚随身体联动。</span></div>`;
    const svg = document.querySelector('#touch-controller');
    const update = () => { touch=resolveHuman(touch); drawStick(svg,touch); mapPuppet(main,touch); };
    function selectPreset(index) { touch = resolveHuman(presets[index]); main.querySelectorAll('[data-preset]').forEach((b,i)=>{b.classList.toggle('selected',i===index);b.setAttribute('aria-pressed',String(i===index));}); update(); }
    function moveJoint(key,x,y) {
      touch[key]=[x,y];
      main.querySelectorAll('[data-preset]').forEach(b=>{b.classList.remove('selected');b.setAttribute('aria-pressed','false');});
      update();
    }
    svg.querySelectorAll('[data-joint]').forEach(handle => {
      // Include the halo in the hit area to make the joint easier to touch.
      const hitArea = handle.parentElement;
      hitArea.onpointerdown = e => { if(e.button!==0 || !e.isPrimary) return; e.preventDefault(); dragging = handle.dataset.joint; hitArea.setPointerCapture(e.pointerId); handle.classList.add('dragging'); };
      hitArea.onpointermove = e => { if(dragging!==handle.dataset.joint || !hitArea.hasPointerCapture(e.pointerId)) return; const point = new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse()); moveJoint(dragging,point.x,point.y); };
      const end = () => { dragging=null; handle.classList.remove('dragging'); };
      hitArea.onpointerup = end; hitArea.onpointercancel=end; hitArea.onlostpointercapture=end;
      handle.onkeydown = e => { const dir = {ArrowLeft:[-5,0],ArrowRight:[5,0],ArrowUp:[0,-5],ArrowDown:[0,5]}[e.key]; if(!dir) return; e.preventDefault(); const key=handle.dataset.joint; moveJoint(key,touch[key][0]+dir[0],touch[key][1]+dir[1]); };
    });
    main.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>selectPreset(Number(b.dataset.preset)));
    document.querySelector('#reset-pose').onclick=()=>{selectPreset(0);announce('已恢复屏幕角色的初始姿态');}; update();
  }
  const poseSteps = [
    {title:'向两侧展开双臂',detail:'身体舒展，皮影也跟着打开姿态。',wusong_right:[38,135],wusong_left:[262,135],wusong_neck:[150,136]},
    {title:'缓缓举起双手',detail:'举手投足之间，让影子替你表达。',wusong_right:[63,66],wusong_left:[237,66],wusong_neck:[150,128]},
    {title:'轻轻侧身，亮个相',detail:'让身体的变化，成为角色的神情。',wusong_right:[59,133],wusong_left:[233,99],wusong_neck:[168,134]}
  ];
  function posePage() {
    main.innerHTML = `${modeHeading('03','以身入戏','这一次，你就是执影人。让身体的语言，变成幕布上的故事。')}<div class="pose-layout"><section class="body-panel"><div class="panel-bar"><span><i class="sage-dot"></i>姿态体验区</span><span id="pose-status">示范待开始</span></div><div class="pose-view"><div class="capture-corner top-left"></div><div class="capture-corner top-right"></div><div class="capture-corner bottom-left"></div><div class="capture-corner bottom-right"></div><span class="pose-view-label">BODY AS A BRUSH</span>${stickman('pose-skeleton')}<div class="scan-line"></div><span class="pose-view-note">颈点取双肩中点 · 示范骨架</span></div><div class="body-caption"><span class="pose-status-dot"></span><span id="pose-instruction">站到光影之间，让身体讲一个故事。</span></div></section><div class="mapping-bridge" aria-hidden="true"><span>姿态</span>${icon('arrow')}<span>光影</span></div><section class="screen-panel pose-preview"><div class="panel-bar"><span><i class="red-dot"></i>你的皮影分身</span><span>角色 · 武松</span></div><div class="puppet-preview">${stage({single:true,points:true})}</div><div class="body-caption"><span>${icon('spark')}</span><span id="pose-detail">你的每一次表达，都会在光影中得到回应。</span></div></section></div><div class="pose-bottom"><div class="pose-steps">${['展开双臂','举起双手','侧身亮相'].map((s,i)=>`<div data-pose-step="${i}"><span>${String(i+1).padStart(2,'0')}</span><div>${s}<small>${['舒展身体','让影子跟随','进入你的角色'][i]}</small></div></div>`).join('')}</div><div class="pose-action"><button type="button" class="primary-button" id="pose-start">${icon('pose')}体验姿态演示</button><span>先看一遍，找到入戏的感觉</span></div></div>`;
    const initial=resolveHuman(presets[0]);drawStick(document.querySelector('#pose-skeleton'),initial);mapPuppet(main,initial);
    document.querySelector('#pose-start').onclick = () => { posePlaying=!posePlaying; if(poseTime>=12) {poseTime=0;poseStep=-1;} updatePose(); };
    updatePose();
  }
  function updatePose() {
    const index = Math.min(2,Math.floor(poseTime/4));
    const button = document.querySelector('#pose-start');
    button.innerHTML = `${icon(posePlaying?'pose':'play')}${posePlaying?'暂停姿态演示':poseTime>=12?'再体验一次':poseTime>0?'继续姿态演示':'体验姿态演示'}`;
    document.querySelector('#pose-status').textContent = posePlaying ? '示范姿态播放中' : poseTime>=12?'示范已完成':poseTime>0?'示范已暂停':'示范待开始';
    main.querySelector('.pose-view').classList.toggle('is-demonstrating',posePlaying);
    if ((posePlaying || poseTime>0) && index!==poseStep) {
      poseStep=index; const state = poseSteps[index], points=resolveHuman(state);drawStick(document.querySelector('#pose-skeleton'),points);mapPuppet(main,points);
      document.querySelector('#pose-instruction').textContent=state.title; document.querySelector('#pose-detail').textContent=state.detail;
      main.querySelectorAll('[data-pose-step]').forEach((el,i)=>el.classList.toggle('active',index===i));
    }
  }
  function render() {
    const hash = location.hash.slice(1) || 'home';
    if(hash==='main' && main.childElementCount) { main.focus({preventScroll:true}); main.scrollIntoView({behavior:'instant'}); return; }
    const next = ['classic','touch','pose'].includes(hash)?hash:'home';
    const turnPage = main.childElementCount > 0 && next !== route && next !== 'home';
    window.TheatrePageTurn.finish();
    // A modes anchor scroll should not replace the home DOM or lose focus.
    if(hash==='modes' && route==='home' && document.querySelector('#modes')) {document.querySelectorAll('[data-nav]').forEach(a=>{if(a.dataset.nav==='modes')a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});document.querySelector('#modes').scrollIntoView({behavior:motionPaused?'instant':'smooth',block:'start'});return;}
    route=next; play=false; elapsed=0; posePlaying=false; poseTime=0; poseStep=-1; dragging=null;
    clearTimeout(toastTimer); document.querySelector('#toast').classList.remove('show'); document.querySelector('#toast').textContent='';
    document.body.dataset.page=route;
    ({home,classic,touch:touchPage,pose:posePage})[route]();
    document.title=`${{home:'影境 · 皮影互动体验',classic:'经典传唱 · 武松打虎',touch:'指尖皮影 · 影境',pose:'以身入戏 · 影境'}[route]}`;
    document.querySelectorAll('[data-nav]').forEach(a=>{if(route==='home'&&a.dataset.nav===(hash==='modes'?'modes':'home'))a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    window.scrollTo({top:0,left:0,behavior:'instant'}); main.focus({preventScroll:true});
    if(hash==='modes')document.querySelector('#modes').scrollIntoView({block:'start'});
    if(turnPage) window.TheatrePageTurn.play(next,motionPaused);
  }
  function applyMotion() {document.body.classList.toggle('motion-paused',motionPaused);const b=document.querySelector('#motion-toggle');b.setAttribute('aria-pressed',String(motionPaused));b.setAttribute('aria-label',motionPaused?'开启界面动效':'暂停界面动效');b.title=motionPaused?'开启界面动效':'暂停界面动效';b.textContent=motionPaused?'▷':'Ⅱ';}
  document.querySelector('#motion-toggle').onclick=()=>{motionPaused=!motionPaused;if(motionPaused)window.TheatrePageTurn.finish();applyMotion();};
  const dialog=document.querySelector('#about-dialog');
  document.querySelector('#about-open').onclick=()=>dialog.showModal();
  dialog.querySelectorAll('.dialog-close,.dialog-done').forEach(b=>b.onclick=()=>dialog.close());
  dialog.onclick=e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}};
  window.addEventListener('hashchange',render);
  document.addEventListener('visibilitychange',()=>{lastTime=0;});
  function frame(timestamp) {
    const dt=lastTime?Math.min((timestamp-lastTime)/1000,.1):0; lastTime=timestamp;
    if(!document.hidden && !dialog.open) {
      if(route==='classic'&&play){elapsed=Math.min(DURATION,elapsed+dt);if(elapsed>=DURATION)play=false;updatePlayer();}
      if(route==='pose'&&posePlaying){poseTime=Math.min(12,poseTime+dt);if(poseTime>=12)posePlaying=false;updatePose();}
      if(route==='home'&&!motionPaused) setPose(main,[-81,-46+Math.sin(timestamp/1200)*10],[102,-24+Math.sin(timestamp/1500)*12],Math.sin(timestamp/1800)*1.5);
    }
    requestAnimationFrame(frame);
  }
  applyMotion();render();requestAnimationFrame(frame);
})();
