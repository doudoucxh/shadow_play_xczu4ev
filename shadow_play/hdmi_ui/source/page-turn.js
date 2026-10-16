/* A restrained two-leaf turn through an aged diary. */
(function () {
  'use strict';
  const W = 1000;
  const H = 550;
  const STRIPS = 40;
  const CLOSE_STRIPS = 24;
  const LEAVES = 2;
  const FLIP_END = 730;
  const READING_TIME = 600;
  const EXIT_TIME = 420;
  const DURATION = FLIP_END + READING_TIME + EXIT_TIME;
  const CLOSE_DURATION = 1080;
  const HINGE = 140;
  const LEFT_WIDTH = 120;
  const PAGE_WIDTH = 840;
  const PAGE_TOP = 45;
  const PAGE_HEIGHT = 460;
  const LEAF_STARTS = [0, 75];
  const LEAF_DURATIONS = [650, 655];
  const PI = Math.PI;
  const clamp = function (v) { return Math.max(0, Math.min(1, v)); };
  const smooth = function (v) { v = clamp(v); return v * v * (3 - 2 * v); };

  function paperTexture(doc, back) {
    const canvas = doc.createElement('canvas'); canvas.width = W; canvas.height = H;
    const c = canvas.getContext('2d');
    const fill = c.createLinearGradient(0, 0, W, H);
    fill.addColorStop(0, back ? '#cab99b' : '#c3af8d');
    fill.addColorStop(.2, back ? '#e4d6ba' : '#deceb0');
    fill.addColorStop(.62, back ? '#eee3cc' : '#e9dcc2');
    fill.addColorStop(1, '#baa07d');
    c.fillStyle = fill; c.fillRect(0, 0, W, H);
    let seed = back ? 3177 : 19079;
    const random = function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    for (let i = 0; i < 2200; i++) {
      const x = random() * W, y = random() * H;
      c.strokeStyle = i % 3 ? 'rgba(101,71,36,.065)' : 'rgba(255,250,221,.3)';
      c.lineWidth = .35 + random() * .35;
      c.beginPath(); c.moveTo(x, y); c.lineTo(x + 3 + random() * 17, y + (random() - .5) * 2); c.stroke();
    }
    for (let i = 0; i < 34; i++) {
      const x = random() * W, y = random() * H, r = 8 + random() * 53;
      const stain = c.createRadialGradient(x, y, 0, x, y, r);
      stain.addColorStop(0, 'rgba(119,67,27,' + (.025 + random() * .035) + ')');
      stain.addColorStop(.67, 'rgba(129,79,30,.035)'); stain.addColorStop(1, 'rgba(129,79,30,0)');
      c.fillStyle = stain; c.fillRect(x - r, y - r, r * 2, r * 2);
    }
    for (let i = 0; i < 450; i++) {
      const x = random() * W, y = random() * H;
      c.fillStyle = 'rgba(106,65,26,' + (.03 + random() * .13) + ')';
      c.fillRect(x, y, .3 + random() * 1.4, .3 + random() * 1.1);
    }
    const edge = c.createLinearGradient(0, 0, W, 0);
    edge.addColorStop(0, 'rgba(66,38,17,.35)'); edge.addColorStop(.025, 'rgba(108,66,27,.12)');
    edge.addColorStop(.12, 'rgba(108,66,27,0)'); edge.addColorStop(.9, 'rgba(108,66,27,0)');
    edge.addColorStop(.985, 'rgba(111,64,24,.12)'); edge.addColorStop(1, 'rgba(63,35,15,.35)');
    c.fillStyle = edge; c.fillRect(0, 0, W, H);
    const ends = c.createLinearGradient(0, 0, 0, H);
    ends.addColorStop(0, 'rgba(74,42,18,.33)'); ends.addColorStop(.035, 'rgba(123,76,30,.05)');
    ends.addColorStop(.12, 'rgba(123,76,30,0)'); ends.addColorStop(.88, 'rgba(123,76,30,0)');
    ends.addColorStop(.98, 'rgba(101,56,21,.09)'); ends.addColorStop(1, 'rgba(68,37,15,.32)');
    c.fillStyle = ends; c.fillRect(0, 0, W, H);
    c.strokeStyle = 'rgba(89,52,22,.3)'; c.lineWidth = .7;
    for (let i = 0; i < 140; i++) {
      const x = random() * W;
      c.beginPath(); c.moveTo(x, 0); c.lineTo(x + random() * 2, 1 + random() * 6);
      c.moveTo(x, H); c.lineTo(x - random() * 2, H - 1 - random() * 6); c.stroke();
    }
    return canvas;
  }

  function polygon(c, p) {
    c.beginPath(); c.moveTo(p[0].x, p[0].y);
    for (let i = 1; i < p.length; i++) c.lineTo(p[i].x, p[i].y);
    c.closePath();
  }

  function create(options) {
    options = options || {};
    const canvas = options.canvas;
    if (!canvas || typeof canvas.getContext !== 'function') throw new TypeError('ShadowPageTurn.create needs a canvas.');
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return { play: function (o) { if (o && o.onComplete) o.onComplete(); }, finish: function () {}, destroy: function () {} };
    const doc = canvas.ownerDocument || document, win = doc.defaultView || window;
    const parent = canvas.parentElement || canvas;
    const sizeHost = parent.closest('.shadow-app') || parent;
    const reduced = Boolean(options.reducedMotion);
    const frontBase = paperTexture(doc, false), backBase = paperTexture(doc, true);
    const titleLayer = doc.createElement('canvas');
    titleLayer.width = PAGE_WIDTH; titleLayer.height = PAGE_HEIGHT;
    const titleCtx = titleLayer.getContext('2d');
    const bookBase = doc.createElement('canvas');
    bookBase.width = W; bookBase.height = H;
    const destinationBook = doc.createElement('canvas');
    destinationBook.width = W; destinationBook.height = H;
    const cover = doc.createElement('canvas');cover.width = PAGE_WIDTH;cover.height = PAGE_HEIGHT;
    let coverImage=cover;
    const coverCtx = cover.getContext('2d');
    const leather = coverCtx.createLinearGradient(0,0,PAGE_WIDTH,PAGE_HEIGHT);
    leather.addColorStop(0,'#493522');leather.addColorStop(.45,'#302116');leather.addColorStop(1,'#211810');
    coverCtx.fillStyle=leather;coverCtx.fillRect(0,0,PAGE_WIDTH,PAGE_HEIGHT);
    for(let i=0;i<1600;i++){
      const x=(i*317%839),y=(i*173%459);
      coverCtx.fillStyle=i%3?'rgba(208,168,97,.035)':'rgba(0,0,0,.09)';
      coverCtx.fillRect(x,y,1+(i%7),.5+(i%3)*.2);
    }
    for(const inset of [12,19,27]){coverCtx.strokeStyle=inset===19?'#b3965d':'#6d5430';coverCtx.lineWidth=inset===19?1.6:.7;coverCtx.strokeRect(inset,inset,PAGE_WIDTH-inset*2,PAGE_HEIGHT-inset*2);}
    for(const [x,y,sx,sy] of [[27,27,1,1],[PAGE_WIDTH-27,27,-1,1],[27,PAGE_HEIGHT-27,1,-1],[PAGE_WIDTH-27,PAGE_HEIGHT-27,-1,-1]]){
      coverCtx.strokeStyle='#c2a66c';coverCtx.lineWidth=3;coverCtx.beginPath();coverCtx.moveTo(x,y+sy*25);coverCtx.lineTo(x,y);coverCtx.lineTo(x+sx*25,y);coverCtx.stroke();
    }
    if(typeof win.createImageBitmap==='function')win.createImageBitmap(cover).then(function(bitmap){if(destroyed)bitmap.close();else coverImage=bitmap;}).catch(function(){});
    const burn = win.ShadowPaperBurn?.create({document:doc,width:W,height:H,pageTop:PAGE_TOP,pageHeight:PAGE_HEIGHT,hinge:HINGE,pageWidth:PAGE_WIDTH});
    canvas.style.pointerEvents = 'none'; canvas.style.width = '100%'; canvas.style.height = '100%';
    canvas.setAttribute('aria-hidden', 'true');
    canvas.dataset.turnProgress = '0'; canvas.dataset.turnState = 'idle';
    canvas.dataset.visibleLeaves = '0';
    canvas.dataset.movingLeaves = '0';
    canvas.dataset.flipProgress = '0';
    canvas.dataset.titleFaces = '0';
    canvas.dataset.titleReadable = 'false';
    canvas.dataset.turnPhase = 'idle';
    canvas.dataset.revealProgress = '0';
    canvas.dataset.turnDirection = 'open';
    let width = 1, height = 1, ratio = 1, raf = 0, current = null, destroyed = false;
    let preparedKey = '';
    if (doc.fonts) doc.fonts.load('112px "ShadowBrush"','经典表演笔墨成戏以身入戏').then(function () {
      preparedKey = '';
      if (current?.direction==='open') { prepare(current.title, current.subtitle); render(current.progress); }
    }).catch(function () {});

    function clear() {
      canvas.style.opacity='';
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.restore();
    }

    function measure() {
      if (destroyed) return;
      const rect = sizeHost.getBoundingClientRect();
      if(rect.width<2||rect.height<2)return;
      const w = rect.width, h = rect.height, r = 1;
      if (w === width && h === height && r === ratio) return;
      width = w; height = h; ratio = r;
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      if(current)current.settledFrame=false;
      if (current) render(current.progress);
    }

    function prepare(title, subtitle) {
      const key = String(title || '光影入戏') + '\u0000' + String(subtitle || '');
      if (preparedKey === key) return;
      preparedKey = key;
      const c = titleCtx;
      c.clearRect(0, 0, PAGE_WIDTH, PAGE_HEIGHT);
      c.textAlign = 'center'; c.textBaseline = 'middle';
      const text = String(title || '光影入戏');
      c.font = Math.min(112, 660 / Math.max(4, text.length)) + 'px "ShadowBrush","STKaiti","KaiTi",serif';
      c.lineWidth = .65; c.strokeStyle = 'rgba(34,22,11,.18)';
      c.strokeText(text, PAGE_WIDTH * .5, PAGE_HEIGHT * .5);
      c.fillStyle = '#20150d'; c.fillText(text, PAGE_WIDTH * .5, PAGE_HEIGHT * .5);
      // Sparse dry-brush fibres are cut into the cached ink, never the paper.
      let inkSeed = Array.from(text).reduce(function (n, ch) { return n + ch.charCodeAt(0); }, 107);
      const inkRandom = function () { inkSeed = (inkSeed * 16807) % 2147483647; return inkSeed / 2147483647; };
      c.save(); c.globalCompositeOperation = 'destination-out'; c.fillStyle = 'rgba(0,0,0,.2)';
      for (let i = 0; i < 110; i++) {
        c.fillRect(PAGE_WIDTH * .2 + inkRandom() * PAGE_WIDTH * .6, PAGE_HEIGHT * .35 + inkRandom() * PAGE_HEIGHT * .3, 2 + inkRandom() * 6, .3 + inkRandom() * .5);
      }
      c.restore();
      if (subtitle) {
        c.font = '23px "STKaiti","KaiTi","Kaiti SC",serif';
        c.fillStyle = '#684621'; c.fillText(String(subtitle), PAGE_WIDTH * .5, PAGE_HEIGHT * .69, 380);
      }
      const destination = destinationBook.getContext('2d');
      destination.clearRect(0, 0, W, H); destination.drawImage(bookBase, 0, 0);
      destination.drawImage(titleLayer, HINGE, PAGE_TOP, PAGE_WIDTH, PAGE_HEIGHT);
    }

    function geometry(progress, leaf, strips) {
      const angle = PI * smooth(progress);
      const envelope = Math.sin(PI * progress);
      const leafPhase = leaf * .61;
      // Tangent rotation travels outward. The spine leads; the middle and free
      // edge follow later. Separate top/bottom fields give diagonal tension.
      function tangent(u, edge) {
        const delay = .25 * smooth(u);
        const phase = clamp(progress + (.09 - delay + edge * .026 * u) * envelope);
        const wave = .20 * envelope * Math.sin(PI * 2 * u - progress * 5.2 + leafPhase) * Math.sin(PI * u);
        const corner = envelope * Math.pow(u, 4) * (edge < 0 ? .43 : -.31) * (1 + .11 * Math.sin(leafPhase));
        const landing = clamp((progress - .75) / .25);
        const rebound = .13 * Math.sin(landing * PI * 2) * Math.sin(landing * PI) * u * u;
        return PI * smooth(phase) + wave + corner + rebound;
      }
      const points = [], quads = [];
      let xTop = 0, zTop = 0, xBottom = 0, zBottom = 0;
      for (let i = 0; i <= strips; i++) {
        const u = i / strips;
        if (i) {
          const mid = (i - .5) / strips, step = PAGE_WIDTH / strips;
          const at = tangent(mid, -1), ab = tangent(mid, 1);
          xTop += Math.cos(at) * step; zTop += Math.sin(at) * step;
          xBottom += Math.cos(ab) * step; zBottom += Math.sin(ab) * step;
        }
        const topPerspective = 4600 / (4600 - zTop), bottomPerspective = 4600 / (4600 - zBottom);
        const topLift = envelope * (-18 * u * u + 17 * Math.sin(PI * 1.6 * u + leafPhase) * Math.sin(PI * u));
        const bottomLift = envelope * (10 * u * u + 12 * Math.sin(PI * 1.4 * u - leafPhase) * Math.sin(PI * u));
        const tt = tangent(u, -1), tb = tangent(u, 1);
        points.push({
          top: { x: HINGE + xTop * topPerspective, y: H / 2 + (-PAGE_HEIGHT / 2 + topLift) * topPerspective },
          bottom: { x: HINGE + xBottom * bottomPerspective, y: H / 2 + (PAGE_HEIGHT / 2 + bottomLift) * bottomPerspective },
          z: (zTop + zBottom) / 2, theta: (tt + tb) / 2, thetaTop: tt, thetaBottom: tb,
        });
      }
      for (let i = 0; i < strips; i++) {
        const a = points[i], b = points[i + 1];
        const theta = (a.theta + b.theta) / 2;
        quads.push({ index: i, z: (a.z + b.z) / 2, theta: theta, back: Math.cos(theta) < 0,
          leftTheta: a.theta, rightTheta: b.theta, curvature: (b.theta - a.theta) * strips,
          points: [a.top, b.top, b.bottom, a.bottom] });
      }
      quads.sort(function (a, b) { return a.z - b.z; });
      return { points: points, quads: quads, angle: angle, strips: strips,
        maxX: Math.max.apply(null, points.map(function (p) { return Math.max(p.top.x, p.bottom.x); })) };
    }

    function outline(points) {
      return points.map(function (p) { return p.top; }).concat(points.slice().reverse().map(function (p) { return p.bottom; }));
    }

    function drawLeafShadow(surface, progress) {
      ctx.save(); ctx.translate(3 + Math.sin(surface.angle) * 4, 4); polygon(ctx, outline(surface.points));
      ctx.fillStyle = 'rgba(63,34,13,' + (.12 + Math.sin(PI * progress) * .08) + ')'; ctx.fill(); ctx.restore();
    }

    function prepareBookBase() {
      const ctx = bookBase.getContext('2d');
      const dark = ctx.createLinearGradient(0, 0, 0, H);
      dark.addColorStop(0, '#302318'); dark.addColorStop(1, '#1f1710');
      ctx.fillStyle = dark; ctx.fillRect(0, 0, W, H);
      // Both halves remain attached to the same spine throughout the riffle.
      ctx.fillStyle = '#654326'; ctx.fillRect(15, PAGE_TOP + 3, 970, PAGE_HEIGHT + 29);
      for (let i = 24; i >= 0; i--) {
        ctx.strokeStyle = i % 2 ? '#b8965f' : '#e4c894'; ctx.lineWidth = 1;
        const y = PAGE_TOP + PAGE_HEIGHT + i * .82 + Math.sin(i * 1.7) * .6;
        ctx.beginPath(); ctx.moveTo(19 + (i * 7 % 5) - 2, y);
        ctx.quadraticCurveTo(20 + LEFT_WIDTH / 2, y - 1.4, HINGE, y + 5.5);
        ctx.quadraticCurveTo(HINGE + PAGE_WIDTH / 2, y - .7, 981 + (i * 11 % 7) - 3, y + Math.sin(i * .8)); ctx.stroke();
      }
      ctx.drawImage(backBase, HINGE - LEFT_WIDTH, PAGE_TOP, LEFT_WIDTH, PAGE_HEIGHT);
      ctx.drawImage(frontBase, HINGE, PAGE_TOP, PAGE_WIDTH, PAGE_HEIGHT);
      const spine = ctx.createLinearGradient(HINGE - 23, 0, HINGE + 23, 0);
      spine.addColorStop(0, 'rgba(81,46,17,0)'); spine.addColorStop(.43, 'rgba(85,47,16,.22)');
      spine.addColorStop(.5, 'rgba(64,34,12,.48)'); spine.addColorStop(.57, 'rgba(85,47,16,.22)'); spine.addColorStop(1, 'rgba(81,46,17,0)');
      ctx.fillStyle = spine; ctx.fillRect(HINGE - 23, PAGE_TOP, 46, PAGE_HEIGHT);
      ctx.strokeStyle = 'rgba(83,47,19,.45)'; ctx.lineWidth = .8;
      ctx.beginPath(); ctx.moveTo(HINGE, PAGE_TOP); ctx.lineTo(HINGE, PAGE_TOP + PAGE_HEIGHT); ctx.stroke();
    }

    function drawSimpleLeaf(surface, leaf) {
      function paperLight(theta, curvature) {
        const facing = Math.abs(Math.cos(theta));
        const ridge = .105 * Math.exp(-Math.pow((theta - (Math.cos(theta) < 0 ? 2.12 : 1.02)) / .23, 2));
        const light = .65 + .27 * facing + .035 * Math.cos(theta - .5) + ridge - .045 * Math.min(1, Math.abs(curvature) * .2);
        const tint = leaf % 3 - 1;
        return 'rgb(' + Math.round((234 + tint) * light) + ',' + Math.round((220 + tint) * light) + ',' + Math.round((193 + tint) * light) + ')';
      }
      surface.quads.forEach(function (quad) {
        const p = quad.points.map(function (v) { return { x: v.x, y: v.y }; });
        const left = { x: (p[0].x + p[3].x) / 2, y: (p[0].y + p[3].y) / 2 };
        const right = { x: (p[1].x + p[2].x) / 2, y: (p[1].y + p[2].y) / 2 };
        if (Math.hypot(right.x - left.x, right.y - left.y) < .15) return;
        const direction = right.x >= left.x ? 1 : -1;
        p[0].x -= direction * .35; p[3].x -= direction * .35;
        p[1].x += direction * .35; p[2].x += direction * .35;
        const g = ctx.createLinearGradient(left.x, left.y, right.x, right.y);
        g.addColorStop(0, paperLight(quad.leftTheta, quad.curvature));
        g.addColorStop(1, paperLight(quad.rightTheta, quad.curvature));
        polygon(ctx, p); ctx.fillStyle = g; ctx.fill();
      });
      // Shared age marks stay subtle; lighting above follows the moving bend.
      const grainOutline = outline(surface.points);
      const grainLeft = Math.min.apply(null, grainOutline.map(function (p) { return p.x; }));
      const grainRight = Math.max.apply(null, grainOutline.map(function (p) { return p.x; }));
      const grainTop = Math.min.apply(null, grainOutline.map(function (p) { return p.y; }));
      const grainBottom = Math.max.apply(null, grainOutline.map(function (p) { return p.y; }));
      ctx.save(); polygon(ctx, grainOutline); ctx.clip();
      ctx.globalAlpha *= .095;
      ctx.drawImage(frontBase, grainLeft, grainTop, Math.max(.1, grainRight - grainLeft), Math.max(.1, grainBottom - grainTop));
      ctx.restore();
    }

    function cornerCurl(surface, progress, leaf) {
      const phase = clamp((progress - (.075 + .012 * Math.sin(leaf * .93))) / (.86 + .018 * Math.cos(leaf * 1.17)));
      const amount = Math.sin(PI * phase) * (.48 + .10 * (.5 + .5 * Math.sin(leaf * 1.71)));
      if (amount < .025) return null;
      const u = 1 - .108 * amount;
      const at = u * surface.strips, index = Math.floor(at), mix = at - index;
      const p = surface.points[index], q = surface.points[Math.min(index + 1, surface.strips)];
      const end = surface.points[surface.strips];
      const a = { x: p.top.x + (q.top.x - p.top.x) * mix, y: p.top.y + (q.top.y - p.top.y) * mix };
      const c = end.top;
      const b = { x: c.x + (end.bottom.x - c.x) * .12 * amount, y: c.y + (end.bottom.y - c.y) * .12 * amount };
      const dx = b.x - a.x, dy = b.y - a.y, length2 = dx * dx + dy * dy;
      if (length2 < 9) return null;
      const t = ((c.x - a.x) * dx + (c.y - a.y) * dy) / length2;
      const foot = { x: a.x + dx * t, y: a.y + dy * t };
      const distance = Math.hypot(foot.x - c.x, foot.y - c.y);
      if (distance < 1.1) return null;
      const inward = { x: (foot.x - c.x) / distance, y: (foot.y - c.y) / distance };
      const returned = .4 + .15 * (.5 + .5 * Math.sin(leaf * 1.3 + progress * 1.7));
      const r = { x: foot.x + inward.x * distance * returned,
        y: foot.y + inward.y * distance * returned - amount * (2.6 + leaf % 3) };
      return { a: a, b: b, c: c, r: r, foot: foot, inward: inward, distance: distance,
        u: u, amount: amount, bulge: Math.min(10, distance * .35) };
    }

    function clipCornerBody(curl) {
      const outside = { x: curl.c.x + (curl.c.x - curl.foot.x) * 2,
        y: curl.c.y + (curl.c.y - curl.foot.y) * 2 };
      ctx.beginPath(); ctx.rect(-W * 2, -H * 2, W * 5, H * 5);
      ctx.moveTo(curl.a.x, curl.a.y); ctx.lineTo(outside.x, outside.y); ctx.lineTo(curl.b.x, curl.b.y); ctx.closePath();
      ctx.clip('evenodd');
    }

    function curlLipPath(curl) {
      const a = curl.a, b = curl.b, r = curl.r, n = curl.inward, bulge = curl.bulge;
      ctx.beginPath(); ctx.moveTo(a.x, a.y);
      ctx.quadraticCurveTo((a.x + r.x) / 2 + n.x * bulge, (a.y + r.y) / 2 + n.y * bulge, r.x, r.y);
      ctx.quadraticCurveTo((b.x + r.x) / 2 + n.x * bulge * .6, (b.y + r.y) / 2 + n.y * bulge * .6, b.x, b.y);
      ctx.quadraticCurveTo((a.x + b.x) / 2 - n.x * bulge * .35, (a.y + b.y) / 2 - n.y * bulge * .35, a.x, a.y);
      ctx.closePath();
    }

    function drawCornerLip(curl) {
      const a = curl.a, b = curl.b, r = curl.r, n = curl.inward;
      ctx.save();
      // A tiny shadow lies directly under the returned corner, not across a page.
      ctx.beginPath(); ctx.moveTo(a.x, a.y);
      ctx.quadraticCurveTo((a.x + b.x) / 2 + n.x * 2, (a.y + b.y) / 2 + n.y * 2, b.x, b.y);
      ctx.strokeStyle = 'rgba(65,37,15,.3)'; ctx.lineWidth = 3.2; ctx.stroke();
      const g = ctx.createLinearGradient(curl.foot.x - n.x * 2, curl.foot.y - n.y * 2, r.x, r.y);
      g.addColorStop(0, '#9d7a43'); g.addColorStop(.19, '#e0c491');
      g.addColorStop(.48, '#f3dfb4'); g.addColorStop(.77, '#e8cfa1'); g.addColorStop(1, '#c6a371');
      curlLipPath(curl); ctx.fillStyle = g;
      ctx.fill();
      ctx.strokeStyle = 'rgba(101,66,28,.46)'; ctx.lineWidth = .55; ctx.stroke();
      ctx.beginPath(); ctx.moveTo(a.x, a.y);
      ctx.quadraticCurveTo((a.x + r.x) / 2 + n.x * curl.bulge, (a.y + r.y) / 2 + n.y * curl.bulge, r.x, r.y);
      ctx.strokeStyle = 'rgba(255,239,203,.86)'; ctx.lineWidth = .65; ctx.stroke();
      ctx.restore();
    }

    function drawLeafEdges(surface, progress, curl) {
      // The visible cut edges stay thin; they do not turn into a cardboard rim.
      if (progress > .015) {
        ctx.strokeStyle = 'rgba(91,55,25,.46)'; ctx.lineWidth = .55; ctx.lineJoin = 'round';
        ['top', 'bottom'].forEach(function (edge) {
          ctx.beginPath();
          surface.points.forEach(function (p, i) {
            if (edge === 'top' && curl && i > curl.u * surface.strips) return;
            if (!i) ctx.moveTo(p[edge].x, p[edge].y); else ctx.lineTo(p[edge].x, p[edge].y);
          });
          if (edge === 'top' && curl) ctx.lineTo(curl.a.x, curl.a.y);
          ctx.stroke();
        });
        const end = surface.points[surface.strips];
        const edgeStart = curl ? curl.b : end.top;
        ctx.beginPath(); ctx.moveTo(edgeStart.x, edgeStart.y); ctx.lineTo(end.bottom.x, end.bottom.y);
        ctx.strokeStyle = '#f1d9a8'; ctx.lineWidth = .8; ctx.stroke();
      }
    }

    function peelShape(progress) {
      const motion = smooth(progress);
      const swell = Math.sin(PI * progress);
      return { x: W + 100 - (W + 260) * motion, arch: 42 * swell, tilt: 12 * swell,
        width: 88 * Math.pow(Math.max(0, swell), .7), strength: swell };
    }

    function peelEdge(shape, y) {
      const t = clamp((y + 60) / (H + 120)), s = 1 - t;
      return shape.x + s * s * s * -shape.tilt / 2 + 3 * s * s * t * shape.arch +
        3 * s * t * t * shape.arch * .7 + t * t * t * shape.tilt / 2;
    }

    function clipPeelingPaper(shape) {
      ctx.beginPath(); ctx.moveTo(-W, -60); ctx.lineTo(peelEdge(shape, -60), -60);
      ctx.bezierCurveTo(shape.x + shape.arch, -60 + (H + 120) / 3, shape.x + shape.arch * .7, -60 + (H + 120) * 2 / 3,
        peelEdge(shape, H + 60), H + 60);
      ctx.lineTo(-W, H + 60); ctx.closePath(); ctx.clip();
    }

    function drawPeelingEdge(shape) {
      if (shape.width < .2 || shape.x < -130) return;
      const top = PAGE_TOP - 6, bottom = PAGE_TOP + PAGE_HEIGHT + 12;
      const samples = 28;
      function band(inner, outer) {
        ctx.beginPath();
        for (let i = 0; i <= samples; i++) {
          const y = top + (bottom - top) * i / samples, x = peelEdge(shape, y) + outer;
          if (!i) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        for (let i = samples; i >= 0; i--) {
          const y = top + (bottom - top) * i / samples;
          ctx.lineTo(peelEdge(shape, y) + inner, y);
        }
        ctx.closePath();
      }
      ctx.save();
      const x = peelEdge(shape, H / 2);
      band(0, 28 * shape.strength);
      const shadow = ctx.createLinearGradient(x - 3, 0, x + 29, 0);
      shadow.addColorStop(0, 'rgba(30,18,8,.28)'); shadow.addColorStop(1, 'rgba(30,18,8,0)');
      ctx.fillStyle = shadow; ctx.fill();
      band(-shape.width, 0);
      const backLight = ctx.createLinearGradient(x - shape.width, 0, x, 0);
      backLight.addColorStop(0, '#9a8060'); backLight.addColorStop(.2, '#d1bfa0');
      backLight.addColorStop(.52, '#f1e4c9'); backLight.addColorStop(.82, '#e4d1aa'); backLight.addColorStop(1, '#a88a63');
      ctx.fillStyle = backLight; ctx.fill();
      ctx.save(); ctx.clip(); ctx.globalAlpha = .12;
      ctx.drawImage(backBase, shape.x - shape.width - 30, top, shape.width + shape.arch + 55, bottom - top);
      ctx.restore();
      ctx.beginPath();
      for (let i = 0; i <= samples; i++) {
        const y = top + (bottom - top) * i / samples;
        if (!i) ctx.moveTo(peelEdge(shape, y), y); else ctx.lineTo(peelEdge(shape, y), y);
      }
      ctx.strokeStyle = 'rgba(255,239,205,.8)'; ctx.lineWidth = .9; ctx.stroke();
      ctx.restore();
    }

    function texturedTriangle(texture,source,target) {
      const [s0,s1,s2]=source,[d0,d1,d2]=target;
      const a=s1.x-s0.x,b=s1.y-s0.y,c=s2.x-s0.x,d=s2.y-s0.y,det=a*d-b*c;
      if(Math.abs(det)<.0001)return;
      const ux=d1.x-d0.x,uy=d1.y-d0.y,vx=d2.x-d0.x,vy=d2.y-d0.y;
      const m0=(ux*d-vx*b)/det,m1=(uy*d-vy*b)/det,m2=(vx*a-ux*c)/det,m3=(vy*a-uy*c)/det;
      const center={x:(d0.x+d1.x+d2.x)/3,y:(d0.y+d1.y+d2.y)/3};
      const clip=target.map(p=>{const d=Math.hypot(p.x-center.x,p.y-center.y)||1;return{x:p.x+(p.x-center.x)/d*.8,y:p.y+(p.y-center.y)/d*.8};});
      // Only submit the narrow source strip. Drawing the entire leather bitmap
      // through every triangle makes the compositor rasterize it 80 times.
      const sx=Math.max(0,Math.min(s0.x,s1.x,s2.x)-1),sy=Math.max(0,Math.min(s0.y,s1.y,s2.y)-1);
      const sw=Math.min(texture.width,Math.max(s0.x,s1.x,s2.x)+1)-sx;
      const sh=Math.min(texture.height,Math.max(s0.y,s1.y,s2.y)+1)-sy;
      ctx.save();polygon(ctx,clip);ctx.clip();ctx.transform(m0,m1,m2,m3,d0.x-m0*s0.x-m2*s0.y,d0.y-m1*s0.x-m3*s0.y);ctx.drawImage(texture,sx,sy,sw,sh,sx,sy,sw,sh);ctx.restore();
    }

    function drawClosingCover(surface) {
      drawLeafShadow(surface,.5);
      polygon(ctx,outline(surface.points));ctx.fillStyle='#302116';ctx.fill();
      for(const quad of surface.quads){
        const x0=quad.index/surface.strips*PAGE_WIDTH,x1=(quad.index+1)/surface.strips*PAGE_WIDTH;
        const [a,b,c,d]=quad.points;
        texturedTriangle(coverImage,[{x:x0,y:0},{x:x1,y:0},{x:x1,y:PAGE_HEIGHT}],[a,b,c]);
        texturedTriangle(coverImage,[{x:x0,y:0},{x:x1,y:PAGE_HEIGHT},{x:x0,y:PAGE_HEIGHT}],[a,c,d]);
        polygon(ctx,quad.points);ctx.fillStyle='rgba(0,0,0,'+(.28*(1-Math.abs(Math.cos(quad.theta))))+')';ctx.fill();
      }
      polygon(ctx,outline(surface.points));ctx.strokeStyle='#ad8b53';ctx.lineWidth=1.6;ctx.stroke();
    }

    function renderClose(progress) {
      const elapsed=progress*CLOSE_DURATION,settle=clamp((elapsed-820)/260);
      canvas.dataset.turnPhase=elapsed<820?'closing':'settling';
      canvas.dataset.flipProgress=clamp(elapsed/820).toFixed(4);
      canvas.dataset.revealProgress=settle.toFixed(4);canvas.dataset.titleReadable='false';canvas.dataset.titleFaces='0';
      // Once the cover lands, let the compositor reveal the home beneath a
      // stationary bitmap. Repainting that full-screen canvas caused an extra
      // upload on every settling frame, exactly when the home was being shown.
      if(settle>0&&current?.settledFrame){canvas.style.opacity=String(1-smooth(settle));return;}
      clear();canvas.style.opacity=String(1-smooth(settle));
      if(progress>=1)return;
      ctx.save();ctx.setTransform(ratio,0,0,ratio,0,0);
      ctx.globalAlpha=1;
      const shade=smooth(clamp((elapsed-420)/380));
      if(shade>0){ctx.save();ctx.globalAlpha*=shade;const bg=ctx.createLinearGradient(0,0,0,height);bg.addColorStop(0,'#34261a');bg.addColorStop(1,'#201810');ctx.fillStyle=bg;ctx.fillRect(0,0,width,height);ctx.restore();}
      const scale=Math.min(width/W,height/H);ctx.translate((width-W*scale)/2,(height-H*scale)/2);ctx.scale(scale,scale);
      let moving=0;
      for(let leaf=0;leaf<2;leaf++){
        const local=clamp((elapsed-leaf*38)/650);
        if(local<=0||local>=1)continue;
        const surface=geometry(1-local,leaf,CLOSE_STRIPS);if(surface.maxX<8)continue;
        moving++;drawLeafShadow(surface,1-local);const curl=cornerCurl(surface,1-local,leaf);
        ctx.save();if(curl)clipCornerBody(curl);drawSimpleLeaf(surface,leaf);drawLeafEdges(surface,1-local,curl);ctx.restore();if(curl)drawCornerLip(curl);
      }
      const local=clamp(elapsed/820),surface=local<1?geometry(1-local,2,CLOSE_STRIPS):null;
      if(local>0&&(!surface||surface.maxX>8)){
        const bounce=settle>0?Math.sin(settle*PI*2)*Math.exp(-settle*6)*1.5:0;
        ctx.save();ctx.translate(0,bounce);
        ctx.globalAlpha*=smooth(clamp(elapsed/65));
        if(local>.8){ctx.save();ctx.globalAlpha*=smooth((local-.8)/.2);for(let i=11;i>=0;i--){ctx.strokeStyle=i%2?'#b7955e':'#dec48d';ctx.lineWidth=.8;ctx.beginPath();ctx.moveTo(HINGE,PAGE_TOP+PAGE_HEIGHT+i*.8+3);ctx.lineTo(HINGE+PAGE_WIDTH,PAGE_TOP+PAGE_HEIGHT+i*.8+3);ctx.stroke();}ctx.restore();}
        if(surface)drawClosingCover(surface);
        else ctx.drawImage(coverImage,HINGE,PAGE_TOP,PAGE_WIDTH,PAGE_HEIGHT);
        ctx.restore();
      }
      canvas.dataset.visibleLeaves=String(moving+(local>0?1:0));canvas.dataset.movingLeaves=String(moving+(local>0&&local<1?1:0));
      ctx.restore();
      if(settle>0&&current)current.settledFrame=true;
    }

    function render(progress) {
      if(current?.direction==='close'){renderClose(progress);return;}
      const elapsed = progress * DURATION;
      canvas.dataset.flipProgress = clamp(elapsed / FLIP_END).toFixed(4);
      const reading = elapsed >= FLIP_END && elapsed < FLIP_END + READING_TIME;
      canvas.dataset.turnPhase = reading ? 'reading' : elapsed < FLIP_END ? 'riffle' : 'reveal';
      canvas.dataset.titleReadable = String(reading);
      clear();
      if (progress >= 1) { canvas.dataset.visibleLeaves = '0'; canvas.dataset.movingLeaves = '0'; canvas.dataset.titleFaces = '0'; return; }
      ctx.save(); ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      const scale = Math.min(width / W, height / H);
      ctx.translate((width - W * scale) / 2, (height - H * scale) / 2); ctx.scale(scale, scale);
      const exit = clamp((elapsed - (DURATION - EXIT_TIME)) / EXIT_TIME);
      canvas.dataset.revealProgress = exit.toFixed(4);
      const peel = exit > 0 ? peelShape(exit) : null;
      if (peel) { ctx.save(); clipPeelingPaper(peel); }
      ctx.drawImage(destinationBook, 0, 0);
      if (burn) burn.draw(ctx, elapsed / 1000, {reading:reading});
      // The remaining flat blank leaves cover this one stationary title page.
      // Once they turn left, the title stays upright on the right page.
      if (elapsed <= LEAF_STARTS[LEAVES - 1]) ctx.drawImage(frontBase, HINGE, PAGE_TOP, PAGE_WIDTH, PAGE_HEIGHT);
      if (progress === 0) { canvas.dataset.visibleLeaves = '2'; canvas.dataset.movingLeaves = '0'; canvas.dataset.titleFaces = '0'; ctx.restore(); return; }
      const active = [];
      for (let leaf = 0; leaf < LEAVES; leaf++) {
        if (elapsed <= LEAF_STARTS[leaf]) continue;
        const local = (elapsed - LEAF_STARTS[leaf]) / LEAF_DURATIONS[leaf];
        if (local < 1) active.push({ index: leaf, progress: clamp(local) });
      }
      active.forEach(function (leaf) {
        leaf.surface = geometry(leaf.progress, leaf.index, STRIPS);
      });
      const visible = active.filter(function (leaf) { return leaf.surface.maxX > 8; });
      visible.slice().sort(function (a, b) {
        const depthA = a.surface.points.reduce(function (sum, p) { return sum + p.z; }, 0) / a.surface.points.length;
        const depthB = b.surface.points.reduce(function (sum, p) { return sum + p.z; }, 0) / b.surface.points.length;
        return depthA - depthB;
      }).forEach(function (leaf) {
        const curl = cornerCurl(leaf.surface, leaf.progress, leaf.index);
        ctx.save();
        if (curl) clipCornerBody(curl);
        drawLeafShadow(leaf.surface, leaf.progress);
        drawSimpleLeaf(leaf.surface, leaf.index);
        drawLeafEdges(leaf.surface, leaf.progress, curl);
        ctx.restore();
        if (curl) drawCornerLip(curl);
      });
      canvas.dataset.visibleLeaves = String(visible.length + 2);
      canvas.dataset.movingLeaves = String(visible.length);
      canvas.dataset.titleFaces = elapsed > LEAF_STARTS[LEAVES - 1] ? '1' : '0';
      if (peel) { ctx.restore(); drawPeelingEdge(peel); }
      ctx.restore();
    }

    function complete(run) {
      if (!run || run.done) return;
      run.done = true;
      if (raf) win.cancelAnimationFrame(raf);
      if (run.readingTimer) win.clearTimeout(run.readingTimer);
      raf = 0;
      if(run.direction==='close'&&!run.covered){run.covered=true;if(typeof run.onCovered==='function')run.onCovered();}
      if (current === run) current = null;
      clear(); canvas.dataset.turnProgress = '1'; canvas.dataset.turnState = 'complete';
      canvas.dataset.visibleLeaves = '0';
      canvas.dataset.movingLeaves = '0';
      canvas.dataset.flipProgress = '1';
      canvas.dataset.titleFaces = '0';
      canvas.dataset.titleReadable = 'false';
      canvas.dataset.turnPhase = 'complete';
      canvas.dataset.revealProgress = '1';
      if (typeof run.onComplete === 'function') run.onComplete();
    }

    function tick(now) {
      raf = 0;
      const run = current;
      if (!run || destroyed) return;
      run.progress = clamp((now - run.started) / run.duration);
      canvas.dataset.turnProgress = run.progress.toFixed(4);
      if (run.progress >= 1) { complete(run); return; }
      const elapsed = now - run.started;
      if(run.direction==='close'){
        if(elapsed>=820&&!run.covered){run.covered=true;if(typeof run.onCovered==='function')run.onCovered();}
        render(run.progress);if(current===run&&!run.done)raf=win.requestAnimationFrame(tick);return;
      }
      if (elapsed >= FLIP_END && elapsed < FLIP_END + READING_TIME) {
        if (burn) {
          // The cached page and ink stay still; only edge embers need 30 fps.
          if (!run.readingLastDraw || now - run.readingLastDraw >= 1000 / 30) {
            render(run.progress); run.readingLastDraw = now;
          }
          raf = win.requestAnimationFrame(tick);
          return;
        }
        // Leave the fully readable sheet on screen without spending frames
        // redrawing a still image or running an animation behind the book.
        run.progress = (FLIP_END + .01) / DURATION;
        canvas.dataset.turnProgress = run.progress.toFixed(4);
        render(run.progress);
        run.readingTimer = win.setTimeout(function () {
          run.readingTimer = 0;
          if (current === run && !run.done) tick(win.performance.now());
        }, FLIP_END + READING_TIME - elapsed);
        return;
      }
      render(run.progress);
      if (current === run && !run.done) raf = win.requestAnimationFrame(tick);
    }

    const observer = typeof win.ResizeObserver === 'function' ? new win.ResizeObserver(measure) : null;
    if (observer) observer.observe(sizeHost);
    win.addEventListener('resize', measure, { passive: true });
    prepareBookBase();
    measure();
    return {
      play: function (settings) {
        if (destroyed) return;
        if (current) complete(current);
        settings = settings || {};
        measure();
        const direction=settings.direction==='close'?'close':'open';
        // Closing has no title sheet. Rebuilding its paper and calligraphy here
        // delayed the first visible response to the return button.
        if(direction==='open')prepare(settings.title, settings.subtitle);
        const run = { started: win.performance.now(), progress: 0, readingTimer: 0, readingLastDraw: 0,
          title: settings.title, subtitle: settings.subtitle, onComplete: settings.onComplete,onCovered:settings.onCovered,covered:false,direction,duration:direction==='close'?CLOSE_DURATION:DURATION,done:false };
        current = run; canvas.dataset.turnProgress = '0'; canvas.dataset.turnState = 'playing';
        canvas.dataset.turnDirection=direction;
        const liveReduced = typeof win.matchMedia === 'function' && win.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reduced || liveReduced) { Promise.resolve().then(function () { if (current === run) complete(run); }); return; }
        render(0); raf = win.requestAnimationFrame(tick);
      },
      finish: function () { if (current) complete(current); else clear(); },
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        if (current) complete(current);
        if (raf) win.cancelAnimationFrame(raf);
        raf = 0; clear();
        if (observer) observer.disconnect();
        if (burn) burn.destroy();
        if(coverImage!==cover)coverImage.close();
        win.removeEventListener('resize', measure);
        canvas.dataset.turnState = 'destroyed';
        canvas.dataset.visibleLeaves = '0';
        canvas.dataset.movingLeaves = '0';
        canvas.dataset.titleReadable = 'false';
      },
    };
  }

  window.ShadowPageTurn = { create: create };
})();
