/* Vector geometry only: action recognition remains in ShadowSketchModel. */
(() => {
  'use strict';
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  const mix=(a,b,t)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t];
  const length=p=>p.slice(1).reduce((n,b,i)=>n+dist(p[i],b),0);
  const bounds=p=>({x0:Math.min(...p.map(q=>q[0])),x1:Math.max(...p.map(q=>q[0])),y0:Math.min(...p.map(q=>q[1])),y1:Math.max(...p.map(q=>q[1]))});
  function project(p,a,b) {
    const dx=b[0]-a[0],dy=b[1]-a[1],n=dx*dx+dy*dy;
    const t=n>1e-12?clamp(((p[0]-a[0])*dx+(p[1]-a[1])*dy)/n,0,1):0;
    const point=mix(a,b,t);return {t,point,d:dist(p,point)};
  }
  function simplify(p,tolerance) {
    if(p.length<3)return p.slice();
    let best=-1,d=tolerance;
    for(let i=1;i<p.length-1;i++){const v=project(p[i],p[0],p.at(-1)).d;if(v>d){d=v;best=i;}}
    if(best<0)return [p[0],p.at(-1)];
    return [...simplify(p.slice(0,best+1),tolerance).slice(0,-1),...simplify(p.slice(best),tolerance)];
  }
  function crossing(a,b,c,d) {
    const ux=b[0]-a[0],uy=b[1]-a[1],vx=d[0]-c[0],vy=d[1]-c[1],den=ux*vy-uy*vx;
    if(Math.abs(den)<1e-9)return null;
    const t=((c[0]-a[0])*vy-(c[1]-a[1])*vx)/den,s=((c[0]-a[0])*uy-(c[1]-a[1])*ux)/den;
    return t>=-1e-6&&t<=1.000001&&s>=-1e-6&&s<=1.000001?{t:clamp(t,0,1),point:mix(a,b,t)}:null;
  }
  function headCandidate(strokes,H) {
    const candidates=[];
    const figureTop=Math.min(...strokes.flat().map(p=>p[1]));
    for(let si=0;si<strokes.length;si++) {
      const p=strokes[si];if(p.length<5)continue;
      // Whole circles and loop portions of a continuous head/body stroke.
      const intervals=[[0,p.length-1]];
      if(p.length<=80)for(let a=0;a<p.length-4;a++)for(let b=a+4;b<p.length;b++) {
        if(a===0&&b===p.length-1)continue;
        if(dist(p[a],p[b])<H*.065)intervals.push([a,b]);
      }
      for(const [a,b] of intervals) {
        const q=p.slice(a,b+1),box=bounds(q),w=box.x1-box.x0,h=box.y1-box.y0,span=Math.max(w,h);
        // An oval head remains a head on a legacy draft stretched by its paper.
        // Closure, enclosed area, upper placement and a downward torso still
        // supply the structural checks; do not rely on a near-circular aspect.
        if(h<H*.045||h>H*.46||w<H*.025||w>H*.45||w/h<.14||w/h>3)continue;
        const closed=dist(q[0],q.at(-1))/span,l=length(q)/span;
        const openTop=(q[0][1]+q.at(-1)[1])/2<box.y0+h*.4||Math.max(q[0][0],q.at(-1)[0])<box.x0+w*.4||Math.min(q[0][0],q.at(-1)[0])>box.x1-w*.4;
        if(closed>(openTop?.9:.39)||l<(openTop&&closed>.39?1.85:2.08)||l>4.8)continue;
        let area=0;for(let i=0;i<q.length;i++){const x=q[i],y=q[(i+1)%q.length];area+=x[0]*y[1]-y[0]*x[1];}
        const fill=Math.abs(area)/2/(w*h);if(fill<.34||fill>.94)continue;
        const center=[(box.x0+box.x1)/2,(box.y0+box.y1)/2];
        // A folded arm at the waist may enclose a loop too. It cannot be
        // the head of a complete figure below the upper body region.
        if(center[1]>figureTop+H*.42)continue;
        // A head sits above a central downward torso, even if hands are higher.
        let below=0;
        for(let sj=0;sj<strokes.length;sj++)for(let k=1;k<strokes[sj].length;k++) {
          if(sj===si&&k>a&&k<=b)continue;
          const u=strokes[sj][k-1],v=strokes[sj][k],dy=Math.abs(v[1]-u[1]),dx=Math.abs(v[0]-u[0]);
          if(dy>dx*1.8&&Math.min(u[1],v[1])>=box.y1-H*.035&&Math.min(u[1],v[1])<box.y1+H*.22&&Math.abs((u[0]+v[0])/2-center[0])<w*.6+H*.035)below+=dy;
        }
        if(below<H*.10)continue;
        const score=2*clamp(below/H,0,.6)+fill*.4+(1-closed)*.3+span/H*.4;
        candidates.push({si,a,b,center,box,score});
      }
    }
    candidates.sort((a,b)=>b.score-a.score);
    const best=candidates[0];if(!best)return null;
    const span=h=>Math.max(h.box.x1-h.box.x0,h.box.y1-h.box.y0);
    best.multiple=candidates.some(h=>h.si!==best.si&&h.score>=best.score*.78&&dist(h.center,best.center)>Math.max(span(h),span(best))*1.35);
    return best;
  }
  function solve(input,options={},gapScale=1) {
    const reject=(stage,details)=>{if(typeof options.onDiagnostic==='function')options.onDiagnostic(stage,details);return null;};
    const dimension=v=>Number.isFinite(Number(v))&&Number(v)>0?Number(v):1;
    const width=dimension(options.width),height=dimension(options.height);
    if(!Array.isArray(input))return reject('input');
    let strokes=input.slice(0,128).map(s=>Array.isArray(s)?s.slice(0,512).map(p=>[Number(p?.[0]),Number(p?.[1])]).filter(p=>p.every(Number.isFinite)).map(p=>[clamp(p[0],0,1)*width,clamp(p[1],0,1)*height]):[]).filter(s=>s.length>1);
    if(strokes.reduce((n,s)=>n+s.length,0)<8)return reject('too-few-points');
    const bb=bounds(strokes.flat()),H=Math.max(bb.y1-bb.y0,bb.x1-bb.x0);
    if(H<1e-5)return reject('empty-extent');
    const eps=H*.0105*gapScale,tol=H*.0035;
    strokes=strokes.map(s=>simplify(s,tol));
    // This helper fits a simple figure, not an arbitrary illustration. Bound
    // work on noisy/repeated ink instead of blocking the HDMI interaction.
    if(strokes.some(s=>s.length>160)||strokes.reduce((n,s)=>n+s.length,0)>768)return reject('complex-ink');
    const head=headCandidate(strokes,H);if(!head||head.multiple)return reject(head?'multiple-people':'head');
    const paths=[];
    for(let i=0;i<strokes.length;i++) {
      if(i!==head.si)paths.push({p:strokes[i],id:i});
      else {
        if(head.a>0)paths.push({p:strokes[i].slice(0,head.a+1),id:i});
        if(head.b<strokes[i].length-1)paths.push({p:strokes[i].slice(head.b),id:i});
      }
    }
    for(let i=paths.length-1;i>=0;i--)if(paths[i].id===head.si) {
      const b=bounds(paths[i].p),m=H*.035;
      if(b.x0>=head.box.x0-m&&b.x1<=head.box.x1+m&&b.y0>=head.box.y0-m&&b.y1<=head.box.y1+m)paths.splice(i,1);
    }
    // Join a straight central torso drawn in several passes. Legs and arm
    // diagonals are deliberately outside this narrow direction/column band.
    for(let pass=0;pass<12;pass++) {
      let joined=false;
      for(let i=0;i<paths.length&&!joined;i++)for(let j=i+1;j<paths.length;j++) {
        const a=paths[i],b=paths[j],ba=bounds(a.p),bb=bounds(b.p);
        const valid=box=>box.y0>=head.box.y1-H*.035&&(box.x1-box.x0)<(box.y1-box.y0)*.25&&Math.abs((box.x0+box.x1)/2-head.center[0])<H*.055;
        if(!valid(ba)||!valid(bb))continue;
        if(Math.min(ba.y1,bb.y1)-Math.max(ba.y0,bb.y0)>eps*.5&&Math.abs(ba.x0+ba.x1-bb.x0-bb.x1)<eps*4) {
          paths[i]={p:[...a.p,...b.p].sort((p,q)=>p[1]-q[1]),id:a.id};paths.splice(j,1);joined=true;break;
        }
        joinTorso: for(const ra of [false,true])for(const rb of [false,true]) {
          const aa=ra?a.p.slice().reverse():a.p,bbb=rb?b.p.slice().reverse():b.p;
          if(dist(aa.at(-1),bbb[0])>eps||(aa.at(-1)[1]-aa[0][1])*(bbb.at(-1)[1]-bbb[0][1])<=0)continue;
          paths[i]={p:[...aa,...bbb.slice(1)],id:a.id};paths.splice(j,1);joined=true;break joinTorso;
        }
        if(joined)break;
      }
      if(!joined)break;
    }
    // Find a continuous central, nearly vertical torso run; do not infer it
    // from the action label, wrist extremes, or a canonical pose template.
    const torsos=[];
    for(let pi=0;pi<paths.length;pi++) {
      const p=paths[pi].p;
      for(let a=0;a<p.length-1;a++)for(let b=a+1;b<p.length;b++) {
        const q=p.slice(a,b+1),box=bounds(q),dy=box.y1-box.y0,dx=box.x1-box.x0;
        if(dy<H*.15||dx>dy*.38||box.y0<head.box.y1-H*.055||box.y0>head.box.y1+H*.20)continue;
        if(Math.abs((box.x0+box.x1)/2-head.center[0])>H*.11)continue;
        const deviation=q.reduce((n,v)=>n+Math.abs(v[0]-head.center[0]),0)/q.length;
        const gap=Math.max(0,box.y0-head.box.y1);
        const score=dy/H-deviation/H*2-gap/H*.5-dx/dy*.15;
        torsos.push({pi,a,b,p:q,box,score});
      }
    }
    const torso=torsos.sort((a,b)=>b.score-a.score)[0];if(!torso)return reject('torso');
    const t0=torso.p.reduce((a,b)=>a[1]<b[1]?a:b),t1=torso.p.reduce((a,b)=>a[1]>b[1]?a:b);
    let neck=t0.slice(),hip=t1.slice();
    let bodyPath=torso.p.slice().sort((a,b)=>a[1]-b[1]).filter((p,i,a)=>i===0||dist(p,a[i-1])>tol*.1);
    const bodyAtY=y=> {
      if(y<=bodyPath[0][1])return bodyPath[0].slice();
      for(let i=1;i<bodyPath.length;i++)if(y<=bodyPath[i][1])return mix(bodyPath[i-1],bodyPath[i],clamp((y-bodyPath[i-1][1])/Math.max(1e-8,bodyPath[i][1]-bodyPath[i-1][1]),0,1));
      return bodyPath.at(-1).slice();
    };
    const bodyProject=p=> {
      let best={d:Infinity,point:neck};
      for(let i=1;i<bodyPath.length;i++){const q=project(p,bodyPath[i-1],bodyPath[i]);if(q.d<best.d)best=q;}
      return best;
    };
    const bodyCrossings=(a,b)=> {
      const out=[];for(let i=1;i<bodyPath.length;i++){const c=crossing(a,b,bodyPath[i-1],bodyPath[i]);if(c&&!out.some(p=>dist(p.point,c.point)<tol*.1))out.push(c);}
      return out;
    };
    const other=[];
    for(let i=0;i<paths.length;i++) {
      if(i!==torso.pi)other.push(paths[i]);
      else {
        if(torso.a>0)other.push({p:paths[i].p.slice(0,torso.a+1),id:paths[i].id});
        if(torso.b<paths[i].p.length-1)other.push({p:paths[i].p.slice(torso.b),id:paths[i].id});
      }
    }
    // A recognized joined-hands gesture may be drawn as one V or two lines.
    // Resolve that topology from the measured ink, without substituting a pose.
    if(options.action==='salute'||options.detectJoinedHands===true) {
      const routes=[],near=p=>bodyProject(p).d<H*.085&&p[1]>head.box.y1+H*.012&&p[1]<hip[1]-H*.02;
      for(const {p} of other) {
        const a=p[0],b=p.at(-1);
        if(near(a)&&near(b)) {
          let k=0,d=0;for(let j=1;j<p.length-1;j++){const v=bodyProject(p[j]).d;if(v>d){d=v;k=j;}}
          if(k&&d>H*.07)routes.push(p.slice(0,k+1),p.slice(k).reverse());
        } else if(near(a)||near(b)) {
          const q=near(a)?p:p.slice().reverse();
          if(bodyProject(q.at(-1)).d>H*.07&&q.at(-1)[1]<hip[1]+H*.08)routes.push(q);
        }
      }
      let best=null;
      for(let i=0;i<routes.length;i++)for(let j=i+1;j<routes.length;j++) {
        const a=routes[i],b=routes[j],meeting=dist(a.at(-1),b.at(-1));
        if(meeting>H*.09||dist(a[0],b[0])<H*.025)continue;
        const score=(length(a)+length(b)-meeting*2)/H;
        if(!best||score>best.score)best={a,b,score};
      }
      if(best) {
        const normal=p=>[clamp(p[0]/width,0,1),clamp(p[1]/height,0,1)];
        const elbow=p=>{
          let point=mix(p[0],p.at(-1),.5),d=0;
          for(const v of p.slice(1,-1)){const n=project(v,p[0],p.at(-1)).d;if(n>d){d=n;point=v;}}
          return normal(point);
        };
        const [a,b]=best.a[0][1]<=best.b[0][1]?[best.a,best.b]:[best.b,best.a];
        return {pose:{head:normal(head.center),leftShoulder:normal(a[0]),rightShoulder:normal(b[0]),leftElbow:elbow(a),rightElbow:elbow(b),leftWrist:normal(a.at(-1)),rightWrist:normal(b.at(-1))},aspect:width/height,quality:.75,source:'strokes',diagnostics:{joinedHands:true,headBounds:head.box}};
      }
    }
    // A long neck may end at the shoulder fork, followed by a separately
    // drawn, very short connector to the lower leg fork. Keep that measured
    // connector instead of requiring a textbook shoulder/hip separation.
    for(let pass=0;pass<4;pass++) {
      let join=null;
      for(let i=0;i<other.length;i++)for(const reverse of [false,true]) {
        const p=reverse?other[i].p.slice().reverse():other[i].p;
        const a=p[0],b=p.at(-1),dx=Math.abs(b[0]-a[0]),dy=b[1]-a[1],gap=dist(a,hip);
        if(gap>eps*2.3||dy<eps*.4||dy<dx*.75||length(p)>H*.145||Math.abs(b[0]-head.center[0])>H*.11)continue;
        const score=gap+dx*.3;if(!join||score<join.score)join={i,p,score};
      }
      if(!join)break;
      bodyPath.push(...join.p.filter(p=>p[1]>hip[1]+tol*.1));bodyPath.sort((a,b)=>a[1]-b[1]);
      hip=bodyPath.at(-1).slice();other.splice(join.i,1);
    }
    // The second leg meeting a continuous torso/first-leg line marks the hip.
    const legStarts=[];
    for(const path of other)for(const end of [0,path.p.length-1]) {
      const p=path.p[end],q=path.p[end===0?path.p.length-1:0];
      if(bodyProject(p).d<eps*1.6&&p[1]>bb.y0+H*.48&&p[1]>neck[1]+(hip[1]-neck[1])*.45&&q[1]>p[1]+H*.16&&Math.abs(q[0]-p[0])>H*.055)legStarts.push({p,q,id:path.id});
    }
    const legForks=legStarts.filter(a=>legStarts.some(b=>a.id!==b.id&&dist(a.p,b.p)<eps*2&&(a.q[0]-a.p[0])*(b.q[0]-b.p[0])<0)||hip[1]-a.p[1]>H*.16&&Math.abs(hip[0]-a.p[0])>H*.035);
    if(legForks.length) {
      const lower=legForks.map(v=>v.p).sort((a,b)=>a[1]-b[1])[0];
      if(lower[1]<hip[1]-eps*2){hip=bodyProject(lower).point;bodyPath=[...bodyPath.filter(p=>p[1]<hip[1]),hip];}
    }
    if(hip[1]-neck[1]<H*.13)return reject('short-torso');
    // A connected pen stroke can contain both arms and their shoulder bar.
    // Preserve the two turns at the bar ends before finding arm paths.
    for(let i=0;i<other.length;i++) {
      const path=other[i],p=path.p;let run=null;
      for(let a=1;a<p.length-2;a++)for(let b=a+1;b<p.length-1;b++) {
        const q=p.slice(a,b+1),box=bounds(q),y=(box.y0+box.y1)/2;
        if(box.y1-box.y0>H*.012||box.x0>bodyAtY(y)[0]-H*.035||box.x1<bodyAtY(y)[0]+H*.035||y<=head.box.y1+H*.008||y>=hip[1]-H*.075)continue;
        if(!run||length(q)>run.l)run={a,b,p:q,l:length(q)};
      }
      if(run){other.splice(i,1,{p:p.slice(0,run.a+1),id:path.id},{p:run.p,id:path.id},{p:p.slice(run.b),id:path.id});i+=2;}
    }
    // Reconnect a shoulder bar split over several strokes. The narrow angle
    // requirement avoids joining two nearby, differently directed same-side arms.
    for(let pass=0;pass<12;pass++) {
      let joined=false;
      for(let i=0;i<other.length&&!joined;i++)for(let j=i+1;j<other.length;j++) {
        const a=other[i],b=other[j],ba=bounds(a.p),bb=bounds(b.p);
        if(ba.y1-ba.y0>H*.012||bb.y1-bb.y0>H*.012||Math.abs((ba.y0+ba.y1-bb.y0-bb.y1)/2)>eps)continue;
        joinBar: for(const ra of [false,true])for(const rb of [false,true]) {
          const aa=ra?a.p.slice().reverse():a.p,bbb=rb?b.p.slice().reverse():b.p;
          if(dist(aa.at(-1),bbb[0])>eps||((aa.at(-1)[0]-aa[0][0])*(bbb.at(-1)[0]-bbb[0][0])<=0))continue;
          other[i]={p:[...aa,...bbb.slice(1)],id:a.id};other.splice(j,1);joined=true;break joinBar;
        }
        if(joined)break;
      }
      if(!joined)break;
    }
    const contacts=[];
    for(const path of other) {
      if(Math.max(...path.p.map(p=>p[1]))<=head.box.y1+H*.025||length(path.p)<H*.045||path.p.every(p=>bodyProject(p).d<H*.035))continue;
      for(const p of [path.p[0],path.p.at(-1)])if(bodyProject(p).d<=eps*1.7)contacts.push(bodyProject(p).point);
      for(let k=1;k<path.p.length;k++)for(const c of bodyCrossings(path.p[k-1],path.p[k]))contacts.push(c.point);
    }
    const twoUpperBranches=p=> {
      let count=0;
      for(const path of other) {
        const touches=path.p.some(v=>dist(v,p)<eps*2)||path.p.slice(1).some((v,i)=>project(p,path.p[i],v).d<eps*2);
        if(touches)for(const end of [path.p[0],path.p.at(-1)])if(end[1]<p[1]-H*.08)count++;
      }
      return count>=2;
    };
    const shoulderContacts=contacts.filter(p=>p[1]>head.box.y1+H*.008&&(p[1]<hip[1]-eps*.65||twoUpperBranches(p)));
    if(!shoulderContacts.length)return reject('shoulder-attachments',{neck,hip,contacts});
    let sy=Math.min(...shoulderContacts.map(p=>p[1])),center=bodyAtY(sy);
    // A separately drawn shoulder bar has continuations at BOTH endpoints.
    // A single line across the torso without these continuations is two arms.
    let bar=null;
    for(let i=0;i<other.length;i++) {
      if(options.action==='akimbo')break;
      const p=other[i].p,box=bounds(p),a=p[0],b=p.at(-1);
      const y=(a[1]+b[1])/2;
      if(box.y1-box.y0>H*.035||y<=head.box.y1+H*.008||y>=hip[1]-H*.075||box.x0>bodyAtY(y)[0]-eps*2||box.x1<bodyAtY(y)[0]+eps*2)continue;
      // A lower forearm may cross the torso almost horizontally, especially
      // after a responsive paper resize. A shoulder bar cannot sit below an
      // independent arm attachment whose route does not join either bar end.
      const upperBranch=other.some((path,j)=>{
        if(j===i||length(path.p)<H*.10)return false;
        const ends=[path.p[0],path.p.at(-1)];
        if(ends.some(v=>Math.min(dist(v,a),dist(v,b))<eps*1.7))return false;
        return ends.some((v,k)=>v[1]<y-H*.04&&v[1]>head.box.y1+H*.008&&bodyProject(v).d<H*.065&&bodyProject(ends[1-k]).d>H*.10);
      });
      if(upperBranch)continue;
      const joins=end=>other.some((q,j)=>j!==i&&length(q.p)>H*.045&&[q.p[0],q.p.at(-1)].some(v=>dist(v,end)<eps*1.5));
      if(joins(a)&&joins(b)&&(!bar||length(p)>length(bar.p)))bar={...other[i],index:i};
    }
    if(bar){sy=(bar.p[0][1]+bar.p.at(-1)[1])/2;center=bodyAtY(sy);}
    const leftShoulder=bar?bar.p.reduce((a,b)=>a[0]<b[0]?a:b).slice():center.slice();
    const rightShoulder=bar?bar.p.reduce((a,b)=>a[0]>b[0]?a:b).slice():center.slice();
    const anchors=bar?[leftShoulder,rightShoulder]:[center];
    const pieces=[];
    for(let i=0;i<other.length;i++) {
      if(bar&&i===bar.index)continue;
      const path=other[i],p=path.p,expanded=[p[0]],events=[0];
      for(let k=1;k<p.length;k++) {
        const a=p[k-1],b=p[k],cuts=[];
        cuts.push(...bodyCrossings(a,b));
        for(const root of anchors){const pr=project(root,a,b);if(pr.d<eps*1.5)cuts.push({t:pr.t,point:pr.point});}
        cuts.sort((a,b)=>a.t-b.t);
        for(const c of cuts) {
          if(dist(expanded.at(-1),c.point)>tol*.1)expanded.push(c.point);
          events.push(expanded.length-1);
        }
        if(dist(expanded.at(-1),b)>tol*.1)expanded.push(b);
      }
      events.push(expanded.length-1);
      // Endpoint contacts near a torso (including a waist-returning wrist)
      // are included without snapping their measured coordinates to its axis.
      const sorted=[...new Set(events)].sort((a,b)=>a-b);
      for(let k=1;k<sorted.length;k++) {
        const q=expanded.slice(sorted[k-1],sorted[k]+1);
        if(q.length>1&&length(q)>H*.018)pieces.push({p:q,id:path.id,chain:i,order:k-1,used:false});
      }
    }
    const rootDistance=p=>{
      if(options.action==='akimbo'&&p[1]>sy+H*.07)return Infinity;
      if(gapScale===1||bar)return Math.min(...anchors.map(a=>dist(p,a)));
      // Independently drawn shoulders need not touch the exact same pixel
      // or height. Keep the measured roots within the upper torso band.
      if(p[1]<head.box.y1+H*.008||p[1]>hip[1]-eps*.65&&!twoUpperBranches(center)||Math.abs(p[1]-sy)>H*.12)return Infinity;
      return bodyProject(p).d;
    };
    const rooted=[];
    for(let i=0;i<pieces.length;i++) {
      const piece=pieces[i],a=piece.p[0],b=piece.p.at(-1),da=rootDistance(a),db=rootDistance(b);
      if(Math.min(da,db)>eps*2.2)continue;
      const q=da<=db?piece.p.slice():piece.p.slice().reverse();
      if(length(q)<H*.045)continue;
      const root=q[0],end=q.at(-1),nearHip=dist(root,hip)<eps*2;
      const belowHip=end[1]>hip[1]+H*.12&&Math.min(...q.map(p=>p[1]))>=hip[1]-eps;
      if(nearHip&&belowHip&&(dist(root,hip)<rootDistance(root)-tol*.2||twoUpperBranches(center)))continue;
      rooted.push({p:q,index:i,direction:da<=db?1:-1,rootDistance:Math.min(da,db),id:piece.id});
    }
    const arms=[];
    for(const start of rooted) {
      let q=start.p.slice();const consumed=new Set([start.index]);
      let cursor={index:start.index,direction:start.direction};
      // A body crossing splits one forearm too. Preserve its original source
      // interval rather than treating every relaxed torso contact as a shoulder.
      const baseEps=H*.0105,atAnchor=p=>Math.min(...anchors.map(a=>dist(p,a)))<baseEps*2.2;
      const tangent=(path,fromEnd)=>{
        const end=fromEnd?path.at(-1):path[0];
        const values=fromEnd?path.slice(0,-1).reverse():path.slice(1);
        const v=values.find(p=>dist(p,end)>H*.014)||values.at(-1);
        if(!v)return [0,0];
        const dx=fromEnd?end[0]-v[0]:v[0]-end[0],dy=fromEnd?end[1]-v[1]:v[1]-end[1],n=Math.hypot(dx,dy);
        return n?[dx/n,dy/n]:[0,0];
      };
      for(let step=0;step<12;step++) {
        const end=q.at(-1),bodyContact=q.length>2&&bodyProject(end).d<eps*1.25&&end[1]>sy+eps*2;
        const previous=pieces[cursor.index],incoming=tangent(q,true);
        let next=null;
        for(let j=0;j<pieces.length;j++) {
          if(consumed.has(j))continue;
          const part=pieces[j],isRooted=rooted.some(r=>r.index===j&&j!==start.index);
          for(const reverse of [false,true]) {
            const pp=reverse?part.p.slice().reverse():part.p,d=dist(pp[0],end),direction=reverse?-1:1;
            if(d>eps*1.7||Math.min(...pp.map(v=>v[1]))>hip[1]-eps)continue;
            const adjacent=part.chain===previous.chain&&part.order===previous.order+cursor.direction&&direction===cursor.direction;
            const outgoing=tangent(pp,false),alignment=incoming[0]*outgoing[0]+incoming[1]*outgoing[1];
            const collinear=alignment>.90;
            // Joining an independently rooted opposite arm would swallow closed
            // waist loops and joined hands. Their other endpoint is a shoulder.
            const otherShoulder=atAnchor(pp.at(-1))&&dist(pp.at(-1),end)>baseEps*2.2;
            if(otherShoulder&&(bodyContact||isRooted))continue;
            if(isRooted&&!adjacent&&!(bodyContact&&collinear))continue;
            if(bodyContact&&!adjacent&&!collinear)continue;
            // The torso itself is never a continuation of an arm route.
            if(pp.every(v=>bodyProject(v).d<H*.027)&&Math.abs(pp.at(-1)[1]-pp[0][1])>H*.055)continue;
            const score=d-(adjacent?eps*3:bodyContact&&collinear?eps:0);
            if(!next||score<next.score)next={j,p:pp,d,direction,score};
          }
        }
        if(!next)break;consumed.add(next.j);q.push(...next.p.slice(1));cursor={index:next.j,direction:next.direction};
      }
      const root=q[0],wrist=q.at(-1);
      if(wrist[1]>hip[1]+H*.16)continue;
      // A folded arm can travel outward and then across the full torso width.
      // Bound overall work while checking its two-bone fit below; 1.25 times
      // figure extent wrongly removes valid arms after the paper becomes wider.
      if(dist(root,wrist)<H*.025||length(q)>H*2)continue;
      let elbow=null,maxD=0;
      for(let i=1;i<q.length-1;i++){const d=project(q[i],root,wrist).d;if(d>maxD){maxD=d;elbow=q[i];}}
      if(!elbow||maxD<length(q)*.055) {
        const half=length(q)/2;let walked=0;elbow=mix(root,wrist,.5);
        for(let i=1;i<q.length;i++){const n=dist(q[i-1],q[i]);if(walked+n>=half){elbow=mix(q[i-1],q[i],(half-walked)/n);break;}walked+=n;}
      }
      if(length(q)>(dist(root,elbow)+dist(elbow,wrist))*1.35)continue;
      const departure=q.find(v=>dist(v,root)>H*.025)||wrist;
      arms.push({root,wrist,elbow,departure,p:q,indices:consumed,score:length(q)/H-start.rootDistance/H*3});
    }
    // Re-tracing an arm must not replace the other, shorter waist-return arm.
    for(let i=arms.length-1;i>=0;i--)for(let j=0;j<i;j++) {
      if(dist(arms[i].root,arms[j].root)<eps&&dist(arms[i].wrist,arms[j].wrist)<eps*1.7&&dist(arms[i].elbow,arms[j].elbow)<eps*1.7){arms.splice(i,1);break;}
    }
    if(arms.length<2)return reject('two-arms');
    let pair=null;
    for(let i=0;i<arms.length;i++)for(let j=i+1;j<arms.length;j++) {
      if([...arms[i].indices].some(k=>arms[j].indices.has(k)))continue;
      const score=arms[i].score+arms[j].score;
      if(!pair||score>pair.score)pair={arms:[arms[i],arms[j]],score};
    }
    if(!pair)return reject('independent-arm-paths');
    const identityCost=(a,side)=> {
      const shoulder=side==='left'?leftShoulder:rightShoulder,sign=side==='left'?-1:1;
      let cost=dist(a.root,shoulder)/H*12;
      // When both paths leave the same neck point, departure direction is
      // stronger evidence than the final wrist x (which may cross the chest).
      const dx=a.departure[0]-a.root[0];if(Math.abs(dx)>H*.025&&Math.sign(dx)!==sign)cost+=.7;
      const hint=options.modelPose?.[side+'Wrist'];
      if(Array.isArray(hint)&&hint.every(Number.isFinite)) {
        const hx=hint[0]-(side==='left'?.34:.66),hy=hint[1]-.32;
        const vx=a.wrist[0]-a.root[0],vy=a.wrist[1]-a.root[1],den=Math.hypot(hx,hy)*Math.hypot(vx,vy);
        if(den>1e-6)cost+=(1-(hx*vx+hy*vy)/den)*.12;
      }
      return cost;
    };
    const [a,b]=pair.arms;
    const direct=identityCost(a,'left')+identityCost(b,'right'),reverse=identityCost(b,'left')+identityCost(a,'right');
    const [left,right]=direct<=reverse?[a,b]:[b,a];
    const normal=p=>[clamp(p[0]/width,0,1),clamp(p[1]/height,0,1)];
    const commonFork=dist(a.root,b.root)<eps*2&&Math.sign(a.departure[0]-a.root[0])===Math.sign(b.departure[0]-b.root[0]);
    const ambiguous=!bar&&(commonFork||Math.abs(direct-reverse)<.15);
    const quality=ambiguous?.62:.9;
    return {pose:{head:normal(head.center),leftShoulder:normal(left.root),rightShoulder:normal(right.root),leftElbow:normal(left.elbow),rightElbow:normal(right.elbow),leftWrist:normal(left.wrist),rightWrist:normal(right.wrist)},aspect:width/height,quality,source:'strokes',diagnostics:{identityAmbiguous:ambiguous,headBounds:head.box,neck:normal(neck),hip:normal(hip)}};
  }
  function extract(input,options={}) {
    // A lifted pen often leaves small physical gaps at a shoulder or elbow.
    // Keep the strict solution where possible; retry only failed geometry.
    let diagnostic,best=null;
    const attemptOptions={...options,onDiagnostic:(stage,details)=>{diagnostic={stage,details};}};
    for(const scale of [1,2,3,4,5]) {
      const result=solve(input,attemptOptions,scale);
      if(result){
        const w=Number(options.width)>0?Number(options.width):1,h=Number(options.height)>0?Number(options.height):1;
        const ink=input.flat().filter(p=>Array.isArray(p)&&p.every(Number.isFinite)).map(p=>[p[0]*w,p[1]*h]);
        const box=bounds(ink),H=Math.max(box.x1-box.x0,box.y1-box.y0),p=result.pose;
        const physical=k=>[p[k][0]*w,p[k][1]*h];
        const sl=physical('leftShoulder'),sr=physical('rightShoulder'),wl=physical('leftWrist'),wr=physical('rightWrist');
        let valid=(sl[1]+sr[1])/2<box.y0+H*.60;
        if(options.action==='akimbo') {
          const folded=(side,s,v)=>v[1]>s[1]+H*.015&&Math.abs(physical(side+'Elbow')[0]-s[0])>Math.abs(v[0]-s[0])+H*.02;
          valid&&=folded('left',sl,wl)||folded('right',sr,wr);
        }
        if(options.action==='raise')valid&&=wl[1]<sl[1]-H*.025&&wr[1]<sr[1]-H*.025;
        if(options.action==='left_raise')valid&&=wl[1]<sl[1]-H*.025&&dist(wl,sl)>H*.12&&wr[1]>sr[1];
        if(options.action==='right_raise')valid&&=wr[1]<sr[1]-H*.025&&dist(wr,sr)>H*.12&&wl[1]>sl[1];
        if(valid){
          result.diagnostics.inkGapScale=scale;
          if(!options.action)return result;
          const el=physical('leftElbow'),er=physical('rightElbow');
          const score=(dist(sl,el)+dist(el,wl)+dist(sr,er)+dist(er,wr)-Math.abs(sl[1]-sr[1])*2)/H;
          if(!best||score>best.score+1e-6)best={result,score};
        }
        diagnostic={stage:'arm-topology'};
      }
    }
    if(best)return best.result;
    if(diagnostic&&typeof options.onDiagnostic==='function')options.onDiagnostic(diagnostic.stage,diagnostic.details);
    return null;
  }
  globalThis.ShadowSketchGeometry=Object.freeze({extract});
})();
