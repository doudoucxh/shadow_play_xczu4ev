/* Recognize a catalog action from trained arm-shape features, then raster fallback. */
(() => {
  'use strict';
  const joints=['head','leftShoulder','rightShoulder','leftElbow','rightElbow','leftWrist','rightWrist'];
  const valid=geometry=>geometry?.pose&&joints.every(key=>Array.isArray(geometry.pose[key])&&geometry.pose[key].length===2&&geometry.pose[key].every(Number.isFinite))&&Number.isFinite(geometry.aspect)&&geometry.aspect>0;
  function recognize(strokes,options={}) {
    const model=globalThis.ShadowSketchModel,solver=globalThis.ShadowSketchGeometry;
    if(typeof model?.predict!=='function'||typeof solver?.extract!=='function')return {accepted:false,reason:'unavailable'};
    const raw=model.predict(strokes,options),allowed=model.metadata.enabled_actions||model.metadata.class_order.slice(0,-1);
    if(model.metadata.recognition_profile==='twenty-action-catalog-v1'){
      const topology=globalThis.ShadowSketchTopology?.classify(strokes,options);
      if(topology?.accepted&&allowed.includes(topology.action))return {accepted:true,action:topology.action,geometry:topology.geometry||null,raw,topology,correction:raw.name===topology.action?null:'trained-arm-shape'};
      if(raw?.rejected||!Number.isFinite(raw?.confidence)||raw.confidence<.55||!allowed.includes(raw.name))return {accepted:false,reason:'classification',raw,topology};
      return {accepted:true,action:raw.name,geometry:null,raw,correction:null};
    }
    if(raw?.rejected||!Number.isFinite(raw?.confidence)||raw.confidence<.55||!allowed.includes(raw.name))return {accepted:false,reason:'classification',raw};
    const clamp=(v,a,b)=>Math.max(a,Math.min(b,v)),hint={};
    if(raw.pose){
      hint.head=raw.pose.head?.map((v,i)=>clamp(v,i===0?.36:.07,i===0?.64:.28));
      for(const side of ['left','right']){
        hint[side+'Wrist']=raw.pose[side+'Wrist']?.map((v,i)=>clamp(v,i===0?.04:.07,i===0?.96:.85));
        hint[side+'Elbow']=raw.pose[side+'Elbow']?.map(v=>clamp(v,.025,.975));
      }
    }
    const measuredOptions={...options,modelPose:hint};
    let diagnostic;
    const geometry=solver.extract(strokes,{...measuredOptions,action:raw.name,onDiagnostic:stage=>{diagnostic=stage;}});
    // A full horizontal span has two long, opposite, nearly straight arms.
    // Check this before trusting a punch label: an asymmetric hand drawing
    // otherwise passes joint extraction and keeps the wrong class unchanged.
    if(allowed.includes('open')){
      const measured=valid(geometry)?geometry:solver.extract(strokes,measuredOptions);
      if(valid(measured)&&!measured.diagnostics?.joinedHands){
        const width=Number(options.width)>0?Number(options.width):1,height=Number(options.height)>0?Number(options.height):1;
        const ink=strokes.flat(),xs=ink.map(p=>p[0]*width),ys=ink.map(p=>p[1]*height),extent=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
        const arms=['left','right'].map((side,i)=>{
          const p=measured.pose,s=p[side+'Shoulder'],e=p[side+'Elbow'],w=p[side+'Wrist'];
          const dx=(w[0]-s[0])*width,dy=(w[1]-s[1])*height,ex=(e[0]-s[0])*width,ey=(e[1]-s[1])*height;
          const span=Math.hypot(dx,dy),bend=span?Math.abs(dx*ey-dy*ex)/span:Infinity;
          const along=span?(dx*ex+dy*ey)/(span*span):-1;
          return (i===0?-dx:dx)>extent*.20&&Math.abs(dy)<extent*.10&&Math.abs(dy)<Math.abs(dx)*.30&&bend<extent*.035&&along>.08&&along<.92;
        });
        if(arms.every(Boolean))return {accepted:true,action:'open',geometry:measured,raw,correction:raw.name==='open'?null:'measured-open-arms'};
      }
    }
    if(valid(geometry))return {accepted:true,action:raw.name,geometry,raw,correction:null};
    // A wrong "hands on hips" label must not prevent the independent paths
    // from being read. This fallback still requires a valid classifier gate,
    // one head, one torso, and two measured arm routes.
    const independent=solver.extract(strokes,{...measuredOptions,detectJoinedHands:true});
    // Stage presentation uses a standard action, so failure to recover exact
    // joints is no longer a rejection after the classifier accepts a drawing.
    if(!valid(independent))return {accepted:true,action:raw.name,geometry:null,raw,correction:null};
    if(independent.diagnostics?.joinedHands&&allowed.includes('salute')){
      return {accepted:true,action:'salute',geometry:independent,raw,correction:'measured-joined-hands'};
    }
    if(raw.name==='akimbo'&&!independent.diagnostics?.identityAmbiguous){
      const width=Number(options.width)>0?Number(options.width):1,height=Number(options.height)>0?Number(options.height):1;
      const ink=strokes.flat().filter(p=>Array.isArray(p)&&p.length>=2&&p.slice(0,2).every(Number.isFinite));
      const xs=ink.map(p=>p[0]*width),ys=ink.map(p=>p[1]*height),extent=Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys));
      if(extent>0){
        const pose=independent.pose;
        const delta=side=>(pose[side+'Wrist'][1]-pose[side+'Shoulder'][1])*height/extent;
        const left=delta('left'),right=delta('right');
        const action=left<-.13&&right>.10?'left_raise':right<-.13&&left>.10?'right_raise':null;
        if(action&&allowed.includes(action))return {accepted:true,action,geometry:independent,raw,correction:'measured-one-hand-up'};
      }
    }
    return {accepted:true,action:raw.name,geometry:null,raw,correction:null};
  }
  globalThis.ShadowSketchRecognition=Object.freeze({recognize});
})();
