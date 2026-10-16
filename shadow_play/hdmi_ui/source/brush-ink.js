/* Deterministic, pressure-shaped ink for the sketch canvas. No input is changed. */
(function () {
  'use strict';
  const cache = new WeakMap();
  const TAU = Math.PI * 2;
  const INK = '#3c3227';
  const WET_INK = '#29251e';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const smooth = v => { v = clamp(v, 0, 1); return v * v * (3 - 2 * v); };
  const random = (seed, index) => {
    let n = (seed ^ Math.imul(index + 17, 0x45d9f3b)) >>> 0;
    n = Math.imul(n ^ (n >>> 16), 0x45d9f3b); n = Math.imul(n ^ (n >>> 16), 0x45d9f3b);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967295;
  };
  function xy(p) { return Array.isArray(p) ? p : [p && p.x, p && p.y]; }
  function catmull(a, b, c, d, t) {
    const t2 = t * t, t3 = t2 * t;
    return .5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
  }
  function chain(path, points) {
    if (!points.length) return;
    path.lineTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      const p = points[i - 1], q = points[i];
      path.quadraticCurveTo(p.x, p.y, (p.x + q.x) / 2, (p.y + q.y) / 2);
    }
    const end = points[points.length - 1]; path.lineTo(end.x, end.y);
  }
  function ribbon(points, radiusScale, rough, seed) {
    const left = [], right = [], path = new Path2D();
    points.forEach((p, i) => {
      const noise = rough ? (random(seed, Math.floor(p.s / 1.7)) - .5) * .30 : 0;
      const radius = Math.max(.10, p.radius * radiusScale);
      left.push({ x: p.x + p.nx * (radius + noise), y: p.y + p.ny * (radius + noise) });
      right.push({ x: p.x - p.nx * (radius - noise * .65), y: p.y - p.ny * (radius - noise * .65) });
    });
    const first = points[0], last = points[points.length - 1];
    path.moveTo(left[0].x, left[0].y); chain(path, left);
    const endAngle = Math.atan2(last.ny, last.nx);
    path.arc(last.x, last.y, Math.max(.1, last.radius * radiusScale), endAngle, endAngle - Math.PI, true);
    chain(path, right.reverse());
    const startAngle = Math.atan2(first.ny, first.nx);
    path.arc(first.x, first.y, Math.max(.1, first.radius * radiusScale), startAngle - Math.PI, startAngle - TAU, true);
    path.closePath();
    return path;
  }
  function build(stroke, width, height, active, pressure, strokeIndex) {
    const scale = clamp(Math.sqrt(Math.min(width, height) / 240), .78, 1.25);
    const raw = [];
    for (let i = 0; i < stroke.length; i++) {
      const p = xy(stroke[i]);
      if (!Number.isFinite(p[0]) || !Number.isFinite(p[1])) continue;
      const q = { x: p[0] * width, y: p[1] * height, pressure: Number.isFinite(pressure && pressure[i]) ? clamp(pressure[i], 0, 1) : null };
      if (!raw.length || Math.hypot(q.x - raw[raw.length - 1].x, q.y - raw[raw.length - 1].y) > .16) raw.push(q);
    }
    if (!raw.length) return null;
    const seed = (Math.imul(Math.round(raw[0].x * 17), 374761393) ^ Math.imul(Math.round(raw[0].y * 19), 668265263) ^ Math.imul(strokeIndex + 1, 1274126177)) >>> 0;
    if (raw.length === 1) {
      const p = raw[0], radius = (2.05 + random(seed, 9) * .45) * scale, dot = new Path2D();
      for (let i = 0; i <= 20; i++) {
        const angle = i / 20 * TAU, r = radius * (.91 + random(seed, i % 20) * .15);
        const x = p.x + Math.cos(angle) * r, y = p.y + Math.sin(angle) * r * .91;
        if (!i) dot.moveTo(x, y); else dot.lineTo(x, y);
      }
      dot.closePath(); return { body: dot, core: dot, fibers: null };
    }
    let roughLength = 0;
    for (let i = 1; i < raw.length; i++) roughLength += Math.hypot(raw[i].x - raw[i - 1].x, raw[i].y - raw[i - 1].y);
    const spacing = Math.max(1.35 * scale, roughLength / 1500);
    const points = [];
    for (let i = 0; i < raw.length - 1; i++) {
      const a = raw[Math.max(0, i - 1)], b = raw[i], c = raw[i + 1], d = raw[Math.min(raw.length - 1, i + 2)];
      const sourceSpeed = Math.hypot(c.x - b.x, c.y - b.y);
      const steps = clamp(Math.ceil(sourceSpeed / spacing), 1, 32);
      for (let j = 0; j < steps; j++) {
        const t = j / steps;
        const previousSpeed = i ? Math.hypot(b.x - a.x, b.y - a.y) : sourceSpeed;
        points.push({ x: catmull(a.x, b.x, c.x, d.x, t), y: catmull(a.y, b.y, c.y, d.y, t), speed: previousSpeed * (1 - t) + sourceSpeed * t, pressure: b.pressure !== null && c.pressure !== null ? b.pressure * (1 - t) + c.pressure * t : null });
      }
    }
    const rawEnd = raw[raw.length - 1]; points.push({ x: rawEnd.x, y: rawEnd.y, speed: points[points.length - 1].speed, pressure: rawEnd.pressure });
    let length = 0;
    points.forEach((p, i) => { if (i) length += Math.hypot(p.x - points[i - 1].x, p.y - points[i - 1].y); p.s = length; });
    let filteredWidth = 4.2 * scale;
    points.forEach((p, i) => {
      const before = points[Math.max(0, i - 2)], after = points[Math.min(points.length - 1, i + 2)];
      const dx = after.x - before.x, dy = after.y - before.y, norm = Math.hypot(dx, dy) || 1;
      p.nx = -dy / norm; p.ny = dx / norm;
      const previous = points[Math.max(0, i - 3)], next = points[Math.min(points.length - 1, i + 3)];
      const a = Math.atan2(p.y - previous.y, p.x - previous.x), b = Math.atan2(next.y - p.y, next.x - p.x);
      const turn = Math.abs(Math.atan2(Math.sin(b - a), Math.cos(b - a)));
      const speed = 1 - Math.exp(-p.speed / (7 * scale));
      let desired = p.pressure === null ? (4.45 - 2.75 * speed + Math.min(.55, turn * .42)) * scale : (1.35 + 3.25 * Math.sqrt(p.pressure)) * scale;
      desired *= .96 + .065 * Math.sin(Math.atan2(dy, dx) * 2 + .6);
      filteredWidth += (desired - filteredWidth) * .22;
      const start = .91 + .13 * Math.exp(-p.s / (5 * scale));
      const endLength = Math.min(15 * scale, Math.max(3 * scale, length * .20));
      const finish = active ? 1 : .12 + .88 * smooth((length - p.s) / endLength);
      p.radius = clamp(filteredWidth * start * finish / 2, .12, 2.65 * scale);
      p.speedRatio = speed;
    });
    const body = ribbon(points, 1, true, seed), core = ribbon(points, .48, false, seed);
    // Narrow transparent fibers expose the actual paper beneath this stroke.
    // Opposite-winding holes do not erase ink laid down by a crossing stroke.
    let bucket = -1;
    for (let i = 2; i < points.length - 3; i++) {
      const p = points[i], current = Math.floor(p.s / (22 * scale));
      if (current === bucket) continue; bucket = current;
      if (p.s < 11 * scale || length - p.s < 12 * scale || p.radius < 1.12 * scale || random(seed, current + 400) < .56) continue;
      const target = p.s + (5 + random(seed, current + 700) * 9) * scale;
      let end = i + 1; while (end < points.length - 2 && points[end].s < target) end++;
      const offset = (random(seed, current + 900) - .5) * .95;
      const thin = (.12 + random(seed, current + 1000) * .15) * scale;
      const left = [], right = [];
      for (let k = i; k <= end; k++) {
        const q = points[k], taper = Math.sin((k - i) / Math.max(1, end - i) * Math.PI);
        const center = q.radius * offset;
        left.push({ x: q.x + q.nx * (center + thin * taper), y: q.y + q.ny * (center + thin * taper) });
        right.push({ x: q.x + q.nx * (center - thin * taper), y: q.y + q.ny * (center - thin * taper) });
      }
      body.moveTo(right[0].x, right[0].y); chain(body, right); chain(body, left.reverse()); body.closePath();
    }
    const fibers = new Path2D();
    // A few translucent bristles soften the outer edge, rather than a blur.
    for (let strand = 0; strand < 2; strand++) {
      let drawing = false;
      points.forEach(p => {
        const gate = random(seed, Math.floor(p.s / (17 * scale)) + 1300 + strand * 71);
        if (gate < .68 || p.radius < .65 || p.s < 5 || length - p.s < 5) { drawing = false; return; }
        const side = strand ? 1 : -1, offset = p.radius + (.13 + gate * .18) * scale;
        const x = p.x + p.nx * offset * side, y = p.y + p.ny * offset * side;
        if (!drawing) fibers.moveTo(x, y); else fibers.lineTo(x, y); drawing = true;
      });
    }
    return { body, core, fibers, fiberWidth: .38 * scale };
  }
  function draw(ctx, strokes, width, height, options) {
    if (!ctx || !Array.isArray(strokes) || !(width > 0 && height > 0)) return;
    options = options || {};
    const activeIndex = Number.isInteger(options.activeStrokeIndex) ? options.activeStrokeIndex : -1;
    ctx.save();
    try {
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      strokes.forEach((stroke, index) => {
        if (!Array.isArray(stroke) || !stroke.length) return;
        const active = index === activeIndex;
        const pressure = Array.isArray(options.pressures && options.pressures[index]) ? options.pressures[index] : (strokes.length === 1 && Array.isArray(options.pressures) ? options.pressures : null);
        const last = xy(stroke[stroke.length - 1]);
        const pressureLast = pressure && pressure[pressure.length - 1];
        let entry = cache.get(stroke);
        if (!entry || entry.width !== width || entry.height !== height || entry.count !== stroke.length || entry.x !== last[0] || entry.y !== last[1] || entry.active !== active || entry.pressure !== pressure || entry.pressureLast !== pressureLast) {
          entry = { width, height, count: stroke.length, x: last[0], y: last[1], active, pressure, pressureLast, geometry: build(stroke, width, height, active, pressure, index) };
          cache.set(stroke, entry);
        }
        const ink = entry.geometry; if (!ink) return;
        ctx.globalAlpha = .96; ctx.fillStyle = INK; ctx.fill(ink.body);
        ctx.save(); ctx.clip(ink.body); ctx.globalAlpha = .14; ctx.fillStyle = WET_INK; ctx.fill(ink.core); ctx.restore();
        if (ink.fibers) { ctx.globalAlpha = .22; ctx.strokeStyle = INK; ctx.lineWidth = ink.fiberWidth; ctx.stroke(ink.fibers); }
      });
    } finally { ctx.restore(); }
  }
  window.ShadowInkBrush = { draw };
})();
