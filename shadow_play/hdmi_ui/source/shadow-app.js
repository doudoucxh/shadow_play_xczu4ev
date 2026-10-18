(() => {
  const root = document.getElementById('shadow-theatre-preview');
  const query = s => root.querySelector(s);
  const all = s => [...root.querySelectorAll(s)];
  const storage = globalThis.openai;
  const batchCollection=globalThis.ShadowBatchCollection?.active?globalThis.ShadowBatchCollection:null;
  const training = batchCollection?globalThis.ShadowTrainingCollector?.create({host:storage,acceptedSamples:globalThis.ShadowAcceptedTrainingSamples||[],maxPromptBytes:1900000,actions:batchCollection.actions}):null;
  const widgetWriterId=globalThis.crypto?.randomUUID?.()||'draw-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  let widgetWriteSeq=0;
  let trainingStrokes=[], trainingInkVersion=0, trainingPointerType='unknown', trainingSending=false,trainingDraftResampled=false,trainingOriginalPointCount=0;
  function withElbows(pose) {
    for(const [side,shoulderX] of [['left',.34],['right',.66]]){
      const elbow=pose[side+'Elbow'];
      if(Array.isArray(elbow)&&elbow.length===2&&elbow.every(Number.isFinite))continue;
      const wrist=pose[side+'Wrist'];
      const distance=Math.hypot(wrist[0]-shoulderX,wrist[1]-.32);
      pose[side+'Elbow']=[(shoulderX+wrist[0])/2+(side==='left'?-1:1)*Math.min(.06,.02+distance*.08),(.32+wrist[1])/2+Math.max(-.015,Math.min(.04,(.32-wrist[1])*.08))];
    }
    return pose;
  }
  const neutral = () => withElbows({head:[.5,.18],leftWrist:[.22,.68],rightWrist:[.78,.68]});
  const presets = {
    neutral:neutral(),
    open:withElbows({head:[.5,.18],leftWrist:[.06,.31],rightWrist:[.94,.31]}),
    raise:withElbows({head:[.5,.18],leftWrist:[.22,.08],rightWrist:[.78,.08]}),
    strike:withElbows({head:[.5,.18],leftWrist:[.04,.34],rightWrist:[.63,.34]})
  };
  const names = {home:'戏台首页',classic:'经典表演',touch:'笔墨成戏',body:'以身入戏'};
  const revision = 'actor-ink-screw-v11';
  const actorLayoutRevision = 'wusong-left-v1';
  const humanModelId = String(globalThis.ShadowSketchModel?.metadata?.model||'unavailable');
  const recognizerId = humanModelId+'|'+String(globalThis.ShadowSketchTopology?.metadata?.model||'raster-only');
  const poseRevision = 'standard-actions-v1';
  const actorNames = {wusong:'武松',tiger:'老虎'};
  const actionNames = {
    wusong:{neutral:'站姿',open:'展臂',raise:'举手',strike:'出拳',left_raise:'左举手',right_raise:'右举手',guard:'护头',akimbo:'叉腰',salute:'准备出拳',point:'指路'},
    tiger:{neutral:'站立'}
  };
  const drawingHints = {wusong:'画出头部、身体与双臂，再点击识别',tiger:'老虎 · 站立'};
  for(const action of globalThis.ShadowActionCatalog?.actions||[])actionNames.wusong[action.id]=action.name;
  const state = {page:'home',menuOpen:false,progress:0,playing:false,selectedActor:'wusong',
    actors:{wusong:{position:.28,pose:neutral(),poseAspect:1,poseSource:'model',action:'neutral',strokes:[],result:drawingHints.wusong},tiger:{position:.72,pose:null,action:'neutral',strokes:[],result:drawingHints.tiger}},bodyDemo:false,bodyPose:'neutral'};
  const design = {gold:'#d6b477',red:'#a53832'};
  let lastTime = 0;
  let drawFrame = 0;
  let homePaintStamp='',artworkEpoch=0;
  let drawDeferred = false;
  let animation = null;
  let inkPointer = null;
  let inkFrame = 0;
  const inkVersions = {wusong:0,tiger:0};
  let lastInkStamp = '';
  let stageDrag = null;
  let cameraStatus = 'off';
  let cameraMessage = '摄像头未开启';
  let cameraPose = null;
  let poseSending = false;
  let recognitionRun = 0;
  let recognitionPending = false;
  let savedFrames=[],selectedFrame=-1,sequencePlaying=false,sequenceTimer=0,sequenceKey='',sequenceResume=false;
  const frameJoints=['head','leftShoulder','rightShoulder','leftElbow','rightElbow','leftWrist','rightWrist'];
  const frameActions=Object.keys(actionNames.wusong);
  let turning = false;
  let finishTurn = null;
  const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
  let reduceMotion = motionPreference.matches;
  const bookEffects = globalThis.ShadowBookEffects?.create({root:query('.shadow-app'),emberCanvas:query('#shadow-embers'),modeCanvases:all('.shadow-mode-edge'),reducedMotion:reduceMotion});
  const pageTurn = globalThis.ShadowPageTurn?.create({canvas:query('#shadow-page-turn'),reducedMotion:reduceMotion});
  const board = globalThis.ShadowBoardClient?.create({root});
  const cameraPreview = globalThis.ShadowCameraPreview?.create({video:query('#shadow-camera-video'),canvas:query('#shadow-body-stick'),empty:query('[data-camera-empty]'),board,
    onState:(status,message)=>{cameraStatus=status;cameraMessage=message||'摄像头未开启';if(status!=='live')cameraPose=null;renderCamera();scheduleDraw();},
    onPose:pose=>{
      if(state.page!=='body')return;
      // Never synthesize detector elbows or retain the previous detected pose.
      cameraPose=pose?clonePose(pose):null;renderCamera();scheduleDraw();
      if(cameraPose&&!poseSending&&board?.status?.motion?.ready&&board.status.motion.puppet){
        poseSending=true;board.control({kind:'pose',pose:cameraPose}).finally(()=>{poseSending=false;});
      }
    }});
  globalThis.ShadowCameraFeed = Object.freeze({
    updatePose:pose=>!board&&(cameraPreview?.updatePose(pose)||false),
    updateFrame:frame=>!board&&(cameraPreview?.updateFrame(frame)||false)
  });
  function announce(message) { query('#shadow-announcement').textContent=message; }
  function clonePose(pose) { return Object.fromEntries(Object.entries(pose).filter(([,point])=>Array.isArray(point)&&point.length===2&&point.every(Number.isFinite)).map(([name,point])=>[name,[...point]])); }
  function standardPose(action) { return globalThis.ShadowStageArt.standardPose(action); }
  function packFrames() {
    const bytes=new Uint8Array(savedFrames.length*36),view=new DataView(bytes.buffer);
    savedFrames.forEach((frame,index)=>{
      let offset=index*36;view.setUint8(offset++,frameActions.indexOf(frame.action));view.setUint8(offset++,1);
      for(const value of [frame.aspect/10,frame.wusong,frame.tiger,...frameJoints.flatMap(key=>frame.pose[key])]){view.setUint16(offset,Math.round(Math.max(0,Math.min(1,value))*10000));offset+=2;}
    });
    return btoa(String.fromCharCode(...bytes));
  }
  function restoreFrames(encoded,index) {
    savedFrames=[];selectedFrame=-1;
    try{
      if(typeof encoded!=='string'||encoded.length>4800)return;
      const bytes=Uint8Array.from(atob(encoded),ch=>ch.charCodeAt(0));if(bytes.length%36)return;
      const view=new DataView(bytes.buffer);
      for(let start=0;start<bytes.length;start+=36){
        const action=frameActions[view.getUint8(start)];if(!action||view.getUint8(start+1)!==1)throw new Error('frame');
        let offset=start+2;const values=[];for(let n=0;n<17;n++,offset+=2){const value=view.getUint16(offset)/10000;if(value>1)throw new Error('coordinate');values.push(value);}
        const [aspect,wusong,tiger,...points]=values;if(aspect<=0)throw new Error('aspect');
        savedFrames.push({action,aspect:1,wusong,tiger,pose:standardPose(action)});
      }
      selectedFrame=savedFrames.length?Math.max(0,Math.min(savedFrames.length-1,Number.isInteger(index)?index:0)):-1;
    }catch{savedFrames=[];}
  }
  function stopSequence() {
    if(sequenceTimer)clearTimeout(sequenceTimer);sequenceTimer=0;sequencePlaying=false;sequenceResume=false;
  }
  function renderSequence() {
    const collecting=training?.active===true,panel=query('.shadow-sequence'),saveButton=query('[data-action="save-frame"]');
    query('[data-screen="touch"]').dataset.collecting=String(collecting);
    panel.hidden=collecting;saveButton.hidden=collecting;
    saveButton.disabled=recognitionPending||sequencePlaying||savedFrames.length>=100;
    query('[data-sequence-count]').textContent='动作序列 · '+(selectedFrame>=0?(selectedFrame+1)+'/':'')+savedFrames.length;
    const play=query('[data-action="play-sequence"]');play.disabled=!savedFrames.length||recognitionPending;play.textContent=sequencePlaying?'暂停播放':'顺序播放';play.setAttribute('aria-pressed',String(sequencePlaying));
    query('[data-action="delete-frame"]').disabled=selectedFrame<0||sequencePlaying;
    const key=savedFrames.length+':'+savedFrames.map(frame=>frame.action).join('|'),strip=query('.shadow-sequence-frames');
    if(key!==sequenceKey||!strip.children.length||strip.querySelectorAll('[data-frame]').length!==savedFrames.length){
      sequenceKey=key;strip.replaceChildren();
      if(!savedFrames.length){const empty=document.createElement('span');empty.textContent='画好后存入动作，即可依次播放';strip.append(empty);}
      savedFrames.forEach((frame,index)=>{const button=document.createElement('button');button.type='button';button.className='shadow-secondary cursor-interaction';button.dataset.frame=String(index);button.textContent=String(index+1).padStart(2,'0')+' '+actionNames.wusong[frame.action];button.addEventListener('click',()=>{stopSequence();applyFrame(index);save();});strip.append(button);});
    }
    for(const button of strip.querySelectorAll('[data-frame]'))button.setAttribute('aria-pressed',String(Number(button.dataset.frame)===selectedFrame));
  }
  function applyFrame(index) {
    const frame=savedFrames[index];if(!frame)return;
    selectedFrame=index;const actor=state.actors.wusong;
    actor.pose=standardPose(frame.action);actor.poseAspect=1;actor.poseSource='standard';actor.action=frame.action;
    actor.result='武松 · '+actionNames.wusong[frame.action];
    query('[data-touch-caption]').textContent=actor.result;
    state.actors.wusong.position=frame.wusong;state.actors.tiger.position=frame.tiger;
    // Playing a saved scene does not replace the unfinished drawing in the pad.
    renderPosition();renderSequence();drawCurrentScreen();
    query('.shadow-sequence-frames [data-frame="'+index+'"]').scrollIntoView({block:'nearest',inline:'nearest'});
  }
  function playSequenceStep() {
    if(!sequencePlaying||turning||state.page!=='touch'){stopSequence();return;}
    applyFrame(selectedFrame+1);
    sequenceTimer=setTimeout(()=>{
      sequenceTimer=0;
      if(selectedFrame>=savedFrames.length-1){stopSequence();renderSequence();save();announce('动作已依次播放完毕');}
      else playSequenceStep();
    },1200);
  }
  function currentActor() { return state.actors[state.selectedActor] || null; }
  function currentStrokes() { return training?.active?trainingStrokes:state.actors.wusong.strokes; }
  function touchArtOptions() {
    const pose=standardPose(state.actors.wusong.action);
    return {mode:'touch',selectedActor:state.selectedActor,controlPose:pose,poseAspect:1,
      actors:Object.fromEntries(Object.entries(state.actors).map(([name,actor])=>[name,{position:actor.position,pose:name==='wusong'?pose:null,poseAspect:1,poseSource:'standard',action:actor.action}]))};
  }
  function compactStrokes(source,limit=192) {
    const strokes=source.filter(s=>s.length);let budget=Math.max(limit,strokes.length),weight=strokes.reduce((sum,s)=>sum+s.length,0);
    return strokes.map((stroke,index)=>{
      const count=Math.min(stroke.length,budget-(strokes.length-index-1),Math.max(1,Math.floor(budget*stroke.length/weight)));
      budget-=count;weight-=stroke.length;
      return Array.from({length:count},(_,i)=>stroke[count===1?0:Math.round(i*(stroke.length-1)/(count-1))].map(v=>Math.round(v*1000)/1000));
    });
  }
  function save() {
    const actors=Object.fromEntries(Object.entries(state.actors).map(([name,actor])=>[name,{...actor,strokes:compactStrokes(actor.strokes)}]));
    const collectionSnapshot=training?.snapshot(),collectionSample=collectionSnapshot?.pending||collectionSnapshot?.lastSubmitted||null;
    const sampleIsDraft=collectionSample?.task.id===training?.task.id;
    const privateContent={revision,actorLayoutRevision,humanModelId,poseRevision,widgetWriterId,widgetWriteSeq:++widgetWriteSeq,page:state.page,menuOpen:state.menuOpen,progress:state.progress,selectedActor:state.selectedActor,actors,sequence:packFrames(),sequenceIndex:selectedFrame,bodyDemo:state.bodyDemo,bodyPose:state.bodyPose,training:training?{collector:collectionSnapshot,draft:sampleIsDraft?[]:compactStrokes(trainingStrokes),pointerType:trainingPointerType,originalPointCount:Math.max(trainingOriginalPointCount,trainingStrokes.flat().length)}:null};
    privateContent.recognizerId=recognizerId;
    const modelContent={page:names[state.page],menu:state.menuOpen?'展开':'收起',selectedActor:actorNames[state.selectedActor]||'未选择',actors:Object.fromEntries(Object.entries(actors).map(([name,actor])=>[actorNames[name],{action:actionNames[name][actor.action],screwPosition:Math.round(actor.position*100)+'%'}])),bodyDemo:state.bodyDemo,training:training?.active||collectionSample?{task:training.task,pointCount:trainingStrokes.reduce((n,s)=>n+s.length,0),submitted:training.submitted,sample:collectionSample}:null};
    if(new TextEncoder().encode(JSON.stringify({modelContent,privateContent})).length>15500){for(const name of Object.keys(actors))actors[name].strokes=compactStrokes(actors[name].strokes,128);if(privateContent.training)privateContent.training.draft=compactStrokes(privateContent.training.draft,128);}
    if(storage?.setWidgetState)storage.setWidgetState({modelContent,privateContent}).catch(()=>{});
  }
  function load(snapshot) {
    const saved=snapshot?.privateContent;
    if(!saved || saved.revision!==revision || turning) return;
    // Host acknowledgements must not replace live full strokes with the compact persistence copy.
    if(saved.widgetWriterId===widgetWriterId&&Number.isInteger(saved.widgetWriteSeq)&&saved.widgetWriteSeq<=widgetWriteSeq)return;
    stopSequence();restoreFrames(saved.sequence,saved.sequenceIndex);
    recognitionRun++;recognitionPending=false;inkPointer=null;stageDrag=null;
    delete query('[data-art="touch"]').dataset.dragging;
    if(names[saved.page]) state.page=saved.page;
    if(state.page!=='body')cameraPreview?.stop();
    state.menuOpen=saved.menuOpen===true;
    if(Number.isFinite(saved.progress)) state.progress=Math.max(0,Math.min(100,saved.progress));
    state.selectedActor=actorNames[saved.selectedActor]?saved.selectedActor:'wusong';
    for(const name of Object.keys(actorNames)){
      const actor=saved.actors?.[name],target=state.actors[name];if(!actor)continue;
      if(Number.isFinite(actor.position))target.position=Math.max(0,Math.min(1,actor.position));
      if(actionNames[name][actor.action])target.action=actor.action;
      if(name==='wusong'&&actor.pose&&Object.keys(neutral()).every(k=>Array.isArray(actor.pose[k])&&actor.pose[k].length===2&&actor.pose[k].every(v=>Number.isFinite(v)&&v>=0&&v<=1)))target.pose=clonePose(actor.pose);
      if(name==='wusong'&&Number.isFinite(actor.poseAspect)&&actor.poseAspect>.1&&actor.poseAspect<10)target.poseAspect=actor.poseAspect;
      if(name==='wusong')target.poseSource=actor.poseSource==='strokes'?'strokes':'model';
      if(Array.isArray(actor.strokes))target.strokes=actor.strokes.slice(0,128).filter(s=>Array.isArray(s)&&s.every(p=>Array.isArray(p)&&p.length===2&&p.every(v=>Number.isFinite(v)&&v>=0&&v<=1))).map(s=>s.slice(0,512));
      if(name==='wusong')target.inkAspect=Number.isFinite(actor.inkAspect)&&actor.inkAspect>.05&&actor.inkAspect<20?actor.inkAspect:null;
      if(typeof actor.result==='string')target.result=actor.result.slice(0,60);
      if(name==='wusong')target.draftDirty=actor.draftDirty!==false||!['strokes','standard'].includes(actor.poseSource);
      const compatibleModel=globalThis.ShadowSketchModel?.metadata?.compatible_models?.includes(saved.humanModelId);
      const unsupportedAction=name==='wusong'&&!actionNames.wusong[actor.action];
      if(name==='wusong'&&(saved.humanModelId!==humanModelId&&!compatibleModel||saved.recognizerId!==recognizerId||unsupportedAction)){
        target.pose=neutral();target.poseAspect=1;target.poseSource='model';target.action='neutral';
        target.draftDirty=true;
        target.result=target.strokes.length?'画稿已保留，请点击识别动作':drawingHints.wusong;
      }
      else if(name==='wusong'&&actor.result?.startsWith('武松 · '))target.result='武松 · '+actionNames.wusong[target.action];
      if(name==='wusong'){target.pose=standardPose(target.action);target.poseAspect=1;target.poseSource='standard';}
      if(name==='tiger'){target.action='neutral';target.pose=null;target.result=drawingHints.tiger;}
    }
    // Swap only the saved rail positions once. Each actor keeps its own pose and ink.
    if(saved.actorLayoutRevision!==actorLayoutRevision&&Number.isFinite(saved.actors?.wusong?.position)&&Number.isFinite(saved.actors?.tiger?.position)){
      [state.actors.wusong.position,state.actors.tiger.position]=[state.actors.tiger.position,state.actors.wusong.position];
    }
    state.bodyDemo=saved.bodyDemo===true;
    if(presets[saved.bodyPose]) state.bodyPose=saved.bodyPose;
    if(training&&saved.training){training.restore(saved.training.collector);const candidate=training.getPending()||training.getLastSubmitted();const source=saved.training.draft?.length?saved.training.draft:candidate?.task.id===training.task.id?candidate.strokes:[];trainingStrokes=Array.isArray(source)?source.slice(0,128).filter(s=>Array.isArray(s)&&s.every(p=>Array.isArray(p)&&p.length===2&&p.every(v=>Number.isFinite(v)&&v>=0&&v<=1))).map(s=>s.slice(0,512)):[];trainingPointerType=String(saved.training.pointerType||'unknown');trainingDraftResampled=trainingStrokes.length>0&&!(batchCollection&&saved.training.draftRaw===true);trainingOriginalPointCount=saved.training.originalPointCount||trainingStrokes.flat().length;trainingInkVersion++;if(training.active)state.selectedActor='wusong';}
    lastInkStamp='';
    render();
  }
  function setPage(page) {
    if(!names[page] || turning) return;
    if(state.page===page){if(page==='home' && state.menuOpen){state.menuOpen=false;render();save();}return;}
    state.playing=false;
    stopSequence();
    if(page!=='body')cameraPreview?.stop();
    recognitionRun++;recognitionPending=false;
    stageDrag=null;
    delete query('[data-art="touch"]').dataset.dragging;
    inkPointer=null;if(inkFrame){cancelAnimationFrame(inkFrame);inkFrame=0;}
    if(animation!==null){cancelAnimationFrame(animation);animation=null;}
    lastTime=0;
    if(motionPreference.matches || !pageTurn) {
      state.page=page;state.menuOpen=false;render();if(page==='home')drawCurrentScreen();save();announce('已进入'+names[page]);return;
    }
    turning=true;
    if(drawFrame){cancelAnimationFrame(drawFrame);drawFrame=0;}
    if(bookEffects?.pause)bookEffects.pause();else bookEffects?.setActive(false);
    const app=query('.shadow-app');
    const overlay=query('#shadow-book-transition');
    app.setAttribute('aria-busy','true');
    app.dataset.turning='true';
    for(const el of all('.shadow-header,main'))el.inert=true;
    overlay.hidden=false;
    let fallback;
    const closing=page==='home',sourcePage=state.page;
    let destinationPrepared=false;
    const prepareDestination=()=>{
      if(destinationPrepared)return;destinationPrepared=true;
      state.page=page;state.menuOpen=false;
      if(closing){
        // The cover is fully opaque here. Lay out and paint the final home
        // before its fade starts, instead of stretching a menu-sized old frame
        // and replacing it when the cover disappears.
        render();drawCurrentScreen();drawDeferred=false;
      }else{render();drawCurrentScreen();drawDeferred=false;}
    };
    const done=()=>{
      if(!turning)return;
      prepareDestination();
      clearTimeout(fallback);
      overlay.hidden=true;
      turning=false;finishTurn=null;
      delete app.dataset.turning;
      app.removeAttribute('aria-busy');
      for(const el of all('.shadow-header,main'))el.inert=false;
      bookEffects?.setPage(state.page,true);
      if(drawDeferred)scheduleDraw();save();announce(closing?'已合卷，返回主界面':'已翻开'+names[page]);
      (closing?query('[data-action="open-menu"]'):query('[data-screen="'+state.page+'"] .shadow-back'))?.focus({preventScroll:true});
    };
    finishTurn=()=>{pageTurn.finish();done();};
    if(!closing)prepareDestination();
    pageTurn.play({title:names[closing?sourcePage:page],direction:closing?'close':'open',onCovered:closing?prepareDestination:undefined,onComplete:done});
    if(turning)fallback=setTimeout(finishTurn,2800);
  }
  function fitCanvas(canvas) {
    const b=canvas.getBoundingClientRect();
    if(b.width<1||b.height<1) return null;
    const dpr=Math.min(devicePixelRatio||1,2);
    if(canvas.width!==Math.round(b.width*dpr)||canvas.height!==Math.round(b.height*dpr)) {canvas.width=Math.round(b.width*dpr);canvas.height=Math.round(b.height*dpr);}
    const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
    return {ctx,w:b.width,h:b.height};
  }
  function artPose(p) {
    const result={};
    for(const [key,[x,y]] of Object.entries(p)) {
      const left=key.startsWith('left');
      result[key]=[(left ? .423 : .475)+(x-(left ? .34 : .66))*.28,.497+(y-.32)*.55];
    }
    return result;
  }
  function drawStick(canvas,pose,body=false) {
    const fitted=fitCanvas(canvas);if(!fitted)return;
    const {ctx,w,h}=fitted;ctx.clearRect(0,0,w,h);
    const top=body?18:10;
    const usableH=h-34;
    const coord=point=>[(body ? .05+point[0]*.9 : point[0])*w,top+point[1]*usableH];
    const shoulders={leftShoulder:[.34,.32],rightShoulder:[.66,.32]};
    const joints={head:pose.head||[.5,.18],...shoulders,...pose,leftHip:[.4,.73],rightHip:[.6,.73]};
    const line=(a,b,color,width)=>{const p=coord(a),q=coord(b);ctx.beginPath();ctx.moveTo(...p);ctx.lineTo(...q);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineCap='round';ctx.stroke();};
    ctx.strokeStyle='#9a9274';ctx.lineWidth=1;
    if(body) {
      ctx.setLineDash([5,6]);ctx.strokeRect(w*.08,7,w*.84,h-34);ctx.setLineDash([]);
      for(const [x,y,dx,dy] of [[.08,7,1,1],[.92,7,-1,1],[.08,h-27,1,-1],[.92,h-27,-1,-1]]) {ctx.strokeStyle='#6d7253';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(x*w+dx*13,y);ctx.lineTo(x*w,y);ctx.lineTo(x*w,y+dy*13);ctx.stroke();}
    } else {
      ctx.fillStyle='#2b2721';ctx.beginPath();ctx.ellipse(w*.5,h-30,w*.23,5,0,0,Math.PI*2);ctx.fill();
    }
    const color=body&&!state.bodyDemo?'#77745d':'#535d43';
    const width=body?3:4;
    line([.5,.26],[.5,.64],color,width);
    line(shoulders.leftShoulder,shoulders.rightShoulder,color,width);
    line([.5,.64],[.4,.73],color,width);line([.5,.64],[.6,.73],color,width);
    if(!body){line([.4,.73],[.34,.88],color,width);line([.6,.73],[.66,.88],color,width);}
    line(shoulders.leftShoulder,pose.leftElbow,color,width);line(pose.leftElbow,pose.leftWrist,color,width);
    line(shoulders.rightShoulder,pose.rightElbow,color,width);line(pose.rightElbow,pose.rightWrist,color,width);
    const head=coord(joints.head);ctx.beginPath();ctx.arc(head[0],head[1],Math.min(w*.072,usableH*.068),0,Math.PI*2);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();
    const visibleJoints=body?Object.entries(joints):Object.entries(pose);
    for(const [name,point] of visibleJoints){const [x,y]=coord(point);ctx.beginPath();ctx.arc(x,y,body?4:7,0,Math.PI*2);ctx.fillStyle=body?color:design.gold;ctx.fill();if(!body){ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fillStyle='#29221a';ctx.fill();}}
  }
  function drawingPaper(width,height) {
    const actor=state.actors.wusong;
    if(!training?.active&&actor.strokes.length&&!(actor.inkAspect>0))actor.inkAspect=width/height;
    return globalThis.ShadowSketchPaper.fit(width,height,training?.active?width/height:actor.inkAspect||width/height);
  }
  function drawSketch() {
    const fitted=fitCanvas(query('#shadow-touch-stick'));if(!fitted)return;
    const {ctx,w,h}=fitted,strokes=currentStrokes();
    const stamp=[training?.active?'training':'wusong',training?.active?trainingInkVersion:inkVersions.wusong,w,h,ctx.canvas.width,ctx.canvas.height].join(':');
    if(stamp===lastInkStamp)return;lastInkStamp=stamp;
    ctx.clearRect(0,0,w,h);
    const paper=drawingPaper(w,h);ctx.save();ctx.translate(paper.x,paper.y);
    if(globalThis.ShadowInkBrush){globalThis.ShadowInkBrush.draw(ctx,strokes,paper.width,paper.height,{activeStrokeIndex:inkPointer?strokes.indexOf(inkPointer.stroke):-1});ctx.restore();return;}
    ctx.strokeStyle='#554a35';ctx.fillStyle='#554a35';ctx.lineWidth=2.5;ctx.lineCap='round';ctx.lineJoin='round';
    for(const stroke of strokes){if(!stroke.length)continue;ctx.beginPath();ctx.moveTo(stroke[0][0]*paper.width,stroke[0][1]*paper.height);for(const p of stroke.slice(1))ctx.lineTo(p[0]*paper.width,p[1]*paper.height);ctx.stroke();if(stroke.length===1){ctx.beginPath();ctx.arc(stroke[0][0]*paper.width,stroke[0][1]*paper.height,1.25,0,Math.PI*2);ctx.fill();}}
    ctx.restore();
  }
  function scheduleInkDraw(){if(turning||state.page!=='touch'||inkFrame)return;inkFrame=requestAnimationFrame(()=>{inkFrame=0;if(!turning&&state.page==='touch')drawSketch();});}
  function drawCurrentScreen() {
    const screen=query('[data-screen="'+state.page+'"]');
    for(const canvas of screen?.querySelectorAll('[data-art]')||[]) {
      const fitted=fitCanvas(canvas);if(!fitted)continue;
      const mode=canvas.dataset.art;
      const homeStamp=mode==='home'?[canvas.width,canvas.height,fitted.w,fitted.h,state.progress,artworkEpoch].join(':'):'';
      if(mode==='home'&&homeStamp===homePaintStamp)continue;
      const pose=mode==='touch'?artPose(state.actors.wusong.pose):mode==='body'&&cameraPose?artPose(cameraPose):undefined;
      const controlPose=mode==='touch'?state.actors.wusong.pose:mode==='body'?cameraPose:undefined;
      if(globalThis.ShadowStageArt) globalThis.ShadowStageArt.draw(fitted.ctx,fitted.w,fitted.h,{mode,pose,controlPose,time:state.progress/100,guide:false,...(mode==='touch'?touchArtOptions():{})});
      if(mode==='home')homePaintStamp=homeStamp;
    }
    if(state.page==='touch')drawSketch();
    if(state.page==='body')cameraPreview?.draw();
  }
  function draw() {
    drawFrame=0;
    if(turning){drawDeferred=true;return;}
    drawDeferred=false;drawCurrentScreen();
  }
  function scheduleDraw() {
    if(turning){drawDeferred=true;return;}
    if(!drawFrame)drawFrame=requestAnimationFrame(draw);
  }
  function renderProgress() {
    const progress=Math.round(state.progress);
    query('#shadow-progress').value=progress;
    query('#shadow-progress-value').textContent=progress+'%';
    const chapter=Math.min(3,Math.floor(progress/25));
    const labels=['第一幕 · 景阳冈','第二幕 · 猛虎现身','第三幕 · 赤手搏虎','第四幕 · 英雄落幕'];
    query('[data-classic-caption]').textContent=labels[chapter];
    for(const b of all('[data-chapter]')) b.setAttribute('aria-pressed',String(+b.dataset.chapter===chapter));
  }
  function renderPosition() {
    const actor=currentActor(),input=query('#shadow-actor-position');
    input.disabled=!actor;
    input.value=actor?Math.round(actor.position*100):50;
    query('[data-position-label]').textContent=actor?actorNames[state.selectedActor]+'丝杆目标（屏幕预览）':'丝杆目标（屏幕预览）';
    query('[data-position-value]').textContent=actor?Math.round(actor.position*100)+'%':'—';
    input.setAttribute('aria-label',actor?actorNames[state.selectedActor]+'丝杆位置':'先选择角色再调整丝杆位置');
    input.setAttribute('aria-valuetext',actor?actorNames[state.selectedActor]+'屏幕目标 '+Math.round(actor.position*100)+'%，非实测位置':'未选择角色');
    const stage=query('[data-art="touch"]');
    stage.dataset.selectedActor=state.selectedActor||'';
    for(const name of Object.keys(actorNames))stage.dataset[name+'Position']=state.actors[name].position.toFixed(4);
  }
  function renderTouch() {
    const actor=state.actors.wusong,selected=true;
    const collecting=training?.active===true;
    for(const button of all('[data-touch-actor]')){button.setAttribute('aria-pressed',String(button.dataset.touchActor===state.selectedActor));button.disabled=collecting||trainingSending;}
    const trainingButton=query('[data-action="toggle-training"]');trainingButton.setAttribute('aria-pressed',String(collecting));trainingButton.textContent=collecting?'返回':'采集';trainingButton.disabled=trainingSending;trainingButton.setAttribute('aria-label',collecting?'结束采集，返回操控画稿':'采集真实手绘训练样本');
    query('[data-drawing-title]').textContent='武松动作画板';
    query('[data-touch-caption]').textContent=collecting?(training.message||'第'+training.task.number+'题：'+training.task.label):selected?actor.result:'选择武松或老虎，再画出动作';
    query('#shadow-touch-stick').setAttribute('aria-disabled',String(!selected));
    query('#shadow-touch-stick').style.pointerEvents=selected?'auto':'none';
    query('#shadow-touch-stick').setAttribute('aria-label','武松动作画布，'+drawingHints.wusong);
    query('.shadow-drawing-wrap').dataset.enabled=String(selected);
    query('[data-action="recognize-drawing"]').disabled=!selected||recognitionPending||trainingSending;
    query('[data-action="recognize-drawing"]').textContent=collecting?(trainingSending?'提交中…':training.submitted?'下一张':training.getPending()?'重试提交':'提交样本'):recognitionPending?'识别中…':'识别动作';
    query('[data-action="clear-drawing"]').disabled=!selected||trainingSending||!!(collecting&&training.getPending());
    query('[data-action="clear-drawing"]').textContent=collecting&&training.submitted?'复制样本':'重画';
    query('[data-art="touch"]').setAttribute('aria-label','可选择并左右拖动的武松和老虎皮影，调整各自丝杆位置');
    renderPosition();
    renderSequence();
    batchCollection?.render({task:training?.task,submitted:training?.submitted,sending:trainingSending,collecting,message:training?.message});
  }
  function renderCamera() {
    const button=query('[data-action="toggle-camera"]');if(!button)return;
    const active=['starting','waiting','live'].includes(cameraStatus);
    button.disabled=false;
    button.textContent=active?'停止识别':board?'开启姿态识别':'开启本地预览';
    button.setAttribute('aria-pressed',String(active));
    query('[data-body-status]').textContent=cameraMessage;
    query('[data-body-hint]').textContent=cameraStatus==='live'?(cameraPose?'实际关键点 · '+(board?.status?.motion?.puppet?'实控通道已就绪':'实机跟随未就绪'):'未检测到人体关键点'):'完整上半身置于画面内';
    query('[data-body-caption]').textContent=cameraStatus==='live'?(board?'板端实拍画面':'本地预览 · 未接入姿态识别'):'等待摄像头画面';
  }
  function renderHomeMenu() {
    query('.shadow-app').dataset.menuOpen=String(state.menuOpen);
    query('.shadow-menu-reveal').inert=!state.menuOpen || turning;
    query('.shadow-menu-reveal').setAttribute('aria-hidden',String(!state.menuOpen));
    query('[data-action="open-menu"]').setAttribute('aria-expanded',String(state.menuOpen));
    query('[data-action="open-menu"]').setAttribute('aria-label',state.menuOpen?'收起三个模式入口':'轻触屏幕，展开三个模式入口');
  }
  function render() {
    query('.shadow-app').dataset.page=state.page;
    renderHomeMenu();
    for(const back of all('.shadow-back'))back.hidden=state.page==='home';
    for(const screen of all('[data-screen]')) screen.hidden=screen.dataset.screen!==state.page;
    bookEffects?.setPage(state.page,!turning);
    const play=query('[data-action="play"]');
    play.setAttribute('aria-pressed',String(state.playing));
    play.querySelector('span').textContent=state.playing?'暂停预览':'屏幕预览';
    const icons=play.querySelector('svg,i');if(icons)icons.remove();
    const icon=document.createElement('i');icon.setAttribute('data-lucide',state.playing?'pause':'play');icon.setAttribute('aria-hidden','true');play.prepend(icon);
    renderTouch();
    renderCamera();
    renderProgress();
    if(globalThis.lucide) globalThis.lucide.createIcons({attrs:{width:18,height:18}});
    scheduleDraw();
  }
  for(const button of all('button[data-page]'))button.addEventListener('click',event=>{event.stopPropagation();setPage(button.dataset.page);});
  function toggleHomeMenu(returnFocus=false) {
    if(turning || state.page!=='home')return;
    state.menuOpen=!state.menuOpen;
    if(globalThis.ShadowBoardDisplay)renderHomeMenu();else render();
    save();
    announce(state.menuOpen?'已展开三个模式入口':'已收起三个模式入口');
    if(returnFocus && !state.menuOpen)query('[data-action="open-menu"]').focus({preventScroll:true});
  }
  query('[data-action="open-menu"]').addEventListener('click',event=>{
    event.stopPropagation();toggleHomeMenu();
  });
  query('[data-screen="home"]').addEventListener('click',event=>{
    if(event.target.closest('button,a,input,select,textarea'))return;
    toggleHomeMenu();
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&!query('.shadow-sample-copy').hidden){event.preventDefault();closeSampleCopy();return;}
    if(event.key==='Escape' && state.page==='home' && state.menuOpen && !turning){event.preventDefault();toggleHomeMenu(true);}
  });
  query('[data-action="play"]').addEventListener('click',()=>{
    if(state.progress>=100)state.progress=0;
    state.playing=!state.playing;lastTime=0;render();save();
    if(state.playing&&!animation)animation=requestAnimationFrame(tick);
    announce(state.playing?'表演示意开始':'表演示意已暂停');
  });
  function tick(now) {
    animation=null;
    if(turning || !state.playing || state.page!=='classic')return;
    if(lastTime) state.progress=Math.min(100,state.progress+Math.min(now-lastTime,100)*.004);
    lastTime=now;
    renderProgress();if(!reduceMotion)scheduleDraw();
    if(state.progress>=100){state.playing=false;render();save();announce('表演示意结束');return;}
    animation=requestAnimationFrame(tick);
  }
  query('[data-action="replay"]').addEventListener('click',()=>{state.progress=0;state.playing=false;render();save();announce('已回到第一幕');});
  query('#shadow-progress').addEventListener('input',e=>{state.progress=+e.target.value;renderProgress();scheduleDraw();});
  query('#shadow-progress').addEventListener('change',save);
  for(const button of all('[data-chapter]'))button.addEventListener('click',()=>{state.progress=+button.dataset.chapter*25;renderProgress();scheduleDraw();save();announce(query('[data-classic-caption]').textContent);});
  async function recognizeSketch() {
    if(training?.active){await submitTraining();return;}
    if(turning||recognitionPending||state.page!=='touch')return;
    stopSequence();
    const actor=state.actors.wusong,name='wusong';
    if(actor.strokes.flat().length<8){actor.result=name==='wusong'?'请先画出头部、身体与双臂':'请先画出虎身、头部与四肢';render();announce(actor.result);return;}
    const model=globalThis.ShadowSketchModel;
    if(typeof model?.predict!=='function'){actor.result='识别模型加载中';render();announce(actor.result);return;}
    const run=++recognitionRun;recognitionPending=true;render();
    try{
      const box=query('#shadow-touch-stick').getBoundingClientRect();
      const paper=drawingPaper(box.width,box.height);
      const result=await globalThis.ShadowSketchRecognition?.recognize(actor.strokes.map(s=>s.map(p=>[...p])),{width:paper.width,height:paper.height});
      if(run!==recognitionRun||state.page!=='touch')return;
      if(!result?.accepted||!actionNames.wusong[result.action]){
        actor.result=result?.reason==='geometry'?'请补全双臂与身体的连接':'没看清，请补全头部、身体与双臂';return;
      }
      actor.pose=standardPose(result.action);actor.poseAspect=1;actor.poseSource='standard';
      actor.action=result.action;actor.result='武松 · '+actionNames.wusong[result.action];actor.draftDirty=false;selectedFrame=-1;save();return true;
    }catch(error){if(run===recognitionRun)actor.result='识别暂未就绪，请稍后再试';}
    finally{if(run===recognitionRun){recognitionPending=false;render();announce(actor.result);}}
  }
  function closeSampleCopy(){query('.shadow-sample-copy').hidden=true;for(const screen of all('main'))screen.inert=false;query('[data-action="recognize-drawing"]').focus({preventScroll:true});}
  function showSampleCopy(){const text=training?.exportPending();if(!text)return;query('#shadow-sample-text').value=text;query('[data-sample-copy-status]').textContent='';query('.shadow-sample-copy').hidden=false;for(const screen of all('main'))screen.inert=true;query('#shadow-sample-text').focus();query('#shadow-sample-text').select();}
  async function submitTraining(){
    if(!training?.active||trainingSending||turning||state.page!=='touch')return;
    if(training.submitted){if(training.next()){trainingStrokes=[];trainingDraftResampled=false;trainingOriginalPointCount=0;trainingInkVersion++;lastInkStamp='';}render();save();return;}
    trainingSending=true;inkPointer=null;render();
    try{const box=query('#shadow-touch-stick').getBoundingClientRect();await training.submit(training.getPending()?undefined:{strokes:trainingStrokes,width:box.width,height:box.height,pointerType:trainingPointerType,resampled:trainingDraftResampled,originalPointCount:Math.max(trainingOriginalPointCount,trainingStrokes.flat().length)});}
    finally{
      trainingSending=false;
      if(batchCollection&&training.submitted&&!batchCollection.complete&&training.next()){trainingStrokes=[];trainingDraftResampled=false;trainingOriginalPointCount=0;trainingInkVersion++;lastInkStamp='';}
      render();save();announce(training.message);
      if(!batchCollection&&training.getPending())showSampleCopy();
    }
  }
  query('[data-action="toggle-training"]').addEventListener('click',()=>{
    if(!training||trainingSending||turning||state.page!=='touch')return;
    recognitionRun++;recognitionPending=false;inkPointer=null;
    if(training.active){training.end();}else{training.begin();state.selectedActor='wusong';}
    trainingInkVersion++;lastInkStamp='';render();save();announce(training.active?'第'+training.task.number+'题：'+training.task.label+'。按自己的习惯绘画，画好后提交样本':'已返回操控画稿');
  });
  query('[data-action="copy-sample"]').addEventListener('click',async()=>{
    const text=query('#shadow-sample-text');text.focus();text.select();
    try{if(!navigator.clipboard?.writeText)throw new Error('unavailable');await navigator.clipboard.writeText(text.value);query('[data-sample-copy-status]').textContent='已复制，请粘贴到对话里';}
    catch{query('[data-sample-copy-status]').textContent='已选中，请复制后粘贴到对话里';}
  });
  query('[data-action="close-sample-copy"]').addEventListener('click',closeSampleCopy);
  query('[data-action="recognize-drawing"]').addEventListener('click',recognizeSketch);
  query('[data-action="save-frame"]').addEventListener('click',async()=>{
    if(turning||training?.active||recognitionPending||sequencePlaying||state.page!=='touch'||savedFrames.length>=100)return;
    const actor=state.actors.wusong;
    if(actor.draftDirty!==false||actor.poseSource!=='standard')if(await recognizeSketch()!==true)return;
    if(!frameJoints.every(key=>Array.isArray(actor.pose[key])&&actor.pose[key].every(Number.isFinite)))return;
    savedFrames.push({action:actor.action,pose:clonePose(actor.pose),aspect:actor.poseAspect,wusong:actor.position,tiger:state.actors.tiger.position});
    selectedFrame=savedFrames.length-1;renderSequence();save();announce('已存入第'+savedFrames.length+'个动作');
    query('.shadow-sequence-frames [data-frame="'+selectedFrame+'"]').scrollIntoView({block:'nearest',inline:'nearest'});
  });
  query('[data-action="play-sequence"]').addEventListener('click',()=>{
    if(turning||training?.active||recognitionPending||state.page!=='touch'||!savedFrames.length)return;
    if(sequencePlaying){stopSequence();sequenceResume=true;renderSequence();save();announce('动作播放已暂停');return;}
    if(!sequenceResume||selectedFrame>=savedFrames.length-1)selectedFrame=-1;
    sequenceResume=false;
    sequencePlaying=true;playSequenceStep();announce('开始依次播放已存动作');
  });
  query('[data-action="delete-frame"]').addEventListener('click',()=>{
    if(turning||sequencePlaying||selectedFrame<0)return;
    savedFrames.splice(selectedFrame,1);selectedFrame=Math.min(selectedFrame,savedFrames.length-1);sequenceKey='';
    if(selectedFrame>=0)applyFrame(selectedFrame);else renderSequence();save();announce('已删除所选动作');
  });
  function selectActor(name) {
    if(turning||training?.active||state.page!=='touch'||!actorNames[name]||state.selectedActor===name)return;
    recognitionRun++;recognitionPending=false;inkPointer=null;
    state.selectedActor=name;render();save();announce('已选中'+actorNames[name]+'，可左右拖动');
  }
  for(const button of all('[data-touch-actor]'))button.addEventListener('click',()=>selectActor(button.dataset.touchActor));
  query('[data-action="clear-drawing"]').addEventListener('click',()=>{
    if(training?.active){if(trainingSending||training.getPending())return;if(training.submitted){showSampleCopy();return;}trainingStrokes=[];trainingDraftResampled=false;trainingOriginalPointCount=0;trainingInkVersion++;inkPointer=null;lastInkStamp='';batchCollection?.saveDraft?.(null);render();save();announce('采集画布已清空');return;}
    const actor=state.actors.wusong;
    stopSequence();recognitionRun++;recognitionPending=false;inkPointer=null;actor.strokes=[];actor.inkAspect=null;actor.draftDirty=true;inkVersions.wusong++;actor.pose=neutral();actor.poseAspect=1;actor.poseSource='model';actor.action='neutral';actor.result=drawingHints.wusong;render();save();announce('武松画布已清空');
  });
  query('[data-action="toggle-camera"]')?.addEventListener('click',async()=>{
    if(turning||state.page!=='body')return;
    if(['live','starting','waiting'].includes(cameraStatus)){cameraPreview?.stop();return;}
    if(!cameraPreview){cameraStatus='error';cameraMessage='当前预览无法访问摄像头';renderCamera();announce(cameraMessage);return;}
    await cameraPreview.start();announce(cameraMessage);
  });
  const stick=query('#shadow-touch-stick');
  function pointerPosition(e){const r=stick.getBoundingClientRect();return globalThis.ShadowSketchPaper.pointFromDisplay(e.clientX-r.left,e.clientY-r.top,drawingPaper(r.width,r.height));}
  stick.addEventListener('pointerdown',e=>{
    const actor=state.actors.wusong;
    const strokes=currentStrokes();
    if(turning||recognitionPending||trainingSending||(training?.active&&(training.getPending()||training.submitted))||state.page!=='touch'||!actor||inkPointer||strokes.length>=128)return;
    if(!training?.active&&!strokes.length){const box=stick.getBoundingClientRect();actor.inkAspect=box.width/box.height;}
    if(!training?.active){stopSequence();actor.draftDirty=true;renderSequence();}
    const stroke=[pointerPosition(e)];strokes.push(stroke);if(training?.active){trainingInkVersion++;trainingPointerType=e.pointerType||'unknown';}else inkVersions.wusong++;inkPointer={id:e.pointerId,stroke};if(e.isTrusted)stick.setPointerCapture(e.pointerId);e.preventDefault();scheduleInkDraw();
  });
  stick.addEventListener('pointermove',e=>{
    if(!inkPointer||inkPointer.id!==e.pointerId)return;
    const point=pointerPosition(e),previous=inkPointer.stroke.at(-1);if(Math.hypot(point[0]-previous[0],point[1]-previous[1])>.002&&inkPointer.stroke.length<512){inkPointer.stroke.push(point);if(training?.active)trainingInkVersion++;else inkVersions.wusong++;}
    if(!training?.active){const actor=state.actors.wusong;actor.result='画好后点击识别动作';query('[data-touch-caption]').textContent=actor.result;}scheduleInkDraw();
  });
  const endInk=()=>{if(!inkPointer)return;inkPointer=null;if(training?.active)trainingInkVersion++;else inkVersions.wusong++;scheduleInkDraw();save();if(batchCollection&&training?.active&&!training.submitted){const box=stick.getBoundingClientRect();batchCollection.saveDraft?.({taskId:training.task.id,task:training.task,strokes:trainingStrokes,width:box.width,height:box.height,pointerType:trainingPointerType,resampled:trainingDraftResampled,originalPointCount:Math.max(trainingOriginalPointCount,trainingStrokes.flat().length)});}};
  stick.addEventListener('pointerup',endInk);stick.addEventListener('pointercancel',endInk);stick.addEventListener('lostpointercapture',endInk);
  globalThis.ShadowDrawingSurface=Object.freeze({capture:()=>{
    const box=stick.getBoundingClientRect(),paper=drawingPaper(box.width,box.height);return{width:paper.width,height:paper.height,strokes:state.actors.wusong.strokes.map(s=>s.map(p=>p.slice()))};
  }});
  root.addEventListener('shadow:agent-action',event=>{
    const action=event.detail?.action;if(state.page!=='touch'||!actionNames.wusong[action])return;
    state.actors.wusong.action=action;state.actors.wusong.pose=standardPose(action);state.actors.wusong.poseAspect=1;state.actors.wusong.poseSource='standard';
    state.actors.wusong.result='程序绘制 · '+actionNames.wusong[action];renderTouch();scheduleDraw();
  });
  const stageCanvas=query('[data-art="touch"]');
  function stagePoint(event) {
    const rect=stageCanvas.getBoundingClientRect();return {x:event.clientX-rect.left,y:event.clientY-rect.top,width:rect.width,height:rect.height};
  }
  stageCanvas.addEventListener('pointerdown',event=>{
    if(turning||state.page!=='touch'||stageDrag||event.button>0)return;
    const point=stagePoint(event),art=globalThis.ShadowStageArt,options=touchArtOptions();
    const name=art?.hitTest?.(point.x,point.y,point.width,point.height,options);if(!actorNames[name])return;
    stopSequence();renderSequence();
    selectActor(name);
    const layout=art.layout(point.width,point.height,touchArtOptions()).actors[name];
    stageDrag={id:event.pointerId,name,startX:point.x,centerX:layout.centerX,moved:false};
    stageCanvas.setPointerCapture(event.pointerId);stageCanvas.dataset.dragging='true';event.preventDefault();
  });
  stageCanvas.addEventListener('pointermove',event=>{
    if(!stageDrag||stageDrag.id!==event.pointerId||turning||state.page!=='touch')return;
    const point=stagePoint(event),centerX=stageDrag.centerX+point.x-stageDrag.startX;
    const position=globalThis.ShadowStageArt?.positionFromX?.(stageDrag.name,centerX,point.width,point.height,touchArtOptions());
    if(!Number.isFinite(position))return;
    state.actors[stageDrag.name].position=Math.max(0,Math.min(1,position));stageDrag.moved=true;
    renderPosition();scheduleDraw();event.preventDefault();
  });
  function endStageDrag(event) {
    if(!stageDrag||event&&stageDrag.id!==event.pointerId)return;
    const ended=stageDrag;stageDrag=null;delete stageCanvas.dataset.dragging;
    if(stageCanvas.hasPointerCapture?.(ended.id))stageCanvas.releasePointerCapture(ended.id);
    if(ended.moved){
      save();announce(actorNames[ended.name]+'屏幕目标 '+Math.round(state.actors[ended.name].position*100)+'%，非实测位置');
      if(event?.type==='pointerup')board?.control({kind:'rail',actor:ended.name,position:state.actors[ended.name].position});
    }
  }
  stageCanvas.addEventListener('pointerup',endStageDrag);stageCanvas.addEventListener('pointercancel',endStageDrag);stageCanvas.addEventListener('lostpointercapture',endStageDrag);
  query('#shadow-actor-position').addEventListener('input',event=>{
    const actor=currentActor();if(!actor||turning||state.page!=='touch')return;
    stopSequence();renderSequence();
    actor.position=Math.max(0,Math.min(1,Number(event.target.value)/100));renderPosition();scheduleDraw();
  });
  query('#shadow-actor-position').addEventListener('change',()=>{if(currentActor()&&!turning&&state.page==='touch'){save();announce(query('#shadow-actor-position').getAttribute('aria-valuetext'));board?.control({kind:'rail',actor:state.selectedActor,position:currentActor().position});}});
  for(const screen of all('[data-screen="classic"] .shadow-stage-screen,[data-screen="touch"] .shadow-stage-screen')){
    const badge=document.createElement('span');badge.className='shadow-screen-only';badge.textContent='屏幕预览 · 非实机反馈';screen.append(badge);
  }
  const realPlay=document.createElement('button');realPlay.type='button';realPlay.className='shadow-secondary cursor-interaction';realPlay.textContent='实机演出';
  let classicRequested=false;
  realPlay.addEventListener('click',async()=>{
    realPlay.disabled=true;
    try{if(await board?.control({kind:'classic',action:classicRequested?'stop':'start'})){classicRequested=!classicRequested;realPlay.textContent=classicRequested?'停止实机':'实机演出';}}
    finally{realPlay.disabled=false;}
  });
  realPlay.disabled=true;realPlay.title='当前只部署界面、识别和音频，机构控制未启用';
  const audioButton=document.createElement('button');audioButton.type='button';audioButton.className='shadow-secondary cursor-interaction';audioButton.textContent='播放原声';
  let audioActive=false,audioRun=0,audioTimer=0;
  function audioControls(active) {
    audioActive=active;audioButton.textContent=active?'停止原声':'播放原声';
    query('[data-action="play"]').disabled=active;
    query('[data-action="replay"]').disabled=active;
    query('#shadow-progress').disabled=active;
    for(const button of all('[data-chapter]'))button.disabled=active;
  }
  function stopAudio() {
    audioRun++;clearTimeout(audioTimer);
    if(audioActive)board?.stopAudio().catch(error=>board.message(error.message,true));
    audioControls(false);
  }
  async function pollAudio(run) {
    try {
      const current=await board.audioStatus();
      if(run!==audioRun||!audioActive)return;
      if(current.running||current.finished){state.progress=Math.min(100,100*current.elapsed_s/current.duration_s);renderProgress();scheduleDraw();}
      if(!current.running){audioControls(false);announce(current.finished?'原声播放完成':current.error||'原声已停止');return;}
    } catch(error) {if(run===audioRun){stopAudio();board?.message('原声连接中断，已请求停止',true);}return;}
    audioTimer=setTimeout(()=>pollAudio(run),300);
  }
  audioButton.addEventListener('click',async()=>{
    if(audioActive){stopAudio();return;}
    if(state.page!=='classic'||turning)return;
    const run=++audioRun;audioControls(true);state.playing=false;render();
    try {
      await board.startAudio();
      if(run!==audioRun||state.page!=='classic')return;
      pollAudio(run);announce('播放原声，机构控制保持关闭');
    } catch(error){if(run===audioRun){stopAudio();board?.message(error.message,true);}}
  });
  // Separate explicit audio playback from the optional silent screen preview.
  query('.shadow-play-controls').append(audioButton);
  const pageObserver=new MutationObserver(()=>{if(state.page!=='classic')stopAudio();});
  pageObserver.observe(query('.shadow-app'),{attributes:true,attributeFilter:['data-page']});
  const artworkObserver=new ResizeObserver(scheduleDraw);
  artworkObserver.observe(root);
  for(const el of all('.shadow-hero-scene,.shadow-stage-screen,.shadow-stick-wrap'))artworkObserver.observe(el);
  window.addEventListener('openai:set_globals',e=>{if(e.detail?.globals?.widgetState)load(e.detail.globals.widgetState);});
  window.addEventListener('shadow:art-ready',()=>{artworkEpoch++;scheduleDraw();});
  document.fonts?.load('18px "ShadowInk"').then(scheduleDraw).catch(()=>{});
  document.addEventListener('visibilitychange',()=>{if(document.hidden && finishTurn)finishTurn();if(document.hidden){cameraPreview?.stop();stopAudio();stopSequence();renderSequence();}});
  window.addEventListener('pagehide',()=>{cameraPreview?.destroy();stopAudio();stopSequence();pageObserver.disconnect();});
  motionPreference.addEventListener('change',e=>{reduceMotion=e.matches;if(reduceMotion && finishTurn)finishTurn();});
  render();load(storage?.widgetState);board?.check();
  if(globalThis.Tweak) {
    const tweak=new Tweak({container:query('.shadow-app'),onChange:()=>{root.style.setProperty('--sh-gold',design.gold);root.style.setProperty('--sh-red',design.red);scheduleDraw();}});
    tweak.addColorPicker(design,'gold',{label:'金色饰边',reference:'--sh-gold'});
    tweak.addColorPicker(design,'red',{label:'戏台朱红',reference:'--sh-red'});
  }
})();
