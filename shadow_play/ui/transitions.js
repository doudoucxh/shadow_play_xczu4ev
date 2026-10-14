/* Decorative page turn only. Navigation never depends on animation completion. */
(() => {
  const layer = document.querySelector('#paper-turn');
  const leaf = layer.querySelector('.paper-leaf');
  const shadow = layer.querySelector('.paper-shadow');
  const glint = layer.querySelector('.paper-curl');
  const main = document.querySelector('#main');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const TURN_DURATION = 3200;
  let animations = [], fallback = 0, revision = 0;

  // Code-native singed paper: charcoal, a broken hot seam and small flame tongues.
  const seam = 'M70 0L64 30 69 58 57 84 63 114 52 141 59 172 68 197 60 225 67 251 54 278 62 307 51 335 63 364 57 395 68 421 59 451 65 480 53 510 60 541 49 568 61 598 56 627 67 655 58 684 64 713 52 744 62 774 55 804 66 834 59 865 65 900';
  document.querySelectorAll('.burn-edge').forEach((edge,index)=>{
    const id = `ember-glow-${index}`;
    edge.innerHTML = `<svg viewBox="0 0 80 900" preserveAspectRatio="none" aria-hidden="true"><defs><filter id="${id}" x="-200%" y="-20%" width="500%" height="140%"><feGaussianBlur stdDeviation="4"/></filter></defs><path d="${seam}H80V0Z" fill="#130b07"/><path class="ember-halo" d="${seam}" fill="none" stroke="#ed4b13" stroke-width="14" filter="url(#${id})"/><path d="${seam}" fill="none" stroke="#963115" stroke-width="5"/><path class="ember-seam" d="${seam}" fill="none" stroke="#ffa247" stroke-width="1.7" stroke-dasharray="39 13 7 18 25 31"/>${[84,225,364,510,655,804].map((y,i)=>`<path class="edge-flame" style="--f-delay:-${i*.63}s" d="M62 ${y+13}Q37 ${y-3} 55 ${y-29}Q48 ${y-12} 64 ${y-2}Q73 ${y+6} 62 ${y+13}Z" fill="#ed7626"/>`).join('')}</svg>`;
  });
  document.querySelectorAll('.ember-field').forEach(field=>{
    const paper = field.classList.contains('paper-embers');
    const count = paper ? 10 : 30;
    field.innerHTML = Array.from({length:count},(_,i)=>{
      const x = paper ? 93+(i*3%7) : (i*37+11)%100;
      const duration = paper ? 3.5+(i%4)*.7 : 10+(i%7)*1.8;
      return `<i class="falling-ember" style="--x:${x}%;--size:${i%5===0?4:2}px;--drift:${paper?-26-(i%4)*12:(i%2?1:-1)*(25+i%6*14)}px;--fall-time:${duration}s;--fall-delay:-${(i*.91)%duration}s;--turn:${i%2?240:-210}deg"></i>`;
    }).join('');
  });
  const suspendEffects = () => document.body.classList.toggle('effects-suspended',document.hidden);
  document.addEventListener('visibilitychange',suspendEffects);
  suspendEffects();

  function finish() {
    revision++;
    clearTimeout(fallback);
    animations.forEach(animation => animation.cancel());
    animations = [];
    const wasTurning = !layer.hidden;
    layer.hidden = true;
    main.inert = false;
    main.removeAttribute('aria-busy');
    document.body.classList.remove('turning-page');
    if (wasTurning) main.focus({preventScroll:true});
  }

  function play(mode, disabled = false) {
    finish();
    if (disabled || reducedMotion.matches || typeof leaf.animate !== 'function') return;
    const titles = {classic:['壹','经典传唱','一声唱腔，千古回响'],touch:['贰','指尖皮影','以手执影，让旧戏新生'],pose:['叁','以身入戏','身入其境，影续千年']};
    const [number,title,verse] = titles[mode];
    layer.querySelector('.paper-chapter').textContent = `第 ${number} 折`;
    layer.querySelector('.paper-title').textContent = title;
    layer.querySelector('.paper-verse').textContent = verse;
    layer.dataset.mode = mode;
    layer.hidden = false;
    main.inert = true;
    main.setAttribute('aria-busy','true');
    document.body.classList.add('turning-page');
    const current = revision;
    const timing = {duration:TURN_DURATION,easing:'cubic-bezier(.36,.02,.22,1)',fill:'forwards'};
    try {
      animations = [
        leaf.animate([
          {transform:'rotateY(0deg) rotateZ(0deg)',opacity:1,offset:0},
          {transform:'rotateY(-3deg) rotateZ(-.2deg)',opacity:1,offset:.2},
          {transform:'rotateY(-48deg) rotateZ(-1.6deg)',opacity:1,offset:.56},
          {transform:'rotateY(-106deg) rotateZ(-3deg)',opacity:1,offset:.86},
          {transform:'rotateY(-132deg) rotateZ(-4deg)',opacity:0,offset:1}
        ],timing),
        shadow.animate([{opacity:.64},{opacity:.5,offset:.3},{opacity:0}],timing),
        glint.animate([
          {transform:'translateX(35%)',opacity:0},
          {transform:'translateX(-10%)',opacity:.9,offset:.35},
          {transform:'translateX(-85%)',opacity:1,offset:.75},
          {transform:'translateX(-115%)',opacity:0}
        ],timing)
      ];
      Promise.all(animations.map(animation=>animation.finished)).then(()=>{
        if(revision===current) finish();
      }).catch(()=>{if(revision===current) finish();});
      // A suspended tab or interrupted animation must never leave the controls blocked.
      fallback = setTimeout(()=>{if(revision===current) finish();},TURN_DURATION+400);
    } catch { finish(); }
  }
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!layer.hidden)finish();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)finish();});
  reducedMotion.addEventListener('change',event=>{if(event.matches)finish();});
  window.TheatrePageTurn = {play,finish};
})();
