/* Local, decorative canvas effects for the old-book interface. */
(function () {
  'use strict';

  const FRAME_MS = 1000 / 30;

  function create(options) {
    options = options || {};
    const root = options.root;
    const canvas = options.emberCanvas;
    if (!root || !canvas || typeof canvas.getContext !== 'function') {
      throw new TypeError('ShadowBookEffects.create needs a root element and an ember canvas.');
    }
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return { setPage: function () {}, setActive: function () {}, setHome: function () {}, destroy: function () {} };

    const doc = canvas.ownerDocument || document;
    const win = doc.defaultView || window;
    const area = canvas.parentElement || root;
    const motionPreference = win.matchMedia('(prefers-reduced-motion: reduce)');
    const noSparks = Boolean(win.ShadowBoardDisplay);
    let reducedMotion = noSparks || Boolean(options.reducedMotion) || motionPreference.matches;
    const originalPointerEvents = canvas.style.pointerEvents;
    canvas.style.pointerEvents = 'none';
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.width = '100%';
    canvas.style.height = '100%';

    let active = false;
    let currentPage = 'home';
    let destroyed = false;
    let frame = 0;
    let lastPaint = 0;
    let lastStep = 0;
    let width = 1;
    let height = 1;
    let dpr = 1;
    let particles = [];
    let protectedAreas = [];
    const modes = Array.from(options.modeCanvases || []).map(function (edgeCanvas) {
      edgeCanvas.style.pointerEvents = 'none'; edgeCanvas.setAttribute('aria-hidden', 'true');
      return { canvas: edgeCanvas, host: edgeCanvas.parentElement, ctx: edgeCanvas.getContext('2d', { alpha: true }), width: 0, height: 0, burn: null };
    });

    function selectedMode() { return modes.find(function (entry) { return entry.host && entry.host.dataset.screen === currentPage; }); }
    function clearMode(entry) {
      if (!entry || !entry.ctx) return;
      entry.ctx.save(); entry.ctx.setTransform(1, 0, 0, 1, 0, 0); entry.ctx.clearRect(0, 0, entry.canvas.width, entry.canvas.height); entry.ctx.restore();
    }
    function clearModes() { modes.forEach(clearMode); }
    function measureMode() {
      const entry = selectedMode(); if (!entry || !entry.ctx) return false;
      const box = entry.canvas.getBoundingClientRect(), w = Math.round(box.width), h = Math.round(box.height);
      if (w < 2 || h < 2 || (entry.width === w && entry.height === h && entry.burn)) return false;
      entry.width = w; entry.height = h; entry.canvas.width = w; entry.canvas.height = h;
      if (entry.burn) entry.burn.destroy();
      const hinge = w * .13;
      entry.burn = win.ShadowPaperBurn && win.ShadowPaperBurn.create({ document: doc, width: w, height: h, pageTop: 8, pageHeight: Math.max(1, h - 16), bookLeft: 8, hinge: hinge, pageWidth: w - hinge - 8 });
      return true;
    }
    function paintMode(seconds, still) {
      const entry = selectedMode(); if (!entry || !entry.ctx || !entry.burn) return;
      clearMode(entry);
      if (still) entry.burn.drawStatic(entry.ctx);
      else entry.burn.draw(entry.ctx, seconds, { reading: true });
    }
    function measureProtectedAreas() {
      const box = area.getBoundingClientRect();
      const screen = root.querySelector('[data-screen="' + currentPage + '"]');
      protectedAreas = screen ? Array.from(screen.querySelectorAll('.shadow-mode-heading,.shadow-hero-copy,button,input,.shadow-controller-title,.shadow-live-hint,.shadow-body-status')).filter(function (el) { return el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'; }).map(function (el) {
        const r = el.getBoundingClientRect(); return { left: r.left - box.left - 6, right: r.right - box.left + 6, top: r.top - box.top - 6, bottom: r.bottom - box.top + 6 };
      }) : [];
    }

    function clear() {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.restore();
    }

    function particle(initial) {
      const kind = Math.random();
      return {
        x: Math.random() * width,
        y: initial ? Math.random() * height : -8 - Math.random() * height * .14,
        radius: .75 + Math.pow(Math.random(), 1.8) * 2,
        speed: 13 + Math.random() * 26,
        drift: -4 + Math.random() * 12,
        phase: Math.random() * Math.PI * 2,
        sway: 2 + Math.random() * 7,
        flicker: 1 + Math.random() * 2,
        alpha: .36 + Math.random() * .38,
        // Most fragments are quiet ash; a few still carry a glowing ember.
        coal: kind < .32,
        ash: kind > .77,
        tail: kind > .35 && kind < .49,
        length: 6 + Math.random() * 9,
      };
    }

    function replenish() {
      const count = Math.max(12, Math.min(54, Math.round(width * height / 18000)));
      particles = Array.from({ length: count }, function () { return particle(true); });
    }

    function paintStatic() {
      clear();
      if(noSparks){paintMode(0,true);return;}
      // Motion-sensitive viewers get a few stationary flecks, without a loop.
      const dots = [[.07, .19, 1.1], [.18, .74, .8], [.34, .1, .6], [.64, .83, .9], [.81, .28, 1.2], [.93, .64, .65]];
      dots.forEach(function (p, i) {
        if (protectedAreas.some(function (r) { return p[0] * width >= r.left && p[0] * width <= r.right && p[1] * height >= r.top && p[1] * height <= r.bottom; })) return;
        ctx.fillStyle = i % 2 ? 'rgba(193,113,57,.23)' : 'rgba(238,180,101,.33)';
        ctx.beginPath(); ctx.arc(p[0] * width, p[1] * height, p[2], 0, Math.PI * 2); ctx.fill();
      });
      paintMode(0, true);
    }

    function measure() {
      if (destroyed) return;
      const box = area.getBoundingClientRect();
      const nextWidth = Math.max(1, box.width || root.clientWidth || 1);
      const nextHeight = Math.max(1, box.height || root.clientHeight || 1);
      const nextDpr = Math.min(1.5, Math.max(1, win.devicePixelRatio || 1));
      const modeChanged = measureMode();
      if (nextWidth === width && nextHeight === height && nextDpr === dpr) {
        if (modeChanged) { measureProtectedAreas(); paintMode(win.performance.now() / 1000, !active || reducedMotion); }
        return;
      }
      const oldWidth = width;
      const oldHeight = height;
      width = nextWidth; height = nextHeight; dpr = nextDpr;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (particles.length && oldWidth > 1 && oldHeight > 1) {
        particles.forEach(function (p) { p.x *= width / oldWidth; p.y *= height / oldHeight; });
        const count = Math.max(12, Math.min(54, Math.round(width * height / 18000)));
        while (particles.length < count) particles.push(particle(true));
        particles.length = count;
      } else replenish();
      measureProtectedAreas();
      if (active && !doc.hidden && reducedMotion) paintStatic();
      else if (!active || doc.hidden) { clear(); paintMode(0, true); }
    }

    function drawParticle(p, seconds) {
      const pulse = .8 + .2 * Math.sin(seconds * p.flicker + p.phase);
      const alpha = p.alpha * pulse;
      const x = p.x + Math.sin(seconds * .52 + p.phase) * p.sway;
      const y = p.y;
      const r = p.radius;
      if (protectedAreas.some(function (rect) { return x + r * 4 >= rect.left && x - r * 4 <= rect.right && y + r * 4 >= rect.top && y - r * 4 <= rect.bottom; })) return;
      if (!p.ash && r > .9) {
        const glow = ctx.createRadialGradient(x, y, 0, x, y, r * 6);
        glow.addColorStop(0, p.coal ? 'rgba(211,67,32,' + (alpha * .3) + ')' : 'rgba(250,149,62,' + (alpha * .4) + ')');
        glow.addColorStop(.3, 'rgba(210,77,29,' + (alpha * .17) + ')');
        glow.addColorStop(1, 'rgba(169,58,21,0)');
        ctx.fillStyle = glow;
        ctx.beginPath(); ctx.arc(x, y, r * 6, 0, Math.PI * 2); ctx.fill();
      }
      // Only an occasional fragment leaves a short, faint trail above itself.
      if (p.tail && Math.sin(seconds * .7 + p.phase) > .4) {
        const tail = ctx.createLinearGradient(x - 2, y - p.length, x, y);
        tail.addColorStop(0, 'rgba(173,77,30,0)');
        tail.addColorStop(1, 'rgba(255,166,73,' + (alpha * .85) + ')');
        ctx.strokeStyle = tail; ctx.lineWidth = Math.max(.8, r * .7);
        ctx.beginPath(); ctx.moveTo(x - p.drift * .09, y - p.length);
        ctx.quadraticCurveTo(x - 1.5, y - p.length * .4, x, y); ctx.stroke();
      }
      ctx.fillStyle = p.coal
        ? 'rgba(216,82,39,' + alpha + ')'
        : p.ash ? 'rgba(203,159,96,' + (alpha * .65) + ')'
          : 'rgba(255,186,98,' + alpha + ')';
      ctx.save(); ctx.translate(x, y); ctx.rotate(p.phase + seconds * .15);
      ctx.beginPath(); ctx.ellipse(0, 0, r * (p.ash ? .48 : .72), r, 0, 0, Math.PI * 2); ctx.fill();
      if (!p.coal && !p.ash && r > 1.3) {
        ctx.fillStyle = 'rgba(255,219,149,' + (alpha * .6) + ')';
        ctx.fillRect(-.3, -.45, .6, .9);
      }
      ctx.restore();
    }

    function paint(dt, seconds) {
      clear();
      const breeze = Math.sin(seconds * .21) * 2;
      for (let i = 0; i < particles.length; i++) {
        let p = particles[i];
        p.x += (p.drift + breeze) * dt;
        p.y += p.speed * dt;
        if (p.y > height + 14 || p.x < -30 || p.x > width + 30) p = particles[i] = particle(false);
        drawParticle(p, seconds);
      }
      paintMode(seconds, false);
    }

    function stop() {
      if (frame) win.cancelAnimationFrame(frame);
      frame = 0; lastPaint = 0; lastStep = 0;
    }

    function tick(now) {
      frame = 0;
      if (motionPreference.matches && !reducedMotion) {
        reducedMotion = true; clear(); if (active && !doc.hidden) paintStatic();
      }
      if (destroyed || !active || doc.hidden || reducedMotion) return;
      const elapsed = now - lastPaint;
      if (!lastPaint || elapsed >= FRAME_MS) {
        const dt = lastStep ? Math.min(.09, (now - lastStep) / 1000) : 1 / 30;
        lastStep = now;
        lastPaint = lastPaint ? lastPaint + Math.max(1, Math.floor(elapsed / FRAME_MS)) * FRAME_MS : now;
        paint(dt, now / 1000);
      }
      frame = win.requestAnimationFrame(tick);
    }

    function resume() {
      if (destroyed || !active || doc.hidden) return;
      measure();
      if (reducedMotion) { paintStatic(); return; }
      if (!frame) frame = win.requestAnimationFrame(tick);
    }

    function onVisibility() {
      stop();
      if (doc.hidden) { clear(); clearModes(); }
      else resume();
    }
    function onMotionPreference(event) {
      reducedMotion = noSparks || event.matches;
      stop(); clear(); resume();
    }

    const observer = typeof win.ResizeObserver === 'function' ? new win.ResizeObserver(measure) : null;
    if (observer) {
      observer.observe(root);
      if (area !== root) observer.observe(area);
      modes.forEach(function (entry) { if (entry.host) observer.observe(entry.host); });
    }
    win.addEventListener('resize', measure, { passive: true });
    doc.addEventListener('visibilitychange', onVisibility);
    motionPreference.addEventListener('change', onMotionPreference);
    measure();

    return {
      pause: function () {
        if(destroyed)return;
        // Freeze the last painted embers; a page turn must not start by
        // clearing and repainting both full-screen decorative canvases.
        active=false;stop();
      },
      setPage: function (page, isActive) {
        if (destroyed) return;
        const nextPage = String(page || 'home');
        if (nextPage !== currentPage) { clearModes(); currentPage = nextPage; }
        active = isActive !== false;
        measure(); measureProtectedAreas();
        if (active) resume();
        else { stop(); clear(); paintMode(0, true); }
      },
      setActive: function (isActive) {
        if (destroyed) return;
        active = Boolean(isActive);
        if (active) resume();
        else { stop(); clear(); paintMode(0, true); }
      },
      setHome: function (isHome) {
        if (destroyed) return;
        currentPage = 'home'; active = Boolean(isHome); clearModes();
        if (active) resume(); else { stop(); clear(); }
      },
      destroy: function () {
        if (destroyed) return;
        destroyed = true; active = false;
        stop(); clear(); clearModes(); particles = []; protectedAreas = [];
        modes.forEach(function (entry) { if (entry.burn) entry.burn.destroy(); entry.burn = null; });
        if (observer) observer.disconnect();
        win.removeEventListener('resize', measure);
        doc.removeEventListener('visibilitychange', onVisibility);
        motionPreference.removeEventListener('change', onMotionPreference);
        canvas.style.pointerEvents = originalPointerEvents;
      },
    };
  }

  function drawOldPaper(ctx, width, height) {
    if (!ctx || width <= 0 || height <= 0) return;
    ctx.save();
    const paper = ctx.createLinearGradient(0, 0, width, height);
    paper.addColorStop(0, '#c9aa72'); paper.addColorStop(.14, '#e1c691');
    paper.addColorStop(.45, '#ead5a6'); paper.addColorStop(.8, '#dfc38d'); paper.addColorStop(1, '#bea06b');
    ctx.fillStyle = paper; ctx.fillRect(0, 0, width, height);
    let seed = 72931;
    const random = function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    const count = Math.min(3000, Math.max(300, Math.floor(width * height / 240)));
    ctx.lineWidth = .45;
    for (let i = 0; i < count; i++) {
      const x = random() * width; const y = random() * height;
      ctx.strokeStyle = i % 3 ? 'rgba(99,65,31,.055)' : 'rgba(255,244,207,.2)';
      ctx.beginPath(); ctx.moveTo(x, y);
      ctx.lineTo(x + 3 + random() * 16, y + (random() - .5) * 2); ctx.stroke();
    }
    for (let i = 0; i < 220; i++) {
      const x = random() * width; const y = random() * height;
      const r = .25 + Math.pow(random(), 4) * 2.1;
      ctx.fillStyle = 'rgba(103,65,32,' + (.03 + random() * .09) + ')';
      ctx.beginPath(); ctx.ellipse(x, y, r * 1.3, r, random() * 3, 0, Math.PI * 2); ctx.fill();
    }
    // Low-contrast age stains, weighted toward the margins.
    for (let i = 0; i < 16; i++) {
      const x = i % 2 ? random() * width * .13 : width * (.87 + random() * .13);
      const y = random() * height;
      const r = Math.min(width, height) * (.035 + random() * .12);
      const stain = ctx.createRadialGradient(x, y, 0, x, y, r);
      stain.addColorStop(0, 'rgba(125,78,31,.065)'); stain.addColorStop(.68, 'rgba(134,83,34,.035)'); stain.addColorStop(1, 'rgba(134,83,34,0)');
      ctx.fillStyle = stain; ctx.fillRect(x - r, y - r, r * 2, r * 2);
    }
    const edgeX = ctx.createLinearGradient(0, 0, width, 0);
    edgeX.addColorStop(0, 'rgba(69,39,17,.33)'); edgeX.addColorStop(.012, 'rgba(100,54,22,.12)');
    edgeX.addColorStop(.07, 'rgba(104,67,28,0)'); edgeX.addColorStop(.92, 'rgba(104,67,28,0)');
    edgeX.addColorStop(.987, 'rgba(100,54,22,.12)'); edgeX.addColorStop(1, 'rgba(69,39,17,.3)');
    ctx.fillStyle = edgeX; ctx.fillRect(0, 0, width, height);
    const edgeY = ctx.createLinearGradient(0, 0, 0, height);
    edgeY.addColorStop(0, 'rgba(83,44,18,.27)'); edgeY.addColorStop(.025, 'rgba(111,66,26,.06)');
    edgeY.addColorStop(.12, 'rgba(111,66,26,0)'); edgeY.addColorStop(.9, 'rgba(111,66,26,0)');
    edgeY.addColorStop(.985, 'rgba(95,48,18,.11)'); edgeY.addColorStop(1, 'rgba(66,35,14,.31)');
    ctx.fillStyle = edgeY; ctx.fillRect(0, 0, width, height);
    // Uneven fibers at the outermost edge give a lightly scorched, worn finish.
    ctx.fillStyle = 'rgba(69,38,18,.18)';
    [false, true].forEach(function (right) {
      ctx.beginPath(); ctx.moveTo(right ? width : 0, 0);
      for (let y = 0; y <= height; y += Math.max(5, height / 80)) {
        const bite = .6 + random() * 3.4;
        ctx.lineTo(right ? width - bite : bite, y);
      }
      ctx.lineTo(right ? width : 0, height); ctx.closePath(); ctx.fill();
    });
    ctx.restore();
  }

  window.ShadowBookEffects = { create: create, drawOldPaper: drawOldPaper };
})();
