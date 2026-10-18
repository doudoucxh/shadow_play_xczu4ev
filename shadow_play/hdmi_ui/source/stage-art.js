/* Canvas shadow theatre with embedded photographic puppet assets. No network or device access. */
(function () {
  'use strict';

  const C = { ink: '#39271f' };
  const TAU = Math.PI * 2;

  function path(c, points, fill, stroke, width) {
    c.beginPath();
    points(c);
    if (fill) { c.fillStyle = fill; c.fill(); }
    if (stroke) { c.strokeStyle = stroke; c.lineWidth = width || 1; c.stroke(); }
  }

  function circle(c, x, y, r, fill, stroke, width) {
    c.beginPath(); c.arc(x, y, r, 0, TAU);
    if (fill) { c.fillStyle = fill; c.fill(); }
    if (stroke) { c.strokeStyle = stroke; c.lineWidth = width || 1; c.stroke(); }
  }

  function flower(c, x, y, r, color, count) {
    c.save(); c.translate(x, y);
    c.strokeStyle = color; c.lineWidth = 1.35;
    for (let i = 0; i < (count || 8); i++) {
      c.rotate(TAU / (count || 8));
      c.beginPath(); c.ellipse(0, -r * 0.58, r * 0.18, r * 0.36, 0, 0, TAU); c.stroke();
    }
    circle(c, 0, 0, r * 0.18, color);
    c.restore();
  }

  function cloud(c, x, y, size, alpha) {
    c.save(); c.translate(x, y); c.scale(size, size); c.globalAlpha = alpha;
    c.strokeStyle = '#a87445'; c.lineWidth = 1.5;
    c.beginPath();
    c.moveTo(-42, 4); c.bezierCurveTo(-28, 5, -25, -9, -14, -9);
    c.bezierCurveTo(-25, -26, 0, -32, 8, -17);
    c.bezierCurveTo(12, -8, -1, -6, -4, -14);
    c.bezierCurveTo(15, -36, 38, -16, 24, -5);
    c.bezierCurveTo(45, -16, 60, 4, 42, 10);
    c.bezierCurveTo(24, 17, 15, 9, 3, 12);
    c.bezierCurveTo(-15, 17, -20, 9, -42, 4); c.stroke();
    c.beginPath(); c.moveTo(-42, 16); c.bezierCurveTo(-6, 32, 33, 21, 59, 14); c.stroke();
    c.restore();
  }

  function background(c) {
    const bg = c.createLinearGradient(0, 0, 0, 550);
    bg.addColorStop(0, '#d6b377'); bg.addColorStop(0.14, '#efcf91');
    bg.addColorStop(0.48, '#f8e4b4'); bg.addColorStop(1, '#d9ad67');
    c.fillStyle = bg; c.fillRect(0, 0, 1000, 550);
    const lamp = c.createRadialGradient(515, 257, 40, 515, 270, 590);
    lamp.addColorStop(0, 'rgba(255,248,215,.79)');
    lamp.addColorStop(0.5, 'rgba(255,235,179,.22)'); lamp.addColorStop(1, 'rgba(114,66,25,.19)');
    c.fillStyle = lamp; c.fillRect(0, 0, 1000, 550);

    // Deterministic linen fibers remain still while the puppets move.
    let seed = 317;
    const rand = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    c.lineWidth = 0.4;
    for (let i = 0; i < 1100; i++) {
      const x = rand() * 1000, y = rand() * 550;
      c.strokeStyle = i % 3 ? 'rgba(114,70,29,.055)' : 'rgba(255,251,216,.28)';
      c.beginPath(); c.moveTo(x, y); c.lineTo(x + rand() * 9, y + rand() * 0.8); c.stroke();
    }
    c.strokeStyle = 'rgba(126,81,43,.036)'; c.lineWidth = .45;
    for (let x = 3; x < 1000; x += 6) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, 550); c.stroke(); }

    // Mountains painted onto the translucent screen, quieter than the puppets.
    path(c, p => {
      p.moveTo(0, 362); p.bezierCurveTo(80, 350, 85, 306, 167, 318);
      p.bezierCurveTo(245, 329, 246, 270, 311, 289);
      p.bezierCurveTo(337, 298, 351, 267, 390, 276);
      p.bezierCurveTo(428, 285, 428, 336, 472, 324);
      p.bezierCurveTo(540, 308, 557, 253, 604, 270);
      p.bezierCurveTo(650, 287, 648, 321, 708, 316);
      p.bezierCurveTo(759, 308, 775, 276, 812, 290);
      p.bezierCurveTo(855, 305, 893, 333, 1000, 315);
      p.lineTo(1000, 478); p.lineTo(0, 478); p.closePath();
    }, 'rgba(157,127,73,.105)');
    path(c, p => {
      p.moveTo(0, 411); p.bezierCurveTo(98, 373, 192, 400, 249, 371);
      p.bezierCurveTo(328, 343, 352, 383, 409, 389);
      p.bezierCurveTo(479, 395, 522, 366, 593, 387);
      p.bezierCurveTo(643, 402, 691, 342, 733, 355);
      p.bezierCurveTo(801, 372, 838, 367, 901, 345);
      p.bezierCurveTo(949, 326, 972, 341, 1000, 361);
      p.lineTo(1000, 486); p.lineTo(0, 486); p.closePath();
    }, 'rgba(148,110,60,.125)');

    cloud(c, 318, 164, .86, .14); cloud(c, 724, 141, .65, .13);
    rocks(c);
    wineFlag(c);
    c.strokeStyle = 'rgba(136,87,42,.18)'; c.lineWidth = 1;
    c.beginPath(); c.moveTo(115, 479); c.bezierCurveTo(361, 467, 710, 486, 895, 470); c.stroke();
    c.beginPath(); c.moveTo(154, 485); c.bezierCurveTo(399, 480, 683, 499, 844, 487); c.stroke();
    c.fillStyle = 'rgba(127,73,31,.06)'; c.fillRect(0, 509, 1000, 41);
    // Traditional carved trim, also useful as the HDMI safe-picture frame.
    c.strokeStyle = 'rgba(136,81,37,.24)'; c.lineWidth = 1;
    c.strokeRect(24, 24, 952, 502); c.strokeRect(29, 29, 942, 492);
    [[35, 35, 1, 1], [965, 35, -1, 1], [35, 515, 1, -1], [965, 515, -1, -1]].forEach(a => {
      c.save(); c.translate(a[0], a[1]); c.scale(a[2], a[3]);
      c.strokeStyle = 'rgba(132,77,31,.38)'; c.lineWidth = 1.4;
      c.beginPath(); c.moveTo(0, 46); c.lineTo(0, 0); c.lineTo(46, 0);
      c.moveTo(7, 31); c.lineTo(7, 7); c.lineTo(31, 7);
      c.moveTo(14, 21); c.lineTo(14, 14); c.lineTo(21, 14); c.stroke(); c.restore();
    });
  }

  function tree(c) {
    c.save(); c.globalAlpha = .35;
    path(c, p => {
      p.moveTo(108, 474); p.bezierCurveTo(156, 433, 156, 343, 155, 287);
      p.bezierCurveTo(155, 240, 167, 204, 166, 176);
      p.lineTo(157, 146); p.lineTo(170, 170); p.lineTo(181, 137);
      p.lineTo(176, 179); p.lineTo(194, 215); p.lineTo(202, 194);
      p.lineTo(205, 225); p.lineTo(231, 245); p.lineTo(258, 238);
      p.lineTo(238, 253); p.lineTo(220, 254); p.lineTo(183, 225);
      p.bezierCurveTo(177, 257, 173, 281, 181, 308);
      p.lineTo(222, 299); p.lineTo(251, 275); p.lineTo(239, 299);
      p.lineTo(270, 309); p.lineTo(227, 309); p.lineTo(180, 332);
      p.bezierCurveTo(173, 390, 177, 433, 200, 474); p.closePath();
    }, '#7e582f', '#79532c', 1);
    c.strokeStyle = '#e3bf7d'; c.lineWidth = 2;
    c.beginPath(); c.moveTo(159, 438); c.bezierCurveTo(153, 367, 176, 327, 164, 252); c.stroke();
    const leaves = [
      [135, 179, 41, 20, -.45], [181, 144, 41, 21, -.3], [212, 178, 38, 19, .5],
      [114, 222, 47, 21, -.18], [153, 200, 45, 23, .25], [230, 228, 44, 20, -.2],
      [259, 239, 29, 14, .24], [240, 294, 36, 17, -.28], [285, 312, 26, 13, .2],
      [128, 317, 38, 17, -.2], [91, 311, 28, 15, .45]
    ];
    leaves.forEach((l, i) => {
      c.save(); c.translate(l[0], l[1]); c.rotate(l[4]);
      path(c, p => {
        p.moveTo(-l[2], 4); p.bezierCurveTo(-l[2]*.7, -l[3]*1.2, -11, -l[3], 0, -l[3]*.72);
        p.bezierCurveTo(16, -l[3]*1.6, l[2]*.7, -l[3]*.7, l[2], 3);
        p.bezierCurveTo(l[2]*.5, l[3], -l[2]*.6, l[3], -l[2], 4); p.closePath();
      }, i % 2 ? '#9b793e' : '#8f6836');
      c.strokeStyle = '#dfbd79'; c.lineWidth = 1.1;
      c.beginPath(); c.moveTo(-l[2]*.76, 3); c.lineTo(l[2]*.75, 2); c.stroke();
      for (let x = -l[2]*.55; x < l[2]*.55; x += 13) {
        c.beginPath(); c.moveTo(x, 2); c.lineTo(x+6, -8); c.moveTo(x, 2); c.lineTo(x+4, 8); c.stroke();
      }
      c.restore();
    });
    c.restore();
  }

  function rocks(c) {
    c.save(); c.globalAlpha = .25;
    path(c, p => {
      p.moveTo(811, 474); p.lineTo(827, 426); p.lineTo(854, 410); p.lineTo(881, 423);
      p.lineTo(898, 448); p.lineTo(947, 462); p.lineTo(961, 475); p.closePath();
    }, '#896338', '#816037', 1);
    path(c, p => { p.moveTo(828, 458); p.lineTo(854, 421); p.lineTo(869, 436); p.moveTo(857, 425); p.lineTo(856, 459); p.lineTo(912, 466); }, null, '#e6c57c', 2);
    // Grass and a few twig shapes anchor the theatre without crowding the action.
    c.strokeStyle = '#73502c'; c.lineWidth = 2;
    [[87,473],[224,478],[803,476],[929,477]].forEach(a => {
      c.beginPath(); c.moveTo(a[0], a[1]); c.quadraticCurveTo(a[0]-5,a[1]-19,a[0]-14,a[1]-24);
      c.moveTo(a[0],a[1]); c.quadraticCurveTo(a[0]+2,a[1]-29,a[0]+8,a[1]-38);
      c.moveTo(a[0],a[1]); c.quadraticCurveTo(a[0]+11,a[1]-15,a[0]+20,a[1]-18); c.stroke();
    }); c.restore();
  }


  function wineFlag(c) {
    const record=assetRecords.flag;if(!record.ready)return;
    // Use the supplied physical prop photograph unchanged. Multiply lets its
    // white photograph backdrop share the existing translucent stage lighting.
    c.save();c.translate(84,66);c.scale(96/126,96/126);
    c.globalAlpha=.92;c.globalCompositeOperation='multiply';
    // The lower-right corner of the reference contains a piece of tiger tail.
    // A display clip retains the complete banner and its pointed fringe.
    c.beginPath();c.moveTo(0,0);c.lineTo(126,0);c.lineTo(126,238);c.lineTo(94,238);
    c.lineTo(81,251);c.lineTo(65,258);c.lineTo(48,249);c.lineTo(34,238);c.lineTo(0,238);c.closePath();c.clip();
    c.drawImage(record.image,0,0);
    c.restore();
  }

  const assetRecords = {
    wusong: { source: null, image: null, ready: false },
    tiger: { source: null, image: null, ready: false },
    flag: { source: null, image: null, ready: false },
  };
  let scenery = null;
  let puppetRig = null;
  let tigerRig = null;
  const NEUTRAL = { head: [.5, .18], leftWrist: [.22, .68], rightWrist: [.78, .68] };

  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
  function smooth(a, b, value) {
    const t = clamp((value - a) / (b - a), 0, 1);
    return t * t * (3 - 2 * t);
  }

  // Flatten the grade once per source; animated joints only copy cached pixels.
  function gradedImage(source) {
    if (!globalThis.ShadowBoardDisplay) return source;
    const canvas=document.createElement('canvas');
    canvas.width=source.naturalWidth||source.width;canvas.height=source.naturalHeight||source.height;
    const paint=canvas.getContext('2d');
    paint.filter='sepia(.5) saturate(.65) brightness(.84) contrast(1.08)';
    paint.drawImage(source,0,0);
    const pixels=paint.getImageData(0,0,canvas.width,canvas.height);
    paint.filter='none';paint.putImageData(pixels,0,0);
    return canvas;
  }

  function flatten(canvas) {
    if(globalThis.ShadowBoardDisplay){const ctx=canvas.getContext('2d'),pixels=ctx.getImageData(0,0,canvas.width,canvas.height);ctx.save();ctx.globalCompositeOperation='source-over';ctx.putImageData(pixels,0,0);ctx.restore();}
    return canvas;
  }

  // Only embedded data URIs are accepted. No remote or local-file request is made.
  function ensureAssets() {
    const supplied = window.ShadowPuppetAssets || {};
    Object.keys(assetRecords).forEach(name => {
      const entry = supplied[name];
      const source = typeof entry === 'string' ? entry : entry && (entry.dataUri || entry.src);
      const record = assetRecords[name];
      if (!source || !/^data:image\//i.test(source) || source === record.source) return;
      const img = new Image();
      record.source = source; record.image = img; record.ready = false;
      if (name === 'wusong') puppetRig = null;
      if (name === 'tiger') tigerRig = null;
      if (name === 'flag') scenery = null;
      img.onload = () => {
        if (record.image !== img) return;
        record.ready = img.naturalWidth > 0 && img.naturalHeight > 0;
        if(record.ready && name!=='flag')record.image=gradedImage(img);
        if(name==='flag')scenery=null;
        if (record.ready) window.dispatchEvent(new CustomEvent('shadow:art-ready', {
          detail: { asset: name, ready: Object.keys(assetRecords).every(key => !assetRecords[key].source||assetRecords[key].ready) },
        }));
      };
      img.onerror = () => { if (record.image === img) record.ready = false; };
      img.src = source;
    });
  }

  function backdrop(c) {
    if (!scenery) {
      scenery = document.createElement('canvas'); scenery.width = 1000; scenery.height = 550;
      background(scenery.getContext('2d'));
      scenery=gradedImage(scenery);
    }
    c.drawImage(scenery, 0, 0);
  }

  function readPoint(pose, name) {
    const p = pose && pose[name];
    return Array.isArray(p) && p.length >= 2 && Number.isFinite(p[0]) && Number.isFinite(p[1])
      ? [clamp(p[0], 0, 1), clamp(p[1], 0, 1)] : NEUTRAL[name];
  }


  const RIG = {
    head: { pivot: [94, 183], polygon: [[0,0],[214,0],[214,165],[117,165],[113,185],[77,185],[75,165],[0,165]] },
    left: {
      pivot: [78, 243], wrist: [22, 357],
      polygon: [[76,237],[91,247],[80,266],[68,283],[60,307],[60,325],[58,341],[46,354],[32,371],[34,424],[-3,424],[-3,366],[8,345],[13,325],[22,305],[35,282],[53,259]],
    },
    right: {
      pivot: [114, 201], wrist: [152, 298],
      polygon: [[105,186],[220,186],[220,333],[132,333],[130,295],[140,275],[134,249],[109,228]],
      partPolygon: [[105,186],[220,186],[220,280],[188,306],[163,322],[149,321],[136,312],[141,298],[155,281],[177,258],[158,244],[137,235],[109,228]],
    },
  };

  function rigCanvas(image) {
    const canvas = document.createElement('canvas');
    canvas.width = (image.naturalWidth||image.width); canvas.height = (image.naturalHeight||image.height);
    return canvas;
  }

  function rigPath(c, polygon, sx, sy) {
    c.beginPath();
    polygon.forEach((p, i) => { if (i) c.lineTo(p[0] * sx, p[1] * sy); else c.moveTo(p[0] * sx, p[1] * sy); });
    c.closePath();
  }

  function prepareRig(image) {
    const sx = (image.naturalWidth||image.width) / 214, sy = (image.naturalHeight||image.height) / 640;
    const parts = {};
    Object.keys(RIG).forEach(name => {
      const canvas = rigCanvas(image), c = canvas.getContext('2d');
      c.drawImage(image, 0, 0);
      c.globalCompositeOperation = 'destination-in';
      rigPath(c, RIG[name].partPolygon || RIG[name].polygon, sx, sy); c.fill();
      parts[name] = canvas;
    });
    const body = rigCanvas(image), c = body.getContext('2d');
    c.drawImage(image, 0, 0);
    c.globalCompositeOperation = 'destination-out';
    Object.keys(RIG).forEach(name => {
      rigPath(c, RIG[name].polygon, sx, sy); c.fill();
      c.lineWidth = .7 * Math.max(sx, sy); c.stroke();
    });
    c.globalCompositeOperation = 'source-over';
    // The photographed wrists overlap a little brocade. Reuse nearby real cloth
    // behind those joints, so a lifted arm reveals a closed torso, not a white gap.
    function cloth(polygon, source, destination) {
      c.save(); rigPath(c, polygon, sx, sy); c.clip();
      c.drawImage(image, source[0]*sx, source[1]*sy, source[2]*sx, source[3]*sy,
        destination[0]*sx, destination[1]*sy, destination[2]*sx, destination[3]*sy);
      c.restore();
    }
    cloth([[67,242],[86,241],[93,251],[86,299],[77,335],[49,335],[58,300]],
      [91,246,38,89], [56,246,38,89]);
    cloth([[126,274],[139,276],[148,298],[148,318],[139,333],[126,332]],
      [102,277,29,56], [125,277,26,56]);
    const caps = {};
    for (const name of ['left', 'right']) {
      const pivot = RIG[name].pivot, radius = name === 'left' ? 11 : 12;
      const cap = document.createElement('canvas'); cap.width = Math.ceil(radius*2*sx); cap.height = Math.ceil(radius*2*sy);
      const pc = cap.getContext('2d'); pc.beginPath();
      pc.ellipse(cap.width/2,cap.height/2,cap.width/2,cap.height/2,0,0,TAU); pc.clip();
      pc.drawImage(image,(pivot[0]-radius)*sx,(pivot[1]-radius)*sy,radius*2*sx,radius*2*sy,0,0,cap.width,cap.height);
      caps[name] = { canvas: cap, radius };
    }
    for(const canvas of [body,...Object.values(parts),...Object.values(caps).map(cap=>cap.canvas)])flatten(canvas);
    return { image, body, parts, caps, sx, sy };
  }

  function wrapAngle(angle) {
    while (angle > Math.PI) angle -= TAU;
    while (angle < -Math.PI) angle += TAU;
    return angle;
  }

  function armAngle(point, side) {
    const shoulder = side === 'left' ? [.34,.32] : [.66,.32];
    const definition = RIG[side];
    const dx = point[0] - shoulder[0], dy = point[1] - shoulder[1];
    if (Math.hypot(dx,dy) < .035) return 0;
    const original = Math.atan2(definition.wrist[1]-definition.pivot[1],definition.wrist[0]-definition.pivot[0]);
    return wrapAngle(Math.atan2(dy,dx)-original);
  }

  function motionFor(options) {
    const active = options.mode === 'home' || options.mode === 'classic' || !options.mode;
    const t = clamp(Number(options.time) || 0, 0, 1) * TAU;
    let control = options.controlPose;
    if (!control && options.pose && !active) {
      const legacy = options.pose;
      control = { head: NEUTRAL.head };
      for (const [side, oldX, oldY] of [['left',.364,.509],['right',.542,.507]]) {
        const p = legacy[side+'Wrist'], neutral = NEUTRAL[side+'Wrist'];
        control[side+'Wrist'] = Array.isArray(p) && p.every(Number.isFinite)
          ? [clamp(neutral[0]+(p[0]-oldX)*2,0,1),clamp(neutral[1]+(p[1]-oldY)*1.8,0,1)] : neutral;
      }
    }
    if (control) {
      const head = readPoint(control,'head');
      return {
        left: armAngle(readPoint(control,'leftWrist'),'left'),
        right: armAngle(readPoint(control,'rightWrist'),'right'),
        head: clamp((head[0]-.5)*1.1+(head[1]-.18)*.28,-.28,.28),
        bounce: 0,
      };
    }
    return {
      left: active ? .10+Math.sin(t)*.18 : 0,
      right: active ? -.13+Math.sin(t+.6)*.20 : 0,
      head: active ? Math.sin(t)*.055 : 0,
      bounce: active ? Math.sin(t*2)*1.5 : 0,
    };
  }

  function rotatedWrist(side, angle) {
    const {pivot,wrist} = RIG[side], dx = wrist[0]-pivot[0], dy = wrist[1]-pivot[1];
    return [pivot[0]+dx*Math.cos(angle)-dy*Math.sin(angle),pivot[1]+dx*Math.sin(angle)+dy*Math.cos(angle)];
  }

  const TOUCH_ARM_JOINTS = {
    left:{shoulder:[78,243],elbow:[43,303],wrist:[22,357],radius:11},
    right:{shoulder:[114,201],elbow:[194,249],wrist:[152,298],radius:13},
  };

  function resolvedTouchPose(options) {
    const state=touchActorState(options,'wusong');
    const fallback=TOUCH_POSES[state.action]||TOUCH_POSES.neutral||NEUTRAL;
    const supplied=state.pose||options.controlPose,raw=supplied||fallback,pose={};
    const point=p=>Array.isArray(p)&&p.length>1&&Number.isFinite(p[0])&&Number.isFinite(p[1])?[clamp(p[0],0,1),clamp(p[1],0,1)]:null;
    for(const key of ['head','leftWrist','rightWrist'])pose[key]=point(raw&&raw[key])||fallback[key];
    const neck=point(raw&&raw.shoulderCenter)||point(raw&&raw.neck);
    pose.hasShoulders=!!(neck||(point(raw&&raw.leftShoulder)&&point(raw&&raw.rightShoulder)));
    for(const side of ['left','right']) {
      const shoulder=point(raw&&raw[side+'Shoulder'])||neck||(side==='left'?[.34,.32]:[.66,.32]);
      pose[side+'Shoulder']=shoulder;
      pose[side+'Elbow']=point(raw&&raw[side+'Elbow'])||(!supplied&&fallback[side+'Elbow'])
        ||[(shoulder[0]+pose[side+'Wrist'][0])/2,(shoulder[1]+pose[side+'Wrist'][1])/2];
    }
    return pose;
  }

  function touchPoseAspect(options) {
    const state=touchActorState(options,'wusong');
    const value=Number(state.poseAspect||options.poseAspect);
    return Number.isFinite(value)&&value>0?clamp(value,.1,10):1;
  }

  function touchPuppetJoints(options) {
    const pose=resolvedTouchPose(options),aspect=touchPoseAspect(options);
    const actor=touchActorState(options,'wusong');
    const levelOpen=actor.poseSource==='standard'&&actor.action==='open';
    const neck=[(pose.leftShoulder[0]+pose.rightShoulder[0])/2,(pose.leftShoulder[1]+pose.rightShoulder[1])/2];
    const head=pose.hasShoulders?clamp(Math.atan2((pose.head[0]-neck[0])*aspect,neck[1]-pose.head[1]),-.28,.28)
      :motionFor({mode:'touch',controlPose:pose}).head;
    const result={pose,aspect,head};
    for(const side of ['left','right']) {
      const source=TOUCH_ARM_JOINTS[side],s=source.shoulder.slice();
      // The photograph is in side profile: its two shoulder pins differ by
      // 42 source pixels. Level only the standard open pose at their midpoint.
      if(levelOpen)s[1]=(TOUCH_ARM_JOINTS.left.shoulder[1]+TOUCH_ARM_JOINTS.right.shoulder[1])/2;
      const upperLength=Math.hypot(source.elbow[0]-source.shoulder[0],source.elbow[1]-source.shoulder[1]);
      const lowerLength=Math.hypot(source.wrist[0]-source.elbow[0],source.wrist[1]-source.elbow[1]);
      const requested={shoulder:pose[side+'Shoulder'],elbow:pose[side+'Elbow'],wrist:pose[side+'Wrist']};
      function angle(a,b,rest) {
        const dx=(b[0]-a[0])*aspect,dy=b[1]-a[1];
        return Math.hypot(dx,dy)>1e-6?Math.atan2(dy,dx):rest;
      }
      const originalUpper=Math.atan2(source.elbow[1]-source.shoulder[1],source.elbow[0]-source.shoulder[0]);
      const originalLower=Math.atan2(source.wrist[1]-source.elbow[1],source.wrist[0]-source.elbow[0]);
      const upperDirection=angle(requested.shoulder,requested.elbow,originalUpper);
      const lowerDirection=angle(requested.elbow,requested.wrist,upperDirection);
      // Use each drawn segment's direction. Absolute canvas position and short
      // stroke length must not collapse an extended arm into a global IK target.
      const elbow=[s[0]+Math.cos(upperDirection)*upperLength,s[1]+Math.sin(upperDirection)*upperLength];
      const wrist=[elbow[0]+Math.cos(lowerDirection)*lowerLength,elbow[1]+Math.sin(lowerDirection)*lowerLength];
      result[side]={shoulder:s,elbow,wrist,requested,upperDirection,lowerDirection,
        upper:upperDirection-originalUpper,lower:lowerDirection-originalLower};
    }
    return result;
  }

  function prepareTouchArmPieces(rig) {
    const pieces={};
    function clipped(source,polygon) {
      const canvas=rigCanvas(rig.image),c=canvas.getContext('2d');c.drawImage(source,0,0);
      c.globalCompositeOperation='destination-in';rigPath(c,polygon,rig.sx,rig.sy);c.fill();return canvas;
    }
    for(const side of ['left','right']) {
      const joint=TOUCH_ARM_JOINTS[side],whole=rig.parts[side];
      let upperPolygon,lowerPolygon;
      if(side==='left') {
        const line=x=>303+(x-43)*.389;
        upperPolygon=[[-100,-100],[314,-100],[314,line(314)+5],[-100,line(-100)+5]];
        lowerPolygon=[[-100,line(-100)-5],[314,line(314)-5],[314,740],[-100,740]];
      } else {
        upperPolygon=[[-100,-100],[314,-100],[314,254],[-100,254]];
        lowerPolygon=[[177,244],[218,244],[220,279],[189,310],[163,323],[149,322],[136,312],[141,298],[155,281],[173,263]];
      }
      const cap=document.createElement('canvas'),r=joint.radius;
      cap.width=Math.ceil(r*2*rig.sx);cap.height=Math.ceil(r*2*rig.sy);
      const cc=cap.getContext('2d');cc.beginPath();cc.ellipse(cap.width/2,cap.height/2,cap.width/2,cap.height/2,0,0,TAU);cc.clip();
      cc.drawImage(whole,(joint.elbow[0]-r)*rig.sx,(joint.elbow[1]-r)*rig.sy,r*2*rig.sx,r*2*rig.sy,0,0,cap.width,cap.height);
      pieces[side]={upper:clipped(whole,upperPolygon),lower:clipped(whole,lowerPolygon),cap};
    }
    return pieces;
  }

  function drawTouchPuppetRig(c,rig,options) {
    if(!rig.touchArms)rig.touchArms=prepareTouchArmPieces(rig);
    const joints=touchPuppetJoints(options);
    c.drawImage(rig.body,0,0);
    const head=RIG.head.pivot;c.save();c.translate(head[0]*rig.sx,head[1]*rig.sy);c.rotate(joints.head);
    c.drawImage(rig.parts.head,-head[0]*rig.sx,-head[1]*rig.sy);c.restore();
    for(const side of ['right','left']) {
      const source=TOUCH_ARM_JOINTS[side],joint=joints[side],parts=rig.touchArms[side];
      const cap=rig.caps[side],p=joint.shoulder;
      if(p[1]!==source.shoulder[1]){
        // Reuse the photographed shoulder leather to bridge the small pin
        // adjustment; do not leave an exposed gap at the torso.
        c.drawImage(cap.canvas,(p[0]-cap.radius)*rig.sx,(Math.min(p[1],source.shoulder[1])-cap.radius)*rig.sy,
          cap.radius*2*rig.sx,(Math.abs(p[1]-source.shoulder[1])+cap.radius*2)*rig.sy);
      }
      c.save();c.translate(joint.shoulder[0]*rig.sx,joint.shoulder[1]*rig.sy);c.rotate(joint.upper);
      c.drawImage(parts.upper,-source.shoulder[0]*rig.sx,-source.shoulder[1]*rig.sy);c.restore();
      c.save();c.translate(joint.elbow[0]*rig.sx,joint.elbow[1]*rig.sy);c.rotate(joint.lower);
      c.drawImage(parts.lower,-source.elbow[0]*rig.sx,-source.elbow[1]*rig.sy);c.restore();
      c.save();c.translate(joint.elbow[0]*rig.sx,joint.elbow[1]*rig.sy);c.rotate(joint.upper);
      c.drawImage(parts.cap,-source.radius*rig.sx,-source.radius*rig.sy);c.restore();
      c.drawImage(cap.canvas,(p[0]-cap.radius)*rig.sx,(p[1]-cap.radius)*rig.sy);
    }
  }

  function realPuppet(c, options, placement) {
    const record = assetRecords.wusong;
    if (!record.ready) return;
    const image = record.image;
    if(options.mode==='touch'||options.mode==='body'&&options.controlPose){
      // Reflect the leather, while keeping drawn left/right arm directions on screen.
      const resolved=resolvedTouchPose(options),pose={head:[1-resolved.head[0],resolved.head[1]]};
      for(const side of ['left','right'])for(const joint of ['Wrist','Elbow','Shoulder']){
        if(joint==='Shoulder'&&!resolved.hasShoulders)continue;
        const p=resolved[(side==='left'?'right':'left')+joint];pose[side+joint]=[1-p[0],p[1]];
      }
      options=Object.assign({},options,{actors:{wusong:Object.assign({},touchActorState(options,'wusong'),{pose})},controlPose:pose});
    }
    const motion=motionFor(options);
    if (!puppetRig || puppetRig.image !== image) puppetRig = prepareRig(image);
    const rig = puppetRig, height = placement ? placement.renderHeight : 384, scale = height / (image.naturalHeight||image.height);
    c.save(); c.translate((placement ? placement.originX : 335.4)+(image.naturalWidth||image.width)*scale,(placement ? placement.originY : 98)+motion.bounce); c.scale(-scale,scale);
    c.shadowColor = globalThis.ShadowBoardDisplay ? 'transparent' : 'rgba(65,43,18,.16)'; c.shadowBlur = 2; c.shadowOffsetX = 1; c.shadowOffsetY = 1;
    if(options.mode==='touch'){drawTouchPuppetRig(c,rig,options);c.restore();return;}
    function part(name, angle) {
      const p = RIG[name].pivot;
      c.save(); c.translate(p[0]*rig.sx,p[1]*rig.sy); c.rotate(angle);
      c.drawImage(rig.parts[name],-p[0]*rig.sx,-p[1]*rig.sy); c.restore();
    }
    // Independent flat leather pieces rotate at their actual shoulder pivots.
    // The body has the old arm silhouettes removed; there is no resting-arm ghost.
    c.drawImage(rig.body,0,0);
    part('head',motion.head);
    part('right',motion.right); part('left',motion.left);
    for (const name of ['left','right']) {
      const cap = rig.caps[name], p = RIG[name].pivot;
      c.drawImage(cap.canvas,(p[0]-cap.radius)*rig.sx,(p[1]-cap.radius)*rig.sy);
    }
    c.restore();
  }

  function realTiger(c, mode, time) {
    const record = assetRecords.tiger;
    if (!record.ready) return;
    const image = record.image;
    const active = mode === 'classic' || mode === 'home';
    const t = clamp(Number(time) || 0, 0, 1) * TAU;
    const height = 218, width = height * (image.naturalWidth||image.width) / (image.naturalHeight||image.height);
    const shift = active ? Math.sin(t) * 4 : 0;
    c.save();
    c.translate(517.6 + shift + width * .52, 482);
    c.rotate(active ? Math.sin(t * 2) * .012 : 0);
    c.shadowColor = globalThis.ShadowBoardDisplay ? 'transparent' : 'rgba(65,43,18,.16)'; c.shadowBlur = 3; c.shadowOffsetX = 1; c.shadowOffsetY = 1;
    c.scale(-1,1);c.drawImage(image, -width * .48, -height, width, height);
    c.restore();
  }



  const TIGER_RIG = {
    tail: { pivot:[163,180], polygon:[[-5,-5],[112,-5],[154,75],[183,122],[196,184],[166,200],[143,164],[119,124],[88,105],[42,96],[2,79],[-6,43]] },
    head: { pivot:[454,182], polygon:[[435,126],[451,98],[487,76],[529,78],[574,93],[613,120],[645,163],[650,224],[632,262],[585,278],[535,269],[497,252],[465,227],[447,199],[435,164]] },
    frontNear: { pivot:[382,278], foot:[472,377], polygon:[[355,260],[389,259],[411,286],[439,311],[469,324],[495,326],[512,340],[512,359],[493,376],[467,385],[442,377],[418,356],[396,332],[378,312],[361,292]] },
    frontFar: { pivot:[345,277], foot:[368,391], polygon:[[321,262],[358,261],[372,294],[379,329],[393,344],[401,361],[401,382],[382,397],[350,397],[329,384],[321,351],[319,312]] },
    rearNear: { pivot:[167,292], foot:[225,374], polygon:[[142,270],[179,275],[191,300],[207,318],[226,323],[253,329],[265,348],[260,378],[234,388],[209,385],[189,369],[174,345],[156,326],[146,303]] },
    rearFar: { pivot:[105,277], foot:[108,375], polygon:[[78,255],[118,255],[133,274],[131,305],[132,330],[146,341],[153,359],[149,379],[124,385],[97,382],[77,370],[66,351],[69,318],[75,285]] },
  };
  const TOUCH_POSES = {"neutral":{"head":[0.5,0.17],"leftWrist":[0.22,0.68],"rightWrist":[0.78,0.68],"leftElbow":[0.29,0.49],"rightElbow":[0.71,0.49]},"open":{"head":[0.5,0.17],"leftWrist":[0.055,0.35],"rightWrist":[0.945,0.35],"leftElbow":[0.23,0.34],"rightElbow":[0.77,0.34]},"raise":{"head":[0.5,0.17],"leftWrist":[0.22,0.055],"rightWrist":[0.78,0.055],"leftElbow":[0.2,0.3],"rightElbow":[0.8,0.3]},"strike":{"head":[0.5,0.17],"leftWrist":[0.045,0.34],"rightWrist":[0.64,0.34],"leftElbow":[0.2,0.34],"rightElbow":[0.77,0.48]},"left_raise":{"head":[0.5,0.17],"leftWrist":[0.22,0.055],"rightWrist":[0.78,0.68],"leftElbow":[0.2,0.3],"rightElbow":[0.71,0.49]},"right_raise":{"head":[0.5,0.17],"leftWrist":[0.22,0.68],"rightWrist":[0.78,0.055],"leftElbow":[0.29,0.49],"rightElbow":[0.8,0.3]},"guard":{"head":[0.5,0.17],"leftWrist":[0.37,0.17],"rightWrist":[0.63,0.17],"leftElbow":[0.26,0.38],"rightElbow":[0.74,0.38]},"akimbo":{"head":[0.5,0.17],"leftWrist":[0.4,0.56],"rightWrist":[0.6,0.56],"leftElbow":[0.22,0.43],"rightElbow":[0.78,0.43]},"salute":{"head":[0.5,0.17],"leftWrist":[0.46,0.4],"rightWrist":[0.54,0.4],"leftElbow":[0.3,0.52],"rightElbow":[0.7,0.52]},"point":{"head":[0.5,0.17],"leftWrist":[0.045,0.34],"rightWrist":[0.78,0.68],"leftElbow":[0.2,0.34],"rightElbow":[0.71,0.49]},"diagonal":{"head":[0.5,0.17],"leftWrist":[0.055,0.2],"rightWrist":[0.945,0.2],"leftElbow":[0.23,0.27],"rightElbow":[0.77,0.27]},"palms":{"head":[0.5,0.17],"leftWrist":[0.48,0.23],"rightWrist":[0.52,0.23],"leftElbow":[0.32,0.43],"rightElbow":[0.68,0.43]},"both_left":{"head":[0.5,0.17],"leftWrist":[0.055,0.3],"rightWrist":[0.1,0.39],"leftElbow":[0.22,0.32],"rightElbow":[0.35,0.36]},"both_right":{"head":[0.5,0.17],"leftWrist":[0.9,0.39],"rightWrist":[0.945,0.3],"leftElbow":[0.65,0.36],"rightElbow":[0.78,0.32]},"both_left_up":{"head":[0.5,0.17],"leftWrist":[0.14,0.035],"rightWrist":[0.17,0.12],"leftElbow":[0.29,0.18],"rightElbow":[0.4,0.25]},"both_right_up":{"head":[0.5,0.17],"leftWrist":[0.83,0.12],"rightWrist":[0.86,0.035],"leftElbow":[0.6,0.25],"rightElbow":[0.71,0.18]},"both_left_down":{"head":[0.5,0.17],"leftWrist":[0.1,0.67],"rightWrist":[0.14,0.73],"leftElbow":[0.24,0.49],"rightElbow":[0.35,0.53]},"both_right_down":{"head":[0.5,0.17],"leftWrist":[0.86,0.73],"rightWrist":[0.9,0.67],"leftElbow":[0.65,0.53],"rightElbow":[0.76,0.49]},"both_left_split":{"head":[0.5,0.17],"leftWrist":[0.12,0.045],"rightWrist":[0.1,0.65],"leftElbow":[0.28,0.19],"rightElbow":[0.36,0.49]},"both_right_split":{"head":[0.5,0.17],"leftWrist":[0.9,0.65],"rightWrist":[0.88,0.045],"leftElbow":[0.64,0.49],"rightElbow":[0.72,0.19]}};
  const TIGER_ACTIONS = ['neutral','paw','leap','crouch','sit','stretch','walk','look_up','look_down','rear','tail_up','lie'];
  const TIGER_BOUNDS = [-70,-180,830,440];

  function photoHull(canvas,sx,sy) {
    const c=canvas.getContext('2d'),w=canvas.width,h=canvas.height;
    const pixels=c.getImageData(0,0,w,h).data,points=[];
    for(let y=0;y<h;y++) {
      let first=-1,last=-1;
      for(let x=0;x<w;x++)if(pixels[(y*w+x)*4+3]>=48){if(first<0)first=x;last=x;}
      if(first>=0){points.push([(first+.5)/sx,(y+.5)/sy]);if(last!==first)points.push([(last+.5)/sx,(y+.5)/sy]);}
    }
    if(points.length<3)return points;
    points.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    const lower=[],upper=[];
    for(const p of points){while(lower.length>1&&cross(lower[lower.length-2],lower[lower.length-1],p)<=0)lower.pop();lower.push(p);}
    for(let i=points.length-1;i>=0;i--){const p=points[i];while(upper.length>1&&cross(upper[upper.length-2],upper[upper.length-1],p)<=0)upper.pop();upper.push(p);}
    lower.pop();upper.pop();return lower.concat(upper);
  }

  function prepareTigerRig(image) {
    const sx=(image.naturalWidth||image.width)/640,sy=(image.naturalHeight||image.height)/392,parts={};
    for(const name of Object.keys(TIGER_RIG)) {
      const canvas=rigCanvas(image),c=canvas.getContext('2d');c.drawImage(image,0,0);
      c.globalCompositeOperation='destination-in';rigPath(c,TIGER_RIG[name].polygon,sx,sy);c.fill();parts[name]=canvas;
    }
    const body=rigCanvas(image),c=body.getContext('2d');c.drawImage(image,0,0);
    c.globalCompositeOperation='destination-out';
    for(const name of Object.keys(TIGER_RIG)) {rigPath(c,TIGER_RIG[name].polygon,sx,sy);c.fill();c.lineWidth=.8*Math.max(sx,sy);c.stroke();}
    const hulls={};
    for(const name of ['frontNear','frontFar','rearNear','rearFar'])hulls[name]=photoHull(parts[name],sx,sy);
    for(const canvas of [body,...Object.values(parts)])flatten(canvas);
    return {image,body,parts,sx,sy,hulls,motions:{}};
  }


  function tigerMotion(action,rig) {
    if(rig&&rig.motions[action])return rig.motions[action];
    const variants={
      paw:{head:-.10,frontNear:-1.28},
      leap:{head:-.04,frontNear:-1.10,frontFar:-1.25,rearNear:1.95,rearFar:1.55,body:-.06,shift:-12,airborne:true},
      crouch:{head:.12,frontNear:-.70,frontFar:-.80,rearNear:1.65,rearFar:-.80},
      sit:{head:.14,tail:-.15,frontNear:.10,frontFar:-.05,rearNear:2.10,rearFar:-1.0,body:-.34,pivot:[170,275]},
      stretch:{head:.15,frontNear:-.95,frontFar:-1.0,rearNear:0,rearFar:-.05,body:.16},
      walk:{head:-.035,frontNear:-.45,frontFar:.30,rearNear:.45,rearFar:-.45},
      look_up:{head:-.48},
      look_down:{head:.48},
      rear:{head:.18,tail:-.20,frontNear:-1.10,frontFar:-1.35,rearNear:.30,rearFar:-.25,body:-.95,pivot:[170,275]},
      tail_up:{tail:.75},
      lie:{head:.20,tail:-.35,frontNear:-1.20,frontFar:-1.45,rearNear:2.20,rearFar:1.65,body:.02},
    };
    const m=Object.assign({head:0,tail:0,frontNear:0,frontFar:0,rearNear:0,rearFar:0,body:0,shift:0,pivot:[320,210]},variants[action]);
    if(action!=='neutral'&&!m.airborne) {
      let lowest=-Infinity;
      for(const name of ['frontNear','frontFar','rearNear','rearFar']) {
        const d=TIGER_RIG[name],points=rig&&rig.hulls[name]||[d.foot];
        for(const p of points) {
          const dx=p[0]-d.pivot[0],dy=p[1]-d.pivot[1];
          const x=d.pivot[0]+dx*Math.cos(m[name])-dy*Math.sin(m[name]);
          const y=d.pivot[1]+dx*Math.sin(m[name])+dy*Math.cos(m[name]);
          lowest=Math.max(lowest,m.pivot[1]+(x-m.pivot[0])*Math.sin(m.body)+(y-m.pivot[1])*Math.cos(m.body));
        }
      }
      m.shift=390-lowest;
    }
    if(rig)rig.motions[action]=m;
    return m;
  }

  function touchActorState(options,name) {
    return options && options.actors && options.actors[name] || {};
  }

  // The same fixed envelopes are used by paint, hit testing and the screw-travel
  // position conversion. Their extra room includes raised arms and rotated paws.
  function layout(width,height,options) {
    options=options||{};width=Number(width)||0;height=Number(height)||0;
    if(width<=0||height<=0)return {actors:{},track:{minX:12,maxX:12,baseline:0}};
    const pad=Math.min(22,height*.07);
    const stageScale=Math.max(.001,Math.min((height-2*pad)/402,width/620));
    let wu=stageScale*.8*384/640,tu=stageScale*.8*218/392;
    wu=Math.min(wu,Math.max(.001,(width-24)/426));
    tu=Math.min(tu,Math.max(.001,(width-24)/(TIGER_BOUNDS[2]-TIGER_BOUNDS[0])));
    const baseline=height-Math.max(27,12+(TIGER_BOUNDS[3]-392)*tu);
    wu=Math.min(wu,Math.max(.001,(baseline-12)/663));
    tu=Math.min(tu,Math.max(.001,(baseline-12)/(392-TIGER_BOUNDS[1])));
    function actor(name,unit,bounds,sourceHeight,fallback) {
      const state=touchActorState(options,name),position=clamp(Number.isFinite(state.position)?state.position:fallback,0,1);
      const actorWidth=(bounds[2]-bounds[0])*unit,actorHeight=(bounds[3]-bounds[1])*unit;
      const minCenterX=12+actorWidth/2,maxCenterX=Math.max(minCenterX,width-12-actorWidth/2);
      const centerX=minCenterX+(maxCenterX-minCenterX)*position;
      const originX=centerX-(bounds[0]+bounds[2])*.5*unit,originY=baseline-sourceHeight*unit;
      return {x:centerX-actorWidth/2,y:originY+bounds[1]*unit,width:actorWidth,height:actorHeight,
        centerX,position,minCenterX,maxCenterX,baseline,originX,originY,renderHeight:sourceHeight*unit,unit};
    }
    return {actors:{
      wusong:actor('wusong',wu,[-90,-23,336,640],640,.28),
      tiger:actor('tiger',tu,TIGER_BOUNDS,392,.72),
    },track:{minX:12,maxX:Math.max(12,width-12),baseline}};
  }

  function positionFromX(name,x,width,height,options) {
    const a=layout(width,height,options).actors[name];
    if(!a||!Number.isFinite(x))return .5;
    return a.maxCenterX>a.minCenterX?clamp((x-a.minCenterX)/(a.maxCenterX-a.minCenterX),0,1):.5;
  }

  const hitMasks = {wusong:null,tiger:null};
  const HIT_PADDING = 8;

  function actorHitMask(name,a,options) {
    const record=assetRecords[name];if(!record.ready)return null;
    const state=touchActorState(options,name);
    const pose=name==='wusong'?(state.pose||options.controlPose||TOUCH_POSES[state.action]||NEUTRAL):null;
    const resolved=pose?resolvedTouchPose(Object.assign({},options,{controlPose:pose})):null;
    const shape=resolved?['head','leftShoulder','rightShoulder','leftWrist','rightWrist','leftElbow','rightElbow'].map(key=>resolved[key]):state.action||'neutral';
    const key=a.unit.toFixed(6)+':'+(resolved?touchPoseAspect(options):1)+':'+(resolved&&resolved.hasShoulders?1:0)+':'+(state.poseSource==='standard'?state.action:'custom')+':'+JSON.stringify(shape);
    const cached=hitMasks[name];
    if(cached&&cached.key===key&&cached.image===record.image)return cached;
    const canvas=document.createElement('canvas');
    canvas.width=Math.ceil(a.width)+HIT_PADDING*2;canvas.height=Math.ceil(a.height)+HIT_PADDING*2;
    const c=canvas.getContext('2d',{willReadFrequently:true});if(!c)return null;
    // Render in frame-local CSS pixels. Translation/position is absent from the
    // cache key, so dragging never rasterizes or reads back the image again.
    c.translate(HIT_PADDING-a.x,HIT_PADDING-a.y);
    if(name==='tiger')touchTiger(c,a,state);
    else realPuppet(c,Object.assign({},options,{mode:'touch',controlPose:pose}),a);
    const pixels=c.getImageData(0,0,canvas.width,canvas.height).data;
    const alpha=new Uint8Array(canvas.width*canvas.height);
    for(let i=0;i<alpha.length;i++)alpha[i]=pixels[i*4+3];
    const mask={key,image:record.image,width:canvas.width,height:canvas.height,alpha};
    hitMasks[name]=mask;return mask;
  }

  function maskContains(mask,x,y,radius) {
    const px=Math.floor(x),py=Math.floor(y),r=Math.ceil(radius);
    for(let dy=-r;dy<=r;dy++)for(let dx=-r;dx<=r;dx++) {
      if(dx*dx+dy*dy>radius*radius)continue;
      const xx=px+dx,yy=py+dy;
      if(xx>=0&&yy>=0&&xx<mask.width&&yy<mask.height&&mask.alpha[yy*mask.width+xx]>=48)return true;
    }
    return false;
  }

  function hitTest(x,y,width,height,options) {
    if(!Number.isFinite(x)||!Number.isFinite(y))return null;
    ensureAssets();
    options=options||{};const scene=layout(width,height,options),selected=options.selectedActor;
    const order=selected==='tiger'?['tiger','wusong']:['wusong','tiger'];
    const candidates=[];
    for(const name of order) {
      const a=scene.actors[name];
      if(!a||x<a.x-8||x>a.x+a.width+8||y<a.y-8||y>a.y+a.height+8)continue;
      const mask=actorHitMask(name,a,options);
      if(mask)candidates.push({name,mask,x:x-a.x+HIT_PADDING,y:y-a.y+HIT_PADDING});
    }
    // A real pixel wins before any touch tolerance. A selected actor's nearby
    // edge cannot steal an opaque pixel belonging to the other actor.
    for(const radius of [0,7])for(const item of candidates)
      if(maskContains(item.mask,item.x,item.y,radius))return item.name;
    return null;
  }

  function touchTiger(c,placement,state) {
    const record=assetRecords.tiger;if(!record.ready)return;
    const image=record.image,action=state.action||'neutral';
    const scale=placement.renderHeight/(image.naturalHeight||image.height);
    c.save();c.translate(placement.originX+(image.naturalWidth||image.width)*scale,placement.originY);c.scale(-scale,scale);
    c.shadowColor=globalThis.ShadowBoardDisplay?'transparent':'rgba(65,43,18,.16)';c.shadowBlur=2;c.shadowOffsetX=1;c.shadowOffsetY=1;
    if(action==='neutral'||!TIGER_ACTIONS.includes(action)) {c.drawImage(image,0,0);c.restore();return;}
    if(!tigerRig||tigerRig.image!==image)tigerRig=prepareTigerRig(image);
    const rig=tigerRig,m=tigerMotion(action,tigerRig),sx=rig.sx,sy=rig.sy;
    c.translate(0,m.shift*sy);c.translate(m.pivot[0]*sx,m.pivot[1]*sy);c.rotate(m.body);c.translate(-m.pivot[0]*sx,-m.pivot[1]*sy);
    function part(name) {
      const p=TIGER_RIG[name].pivot;c.save();c.translate(p[0]*sx,p[1]*sy);c.rotate(m[name]);
      c.drawImage(rig.parts[name],-p[0]*sx,-p[1]*sy);c.restore();
    }
    part('tail');part('rearFar');part('frontFar');c.drawImage(rig.body,0,0);
    part('rearNear');part('head');part('frontNear');
    // Tiny original-photo caps hide the rotating paper joints, preserving stripes.
    for(const name of ['tail','rearNear','frontNear','head']) {
      const p=TIGER_RIG[name].pivot,r=name==='head'?13:10;c.save();c.beginPath();c.ellipse(p[0]*sx,p[1]*sy,r*sx,r*sy,0,0,TAU);c.clip();c.drawImage(image,0,0);c.restore();
    }
    c.restore();
  }

  function selectedMark(c,name,a) {
    const center=a.originX+(name==='wusong'?107:308)*a.unit;
    const radius=Math.min(36,Math.max(21,a.width*.18));
    c.save();c.strokeStyle='rgba(88,107,85,.75)';c.lineWidth=1.1;
    c.beginPath();c.ellipse(center,a.baseline+3,radius,4.5,0,0,Math.PI);c.stroke();
    c.fillStyle='#626d54';c.font='12px "ShadowInk", "KaiTi", serif';c.textAlign='center';c.textBaseline='top';
    c.fillText(name==='wusong'?'武松':'老虎',center,a.baseline+9);c.restore();
  }

  function drawTouch(c,width,height,options) {
    const scene=layout(width,height,options),selected=options.selectedActor;
    const order=selected==='tiger'?['wusong','tiger']:['tiger','wusong'];
    for(const name of order) {
      const a=scene.actors[name],state=touchActorState(options,name);
      if(name==='tiger')touchTiger(c,a,state);
      else {
        const pose=state.pose||options.controlPose||TOUCH_POSES[state.action]||NEUTRAL;
        realPuppet(c,Object.assign({},options,{controlPose:pose}),a);
      }
    }
    if(scene.actors[selected])selectedMark(c,selected,scene.actors[selected]);
  }

  function controlRods(c, options) {
    const p = motionFor(options), scale = 384 / 640, x = 335.4, y = 98+p.bounce;
    const left = rotatedWrist('left',p.left), right = rotatedWrist('right',p.right);
    c.save(); c.globalAlpha *= .14;
    path(c, q => {
      q.moveTo(x+65,299); q.lineTo(x+65,532);
      q.moveTo(x+left[0]*scale,y+left[1]*scale); q.lineTo(x+left[0]*scale-26,532);
      q.moveTo(x+right[0]*scale,y+right[1]*scale); q.lineTo(x+right[0]*scale+26,532);
    }, null, C.ink, 1);
    c.restore();
  }

  function draw(ctx, width, height, options) {
    options = options || {};
    if (!ctx || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return;
    ensureAssets();
    const mode = options.mode || 'home';
    ctx.save(); ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#e5c28a'; ctx.fillRect(0, 0, width, height);
    if (mode === 'touch') {
      ctx.save(); ctx.scale(width / 896, height / 446); ctx.translate(-52, -52);
      backdrop(ctx); ctx.restore();
      drawTouch(ctx,width,height,options);
      ctx.restore(); return;
    }
    if (mode === 'home') {
      const scale = Math.min(width / 1000, height / 550);
      ctx.translate((width - 1000 * scale) / 2, (height - 550 * scale) / 2); ctx.scale(scale, scale);
      backdrop(ctx);
    } else {
      ctx.save(); ctx.scale(width / 896, height / 446); ctx.translate(-52, -52);
      backdrop(ctx); ctx.restore();
      const pad = Math.min(22, height * .07);
      const scale = Math.min((height - pad * 2) / 402, width / 620);
      ctx.translate(width / 2 - 500 * scale, height - pad - 482 * scale); ctx.scale(scale, scale);
    }
    realTiger(ctx, mode, options.time);
    realPuppet(ctx, options);
    if (options.guide) controlRods(ctx, options);
    ctx.restore();
  }

  function isReady() {
    ensureAssets();
    return assetRecords.wusong.ready && assetRecords.tiger.ready && (!assetRecords.flag.source||assetRecords.flag.ready);
  }
  // These ten presentation poses are independent of handwriting proportions.
  // Forward gestures face the tiger on the right of the stage.
  function standardPose(action) {
    const definition=globalThis.ShadowActionCatalog?.actions?.find(item=>item.id===action);
    if(definition){const keys=['head','leftShoulder','rightShoulder','leftElbow','rightElbow','leftWrist','rightWrist'];return Object.fromEntries(keys.map(key=>[key,definition.pose[key].slice()]));}
    const forward={
      open:{head:[.5,.17],leftElbow:[.20,.32],leftWrist:[.055,.32],rightElbow:[.80,.32],rightWrist:[.945,.32]},
      strike:{head:[.5,.17],leftElbow:[.23,.48],leftWrist:[.43,.38],rightElbow:[.80,.34],rightWrist:[.955,.34]},
      salute:{head:[.5,.17],leftElbow:[.25,.50],leftWrist:[.57,.38],rightElbow:[.80,.52],rightWrist:[.72,.35]},
      point:{head:[.5,.17],leftElbow:[.29,.49],leftWrist:[.22,.68],rightElbow:[.80,.34],rightWrist:[.955,.34]}
    };
    const allowed=['neutral','open','raise','strike','left_raise','right_raise','guard','akimbo','salute','point'];
    const pose=allowed.includes(action)?forward[action]||TOUCH_POSES[action]:TOUCH_POSES.neutral;
    return Object.fromEntries(Object.entries({leftShoulder:[.34,.32],rightShoulder:[.66,.32],...pose}).map(([key,point])=>[key,point.slice()]));
  }
  window.ShadowStageArt = { draw: draw, layout: layout, standardPose: standardPose, hitTest: hitTest, positionFromX: positionFromX, isReady: isReady, get ready() { return isReady(); } };
})();
