/* Local paper-edge scorching. The caller supplies the animation clock in seconds.
 * draw(ctx, seconds, {reading}) includes drawStatic(ctx); do not call both.
 * Paint after the book base and before moving leaves. No timers or input hooks.
 */
(function () {
  'use strict';
  const TAU = Math.PI * 2;

  function create(options) {
    options = options || {};
    const doc = options.document || document;
    const number = function (value, fallback) { return Number.isFinite(value) ? value : fallback; };
    const width = Math.max(1, number(options.width, 1000));
    const height = Math.max(1, number(options.height, 550));
    const top = number(options.pageTop, 45);
    const bottom = top + number(options.pageHeight, 460);
    const hinge = number(options.hinge, 500);
    const pageWidth = number(options.pageWidth, 480);
    // The narrow left stub and the broad right page share one outer perimeter.
    // There is deliberately no burn along the hinge or the old x=500 midline.
    const left = number(options.bookLeft, width * .02);
    const right = Math.min(width * .98, hinge + pageWidth);
    const overlay = doc.createElement('canvas');
    overlay.width = Math.ceil(width); overlay.height = Math.ceil(height);
    const ink = overlay.getContext('2d');
    let destroyed = false;
    let seed = 53209;
    const random = function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    const edges = [
      { a: [left, top], b: [right, top], normal: [0, 1], phase: .8 },
      { a: [right, top], b: [right, bottom], normal: [-1, 0], phase: 2.3 },
      { a: [right, bottom], b: [left, bottom], normal: [0, -1], phase: 4.6 },
      { a: [left, bottom], b: [left, top], normal: [1, 0], phase: 1.7 },
    ];

    function point(edge, along, inward) {
      return { x: edge.a[0] + (edge.b[0] - edge.a[0]) * along + edge.normal[0] * inward,
        y: edge.a[1] + (edge.b[1] - edge.a[1]) * along + edge.normal[1] * inward };
    }

    function band(edge, depth, fill) {
      const length = Math.hypot(edge.b[0] - edge.a[0], edge.b[1] - edge.a[1]);
      const count = Math.max(20, Math.ceil(length / 7));
      const outer = [], inner = [];
      for (let i = 0; i <= count; i++) {
        const t = i / count;
        const wave = .6 + .4 * Math.sin(t * 19 + edge.phase);
        outer.push(point(edge, t, -.8 - random() * 1.6));
        inner.push(point(edge, t, depth * (.4 + random() * .45 + wave * .25)));
      }
      ink.beginPath(); ink.moveTo(outer[0].x, outer[0].y);
      outer.forEach(function (p) { ink.lineTo(p.x, p.y); });
      inner.reverse().forEach(function (p) { ink.lineTo(p.x, p.y); });
      ink.closePath(); ink.fillStyle = fill; ink.fill();
    }

    edges.forEach(function (edge) {
      const a = point(edge, .5, 0), b = point(edge, .5, 25);
      const stain = ink.createLinearGradient(a.x, a.y, b.x, b.y);
      stain.addColorStop(0, 'rgba(66,35,16,.64)'); stain.addColorStop(.22, 'rgba(101,49,20,.37)');
      stain.addColorStop(.54, 'rgba(136,72,29,.13)'); stain.addColorStop(1, 'rgba(134,74,30,0)');
      band(edge, 25, stain);
      const charred = ink.createLinearGradient(a.x, a.y, point(edge, .5, 10).x, point(edge, .5, 10).y);
      charred.addColorStop(0, 'rgba(34,23,17,.92)'); charred.addColorStop(.35, 'rgba(53,29,18,.81)');
      charred.addColorStop(.82, 'rgba(89,43,22,.46)'); charred.addColorStop(1, 'rgba(101,49,24,0)');
      band(edge, 9.5, charred);
      // Broken red seams and tiny amber holes keep the rim organic.
      for (let i = 0; i < 22; i++) {
        const t = .015 + random() * .97;
        const p = point(edge, t, .6 + random() * 2.5);
        const q = point(edge, Math.min(.995, t + .0018 + random() * .004), 1 + random() * 2.2);
        ink.strokeStyle = i % 3 ? 'rgba(124,43,24,.72)' : 'rgba(207,97,39,.68)';
        ink.lineWidth = .6 + random() * .8;
        ink.beginPath(); ink.moveTo(p.x, p.y); ink.lineTo(q.x, q.y); ink.stroke();
      }
    });

    const glow = doc.createElement('canvas'); glow.width = glow.height = 32;
    const gc = glow.getContext('2d');
    const glowFill = gc.createRadialGradient(16, 16, 0, 16, 16, 16);
    glowFill.addColorStop(0, 'rgba(255,177,86,.68)'); glowFill.addColorStop(.18, 'rgba(232,93,32,.46)');
    glowFill.addColorStop(.48, 'rgba(151,38,20,.19)'); glowFill.addColorStop(1, 'rgba(139,32,17,0)');
    gc.fillStyle = glowFill; gc.fillRect(0, 0, 32, 32);

    const embers = Array.from({ length: 28 }, function (_, i) {
      const edge = edges[i % edges.length];
      return { edge: edge, t: .025 + random() * .95, phase: random() * TAU,
        size: 3.5 + random() * 4.5, speed: .8 + random() * 1.2 };
    });
    const flames = Array.from({ length: 9 }, function (_, i) {
      const edge = edges[i % edges.length];
      return { edge: edge, t: .05 + random() * .9, phase: random() * TAU,
        height: 5 + random() * 8, width: 1.6 + random() * 1.7 };
    });
    const sparks = Array.from({ length: 11 }, function (_, i) {
      return { anchor: embers[(i * 7) % embers.length], phase: random(),
        duration: 1.6 + random() * 1.8, drift: (random() - .5) * 16,
        rise: 17 + random() * 26, radius: .45 + random() * .7 };
    });

    function drawStatic(ctx) {
      if (!destroyed && ctx) ctx.drawImage(overlay, 0, 0, width, height);
    }

    function draw(ctx, seconds, state) {
      if (destroyed || !ctx) return;
      state = state || {};
      const time = Number.isFinite(seconds) ? seconds : 0;
      drawStatic(ctx);
      if(globalThis.ShadowBoardDisplay)return;
      ctx.save();
      const inheritedAlpha = ctx.globalAlpha;
      embers.forEach(function (ember) {
        const p = point(ember.edge, ember.t, 1.1);
        const pulse = .38 + .24 * Math.sin(time * ember.speed * 2 + ember.phase);
        const size = ember.size * (1 + .12 * Math.sin(time * 2.7 + ember.phase));
        ctx.globalAlpha = inheritedAlpha * pulse;
        ctx.drawImage(glow, p.x - size, p.y - size, size * 2, size * 2);
        ctx.fillStyle = '#e9873d'; ctx.beginPath(); ctx.arc(p.x, p.y, .55, 0, TAU); ctx.fill();
      });
      flames.forEach(function (flame) {
        const flicker = Math.sin(time * 2.8 + flame.phase);
        if (flicker < -.08) return;
        const base = point(flame.edge, flame.t, -.3);
        const heat = .3 + .7 * (flicker + 1) / 2;
        const h = flame.height * heat * (state.reading ? .86 : 1);
        const w = flame.width * (.65 + heat * .35);
        const side = -flame.edge.normal[0] * 2.3;
        const lean = Math.sin(time * 4.1 + flame.phase) * 2.1 + side;
        ctx.globalAlpha = inheritedAlpha * (.5 + heat * .26);
        const fire = ctx.createLinearGradient(base.x, base.y - h, base.x, base.y + 1);
        fire.addColorStop(0, 'rgba(255,207,124,.08)'); fire.addColorStop(.45, 'rgba(246,141,53,.82)');
        fire.addColorStop(1, 'rgba(155,43,21,.9)');
        ctx.fillStyle = fire; ctx.beginPath(); ctx.moveTo(base.x - w, base.y + 1);
        ctx.bezierCurveTo(base.x - w * 1.2, base.y - h * .35, base.x + lean - w, base.y - h * .5, base.x + lean, base.y - h);
        ctx.bezierCurveTo(base.x + lean + .9, base.y - h * .45, base.x + w * 1.3, base.y - h * .32, base.x + w, base.y + 1);
        ctx.closePath(); ctx.fill();
      });
      sparks.forEach(function (spark) {
        const age = ((time / spark.duration + spark.phase) % 1 + 1) % 1;
        const visibility = Math.sin(PI * age);
        if (visibility < .28) return;
        const origin = point(spark.anchor.edge, spark.anchor.t, -.6);
        const outside = -spark.anchor.edge.normal[0] * age * 8;
        const x = origin.x + spark.drift * age + outside;
        const y = origin.y - spark.rise * age;
        ctx.globalAlpha = inheritedAlpha * visibility * .55;
        ctx.fillStyle = age < .45 ? '#f1b263' : '#c76b38';
        ctx.beginPath(); ctx.ellipse(x, y, spark.radius * .72, spark.radius, -.28, 0, TAU); ctx.fill();
      });
      ctx.restore();
    }

    const PI = Math.PI;
    return { draw: draw, drawStatic: drawStatic,
      bounds: { left: left, right: right, top: top, bottom: bottom },
      destroy: function () { destroyed = true; overlay.width = overlay.height = glow.width = glow.height = 0; } };
  }

  window.ShadowPaperBurn = { create: create };
})();
