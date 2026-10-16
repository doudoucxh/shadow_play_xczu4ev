/* Offline action drawing guide. Reads the frozen catalog; never submits ink. */
(() => {
  'use strict';
  const root=document.getElementById('shadow-theatre-preview'),app=root?.querySelector('.shadow-app');
  const oldEntry=root?.querySelector('[data-batch-entry]');
  if(!app||!oldEntry||root.querySelector('[data-action-reference-entry]'))return;
  const entry=document.createElement('button');
  entry.type='button';entry.className=oldEntry.className;entry.hidden=oldEntry.hidden;
  entry.dataset.batchEntry='';entry.dataset.actionReferenceEntry='';entry.textContent='画法';
  entry.setAttribute('aria-label','查看20种动作的标准画法');entry.setAttribute('aria-haspopup','dialog');
  entry.setAttribute('aria-controls','shadow-action-reference');entry.setAttribute('aria-expanded','false');
  oldEntry.replaceWith(entry);
  const style=document.createElement('style');
  style.textContent=`
#shadow-theatre-preview .shadow-action-reference{position:absolute;inset:12px 12px auto;z-index:30;display:grid;grid-template-rows:38px 23px minmax(0,1fr) 38px;gap:7px;box-sizing:border-box;min-height:0;padding:12px;color:#433b2a;background:radial-gradient(ellipse at 10% 0,#efebd5b3,transparent 65%),repeating-linear-gradient(3deg,#998d6d08 0,#e4e2cb14 2px,#b0a78708 4px),linear-gradient(105deg,#d4ceb1,#e3e1ca 55%,#d5d0b6);border:1px solid #8f825f;box-shadow:inset 0 0 0 3px #c4b994,inset 0 0 0 4px #ece5c9,0 0 0 16px #20191275,0 8px 30px #17110da3;container-type:inline-size}
#shadow-theatre-preview .shadow-action-reference[hidden]{display:none!important}
#shadow-theatre-preview .shadow-action-reference-header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:0}
#shadow-theatre-preview .shadow-action-reference-header h2{font-size:25px;line-height:1.2;font-weight:400;margin:0;color:#443c2a;letter-spacing:2px}
#shadow-theatre-preview .shadow-action-reference-header button{flex:none;min-height:34px;padding:4px 14px;font-size:19px;line-height:24px}
#shadow-theatre-preview .shadow-action-reference-convention{font-size:15px;line-height:23px;color:#645b44;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#shadow-theatre-preview .shadow-action-reference-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));grid-template-rows:repeat(4,minmax(0,1fr));gap:6px;min-height:0;min-width:0;overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#968664 #d9d2b7;padding:2px}
#shadow-theatre-preview .shadow-action-reference-card{display:grid;grid-template-rows:minmax(0,1fr) 22px;align-items:stretch;min-height:0;min-width:0;margin:0;padding:3px 6px 4px;color:#4a402d;border:1px solid #b5aa8a;border-radius:2px;background:#e8e6d073;box-shadow:inset 0 1px 0 #f3efdc80;touch-action:manipulation}
#shadow-theatre-preview .shadow-action-reference-card[aria-pressed=true]{border-color:#61704f;background:#c7cdb199;box-shadow:inset 0 0 0 1px #7c8b67}
#shadow-theatre-preview .shadow-action-reference-card:focus-visible{outline:2px solid #4c604b;outline-offset:-1px}
#shadow-theatre-preview .shadow-action-reference-card canvas{display:block;width:100%;height:100%;min-height:0;min-width:0;pointer-events:none}
#shadow-theatre-preview .shadow-action-reference-card span{display:block;font-size:17px;line-height:22px;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#shadow-theatre-preview .shadow-action-reference-card small{font-size:13px;color:#877b61;margin-right:4px}
#shadow-theatre-preview .shadow-action-reference-detail{margin:0;display:flex;align-items:center;min-width:0;padding:3px 8px;border-top:1px solid #b6a786;color:#554a33;font-size:15px;line-height:19px;overflow:auto;overscroll-behavior:contain}
@container(max-width:760px){#shadow-theatre-preview .shadow-action-reference-grid{grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:none;grid-auto-rows:112px}#shadow-theatre-preview .shadow-action-reference-card span{font-size:16px}}
@container(max-width:460px){#shadow-theatre-preview .shadow-action-reference-grid{grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:132px}#shadow-theatre-preview .shadow-action-reference-header h2{font-size:22px}#shadow-theatre-preview .shadow-action-reference-convention{font-size:13px}#shadow-theatre-preview .shadow-action-reference-detail{font-size:14px}}
`;
  app.append(style);
  const modal=document.createElement('section');
  modal.id='shadow-action-reference';modal.className='shadow-action-reference';modal.dataset.actionReferenceModal='';modal.hidden=true;
  modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','shadow-action-reference-title');modal.setAttribute('aria-describedby','shadow-action-reference-convention');
  const heading=document.createElement('div');heading.className='shadow-action-reference-header';
  const title=document.createElement('h2');title.id='shadow-action-reference-title';title.textContent='动作画法';
  const closeButton=document.createElement('button');closeButton.type='button';closeButton.className='shadow-secondary cursor-interaction';closeButton.dataset.actionReferenceClose='';closeButton.textContent='返回画板';closeButton.setAttribute('aria-label','关闭动作画法，返回画板');
  heading.append(title,closeButton);
  const convention=document.createElement('p');convention.className='shadow-action-reference-convention';convention.id='shadow-action-reference-convention';convention.textContent='左右以屏幕为准 · 双臂画清，腿部相同即可';
  const grid=document.createElement('div');grid.className='shadow-action-reference-grid';grid.dataset.actionReferenceGrid='';grid.setAttribute('role','group');grid.setAttribute('aria-label','20种动作标准画法，方向键切换查看');
  const detail=document.createElement('p');detail.className='shadow-action-reference-detail';detail.dataset.actionReferenceDetail='';detail.setAttribute('aria-live','polite');
  modal.append(heading,convention,grid,detail);app.append(modal);
  let opened=false,returnFocus=null,locked=[],selected='open',definitions=[],cards=[];
  const validPoint=p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite);
  function readCatalog(){
    const actions=globalThis.ShadowActionCatalog?.actions;
    return Array.isArray(actions)?actions.filter(a=>a&&typeof a.id==='string'&&typeof a.name==='string'&&a.pose&&['head','leftShoulder','rightShoulder','leftElbow','rightElbow','leftWrist','rightWrist'].every(key=>validPoint(a.pose[key]))):[];
  }
  function paths(action){
    if(action.stroke_paths)return action.stroke_paths;
    const p=action.pose,neck=p.neck||[.5,.255],hip=p.hip||[.5,.66],radius=p.headRadius||[.055,.065];
    const circle=Array.from({length:33},(_,i)=>[p.head[0]+Math.cos(i/32*Math.PI*2)*radius[0],p.head[1]+Math.sin(i/32*Math.PI*2)*radius[1]]);
    return {head:circle,torso:[neck,[.5,.32],hip],shoulders:[p.leftShoulder,p.rightShoulder],left_arm:[p.leftShoulder,p.leftElbow,p.leftWrist],right_arm:[p.rightShoulder,p.rightElbow,p.rightWrist],left_leg:[hip,p.leftKnee||[.39,.79],p.leftFoot||[.29,.93]],right_leg:[hip,p.rightKnee||[.61,.79],p.rightFoot||[.71,.93]]};
  }
  function drawAll(){
    if(!opened)return;
    const measures=cards.map(card=>({card,rect:card.canvas.getBoundingClientRect()}));
    for(const {card,rect}of measures){
      const width=rect.width,height=rect.height;if(width<1||height<1)continue;
      const ratio=Math.min(globalThis.devicePixelRatio||1,2),canvas=card.canvas;
      canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);
      const context=canvas.getContext('2d');context.setTransform(ratio,0,0,ratio,0,0);context.clearRect(0,0,width,height);
      const size=Math.min(width-10,height-2),x=(width-size)/2,y=(height-size)/2;
      const points=paths(card.action);context.lineCap='round';context.lineJoin='round';
      for(const name of ['head','torso','shoulders','left_leg','right_leg','left_arm','right_arm']){
        const stroke=points[name];if(!Array.isArray(stroke)||!stroke.length)continue;
        const arm=name.endsWith('_arm');context.strokeStyle=arm?'#332d21':'#9a8e73';context.lineWidth=arm?2.1:1.25;
        context.beginPath();stroke.forEach((p,i)=>{if(!validPoint(p))return;context[i?'lineTo':'moveTo'](x+p[0]*size,y+p[1]*size);});context.stroke();
      }
    }
  }
  function choose(actionId,focus=false){
    selected=actionId;const action=definitions.find(a=>a.id===selected);
    for(const card of cards){const active=card.action.id===selected;card.button.setAttribute('aria-pressed',String(active));if(active&&focus){card.button.focus({preventScroll:true});card.button.scrollIntoView({block:'nearest',inline:'nearest'});}}
    detail.textContent=action?`${action.name}：${action.distinguishing_instruction||action.instruction||'按图画清双臂的方向和折弯。'}`:'';
  }
  function position(){
    const box=app.getBoundingClientRect(),height=Math.max(180,Math.min(576,box.height-24,(globalThis.innerHeight||600)-24));
    const top=Math.max(12,Math.min(box.height-height-12,Math.max(12,12-box.top)));
    modal.style.top=top+'px';modal.style.height=height+'px';
  }
  function open(){
    if(opened||app.dataset.turning==='true'||app.dataset.page!=='touch')return;
    definitions=readCatalog();if(definitions.length!==20||new Set(definitions.map(a=>a.id)).size!==20)return;
    if(!cards.length){
      cards=definitions.map((action,index)=>{
        const button=document.createElement('button');button.type='button';button.className='shadow-action-reference-card cursor-interaction';button.dataset.referenceAction=action.id;
        button.setAttribute('aria-label',action.name+'。'+(action.instruction||'查看标准画法'));
        const canvas=document.createElement('canvas');canvas.setAttribute('aria-hidden','true');
        const label=document.createElement('span'),number=document.createElement('small');number.textContent=String(index+1).padStart(2,'0');label.append(number,document.createTextNode(action.name));button.append(canvas,label);
        button.addEventListener('click',()=>choose(action.id));grid.append(button);return {button,canvas,action};
      });
    }
    returnFocus=document.activeElement;locked=Array.from(app.children).filter(el=>el!==modal&&el!==style).map(el=>({el,inert:el.inert,hidden:el.getAttribute('aria-hidden')}));
    for(const item of locked){item.el.inert=true;item.el.setAttribute('aria-hidden','true');}
    opened=true;modal.hidden=false;entry.setAttribute('aria-expanded','true');position();choose(selected);drawAll();closeButton.focus({preventScroll:true});
  }
  function close(restore=true){
    if(!opened)return;opened=false;modal.hidden=true;entry.setAttribute('aria-expanded','false');
    for(const item of locked){if(item.el.isConnected){if(app.dataset.turning!=='true')item.el.inert=item.inert;if(item.hidden===null)item.el.removeAttribute('aria-hidden');else item.el.setAttribute('aria-hidden',item.hidden);}}
    locked=[];
    if(restore){const target=returnFocus?.isConnected&&!returnFocus.closest('[hidden],[inert]')?returnFocus:entry;if(!target.closest('[hidden],[inert]'))target.focus({preventScroll:true});}
    returnFocus=null;
  }
  entry.addEventListener('click',open);closeButton.addEventListener('click',()=>close());
  document.addEventListener('keydown',event=>{
    if(!opened)return;
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();return;}
    const focused=cards.findIndex(card=>card.button===document.activeElement);
    if(focused>=0&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)){
      const columns=getComputedStyle(grid).gridTemplateColumns.split(' ').length;
      const shift={ArrowLeft:-1,ArrowRight:1,ArrowUp:-columns,ArrowDown:columns};
      const next=event.key==='Home'?0:event.key==='End'?cards.length-1:Math.max(0,Math.min(cards.length-1,focused+shift[event.key]));event.preventDefault();choose(cards[next].action.id,true);return;
    }
    if(event.key==='Tab'){
      const first=closeButton,last=cards.at(-1)?.button||closeButton;
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus({preventScroll:true});}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus({preventScroll:true});}
    }
  },true);
  document.addEventListener('focusin',event=>{if(opened&&!modal.contains(event.target))closeButton.focus({preventScroll:true});},true);
  const resize=new ResizeObserver(()=>{if(opened){position();drawAll();}});resize.observe(app);resize.observe(grid);
  new MutationObserver(()=>{if(opened&&(app.dataset.page!=='touch'||app.dataset.turning==='true'))close(false);}).observe(app,{attributes:true,attributeFilter:['data-page','data-turning']});
  globalThis.ShadowActionReference=Object.freeze({open,close,get isOpen(){return opened;}});
})();
