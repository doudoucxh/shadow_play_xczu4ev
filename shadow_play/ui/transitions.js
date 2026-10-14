/* Decorative page turn only. Navigation never depends on animation completion. */
(() => {
  const layer = document.querySelector('#paper-turn');
  const leaf = layer.querySelector('.paper-leaf');
  const shadow = layer.querySelector('.paper-shadow');
  const glint = layer.querySelector('.paper-curl');
  const main = document.querySelector('#main');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let animations = [], fallback = 0, revision = 0;

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
    const timing = {duration:1450,easing:'cubic-bezier(.36,.02,.22,1)',fill:'forwards'};
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
      fallback = setTimeout(()=>{if(revision===current) finish();},1800);
    } catch { finish(); }
  }
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!layer.hidden)finish();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)finish();});
  reducedMotion.addEventListener('change',event=>{if(event.matches)finish();});
  window.TheatrePageTurn = {play,finish};
})();
