/* Code-native paper-cut illustrations adapted from user-provided visual references.
 * Rod topology follows TheatreRig; SVG coordinates are not measured attachment pixels.
 * Source photographs stay outside Git. */
(() => {
  let serial = 0;
  const flower = (x, y, r = 8) => `<g transform="translate(${x} ${y})" fill="none" stroke="#f5d8a1" stroke-width="1.4"><circle r="${r}"/><path d="M-${r} 0H${r}M0 -${r}V${r}M-${r*.7} -${r*.7}L${r*.7} ${r*.7}M-${r*.7} ${r*.7}L${r*.7} -${r*.7}"/><circle r="2" fill="#f5d8a1"/></g>`;
  const {rods} = window.TheatreRig;
  function anchor(id, x, y, hand = false) {
    return `<g class="rod-anchor ${hand ? 'hand-anchor' : ''}" data-rod="${id}" transform="translate(${x} ${y})"><title>${rods[id].label}</title><circle class="anchor-ring" r="8"/><circle class="anchor-core" r="3"/><text class="anchor-label" x="${id==='wusong_neck' ? 18 : 0}" y="${id==='wusong_neck' ? 5 : -16}" text-anchor="${id==='wusong_neck' ? 'start' : 'middle'}">${rods[id].label}</text></g>`;
  }
  function arm(side) {
    const id = side === 'left' ? 'wusong_right' : 'wusong_left';
    return `<g class="puppet-arm" data-arm="${side}">
      <path class="upper" fill="none" stroke="#63512c" stroke-width="21" stroke-linecap="round"/>
      <path class="upper-color" fill="none" stroke="#517d49" stroke-width="17" stroke-linecap="round"/>
      <path class="upper-trim" fill="none" stroke="#dfb956" stroke-width="3" stroke-dasharray="2 7"/>
      <path class="lower" fill="none" stroke="#71592e" stroke-width="15" stroke-linecap="round"/>
      <path class="lower-color" fill="none" stroke="#b94c2d" stroke-width="11" stroke-linecap="round"/>
      <path class="lower-trim" fill="none" stroke="#e5bb58" stroke-width="3" stroke-dasharray="3 8"/>
      <circle class="elbow" r="3" fill="#ebcb72" stroke="#69522b"/>
      <circle class="wrist" r="5" fill="#ead09b" stroke="#69522b" stroke-width="1.5"/>
      <path class="rod" fill="none" stroke="#9d8547" stroke-width="2" opacity=".65"/>
      ${anchor(id, 0, 0, true)}
    </g>`;
  }
  function person() {
    return `<g class="puppet-person"><g class="person-body">
      <g stroke="#65512e" stroke-width="1.6" stroke-linejoin="round">
        <path d="M-25 76L-31 132L-43 155L-26 162L-5 134L5 88M13 83L12 137L26 158L43 153L34 129L35 78" fill="#4b7f45"/>
        <path d="M-27 92L-26 129M-19 93L-21 130M-11 94L-16 129M19 94L18 130M27 92L26 130M33 90L32 126" stroke="#dcbd61" stroke-width="1"/>
        <path d="M-42 153L-27 158L-31 170L-47 166M26 155L42 152L48 164L31 170" fill="#eee3bb"/>
        <path d="M-47 164L-29 168L-31 176L-58 178Q-65 176 -61 170ZM30 167L46 161L57 170Q65 176 55 178L32 177Z" fill="#3d3429"/>
        <path d="M-59 176L-32 175M34 175H56" stroke="#d8c99e" stroke-width="1"/>
      </g>
      <g stroke="#71552c" stroke-width="1.5" stroke-linejoin="round">
        <path d="M-21 -23Q0 -31 23 -21L22 26L33 53L42 94Q5 105 -35 93L-30 55L-21 25Z" fill="#53794a"/>
        <path d="M-14 -20L-3 1L16 -20L20 24L-17 28Z" fill="#e0b754"/>
        <path d="M-22 27Q1 34 25 25L29 38L-24 43Z" fill="#c5a043"/>
        <path d="M-27 42Q0 51 29 40L36 80Q4 94 -32 79Z" fill="#d7ac48"/>
        <path d="M-29 72Q6 86 34 70M-31 80Q5 96 38 79M-34 90Q6 103 40 89" fill="none" stroke="#315c3f" stroke-width="3"/>
        <path d="M-24 45Q-13 50 -25 60Q-12 62 -25 72M26 44Q13 50 27 59Q14 64 31 70" fill="none" stroke="#8f5a2c"/>
        <path d="M-16 -18L-7 -4M14 -18L4 -4M-17 6L17 5M-16 18L17 17" stroke="#f3df9a" stroke-dasharray="2 3"/>
        <path d="M-21 30L-9 34L-15 61L-4 53L3 35L13 37L22 63L26 53L21 30" fill="#b34730"/>
        <circle cy="35" r="5" fill="#e8c268"/>
        <path d="M-9 -27L-7 -47L9 -47L13 -24Z" fill="#e7d1a2"/>
        <path d="M-13 -79Q1 -96 17 -81L20 -66L30 -60L22 -56L21 -43Q10 -32 -3 -43L-12 -59Z" fill="#eadbb2"/>
        <path d="M-17 -62Q-24 -88 -8 -99L14 -96L20 -82L10 -75L-4 -77L-4 -57Z" fill="#40352a"/>
        <path d="M-19 -90Q-4 -112 21 -95L16 -84Q-2 -97 -19 -79Z" fill="#ede4c2"/>
        <path d="M-15 -94Q-2 -110 13 -98M-15 -88Q2 -101 18 -90M-14 -84Q2 -93 15 -85" fill="none" stroke="#bba064"/>
        <path d="M-14 -100Q-31 -124 -39 -109Q-41 -97 -25 -96Q-45 -97 -52 -86Q-36 -88 -25 -83Q-47 -80 -55 -66Q-33 -74 -19 -70" fill="none" stroke="#cabc99" stroke-width="4"/>
        <path d="M-17 -89Q-36 -91 -35 -73Q-31 -63 -16 -67Q-30 -58 -32 -42L-18 -48L-21 -29" fill="none" stroke="#46372a" stroke-width="3"/>
        <path d="M-14 -86Q3 -96 18 -84" fill="none" stroke="#467146" stroke-width="5"/>
        <circle cx="3" cy="-91" r="4" fill="#ae3e29" stroke="#e4ba58"/>
        <path d="M9 -69L19 -68M12 -66L18 -65M21 -48L15 -48" fill="none" stroke="#4e392a" stroke-width="1.5"/>
        <path d="M-1 -64Q-11 -68 -8 -57L-2 -54" fill="none" stroke="#967b4c"/>
      </g>
      ${flower(-9,60,6)}${flower(12,60,6)}${flower(0,9,5)}
      <g fill="#ac3f2c"><circle cx="-9" cy="60" r="2.5"/><circle cx="12" cy="60" r="2.5"/><circle cy="9" r="2"/></g>
      ${arm('left')}${arm('right')}
      <path d="M0 -33L-2 238" stroke="#9d8547" stroke-width="2.5" opacity=".65"/>
      ${anchor('wusong_neck',...rods.wusong_neck.anchor)}
    </g></g>`;
  }
  function tiger() {
    return `<g class="puppet-tiger">
      <g stroke-linecap="round" stroke-linejoin="round">
        <path d="M77 -24Q104 -69 137 -91Q159 -103 157 -118Q153 -138 169 -140Q182 -138 172 -129" fill="none" stroke="#6d4a2b" stroke-width="12"/>
        <path d="M77 -24Q104 -69 137 -91Q159 -103 157 -118Q153 -138 169 -140Q182 -138 172 -129" fill="none" stroke="#d59b45" stroke-width="9"/>
        <path d="M77 -24Q104 -69 137 -91Q159 -103 157 -118Q153 -138 169 -140Q182 -138 172 -129" fill="none" stroke="#51402b" stroke-width="9" stroke-dasharray="5 10"/>
        <g stroke="#74502c" stroke-width="1.7">
          <path d="M-58 4L-49 47L-65 58Q-80 61 -79 69L-51 71L-35 55L-31 6M43 1Q72 22 54 42L37 59Q29 69 43 72L70 68L85 45L81 3" fill="#b77532"/>
          <path d="M-74 -38Q-43 -53 11 -45Q55 -55 85 -30Q100 -5 82 22Q58 36 27 17L-35 19Q-64 35 -80 13L-90 -15Z" fill="#d99c43"/>
          <path d="M-77 -34Q-84 -67 -106 -73L-130 -61L-136 -38L-153 -34L-155 -22L-137 -7L-112 1Q-86 3 -68 -19" fill="#d99c43"/>
          <path d="M-114 -65Q-125 -91 -112 -98Q-98 -102 -93 -80L-86 -72" fill="#dca448"/>
          <path d="M-108 -86Q-111 -96 -105 -91L-101 -81" fill="#47392a" stroke="none"/>
          <path d="M-139 -46Q-150 -46 -150 -38L-139 -32L-127 -36" fill="#e6b25c"/>
          <path d="M-150 -30L-140 -29L-143 -24L-151 -25Z" fill="#523729"/>
          <path d="M-149 -20Q-134 -9 -119 -17L-127 -4L-143 -6L-153 -15Z" fill="#b84228"/>
          <path d="M-147 -18L-141 -8L-138 -14M-129 -13L-128 -5L-122 -15" fill="#f6e4b0" stroke="none"/>
          <path d="M-86 -1L-88 45L-105 57Q-113 65 -104 69L-77 69L-66 57L-61 4" fill="#d69a42"/>
          <path d="M59 9Q87 29 67 46L52 54Q49 61 58 66L79 67L96 47Q108 29 91 14" fill="#d69a42"/>
        </g>
        <g fill="#4e3d2a">
          <path d="M-56 -45Q-59 -21 -47 -6Q-48 -29 -43 -47ZM-31 -46Q-37 -25 -23 -9Q-27 -31 -18 -45ZM-5 -44Q-16 -22 0 -4Q-3 -25 7 -46ZM23 -46Q11 -26 26 -8Q24 -30 35 -45ZM48 -43Q33 -27 49 -9Q48 -23 60 -37ZM75 -33Q57 -20 76 -4Q74 -20 86 -21Z"/>
          <path d="M-51 20Q-37 8 -42 -6Q-33 6 -32 19ZM-17 19Q-10 7 -15 -5Q0 5 -4 19ZM16 17Q25 4 23 -3Q36 6 31 19ZM63 25Q47 11 51 3Q62 12 79 16Z"/>
          <path d="M-85 -57Q-96 -46 -82 -35L-88 -30Q-105 -45 -94 -64ZM-105 -68Q-121 -54 -108 -43L-116 -39Q-131 -55 -116 -70ZM-79 -28Q-91 -21 -83 -10Q-101 -12 -96 -25Z"/>
          <path d="M-81 18L-66 27L-65 33L-83 26ZM-85 39L-68 43L-70 49L-86 46ZM82 29L98 33L98 40L78 36ZM65 49L87 50L82 56L59 55Z"/>
        </g>
        <path d="M-135 -51Q-123 -59 -117 -48L-127 -44Z" fill="#ece0a9" stroke="#59412b" stroke-width="1.4"/>
        <circle cx="-128" cy="-50" r="2.7" fill="#372e25"/>
        <g fill="none" stroke="#5d452b" stroke-width="1.2"><path d="M-147 -22L-165 -27M-145 -19L-165 -17M-142 -15L-158 -9M-104 62L-104 68M-98 61L-97 68M-91 61L-90 68M63 60L63 65M69 60L69 66M75 60L75 66"/></g>
      </g>
      <path d="M-100 -75L-100 202M157 -118L158 202" fill="none" stroke="#9d8547" stroke-width="2.5" opacity=".65"/>
      ${anchor('tiger_head',...rods.tiger_head.anchor)}${anchor('tiger_tail',...rods.tiger_tail.anchor)}
    </g>`;
  }
  function stage({single = false, hero = false, points = false} = {}) {
    const id = `scene-${++serial}`;
    return `<svg class="theatre-art ${hero ? 'hero-art' : ''} ${points ? 'show-anchors' : ''}" viewBox="0 0 860 480" role="img" aria-label="${single ? '武松皮影动画预览' : '景阳冈上，武松与老虎的皮影戏台'}"><defs><linearGradient id="${id}-sky" x2="0" y2="1"><stop stop-color="#f2e6cc"/><stop offset="1" stop-color="#f8f1df"/></linearGradient><radialGradient id="${id}-light"><stop stop-color="#fff9dc" stop-opacity=".85"/><stop offset="1" stop-color="#fff9dc" stop-opacity="0"/></radialGradient><pattern id="${id}-grain" width="7" height="7" patternUnits="userSpaceOnUse"><circle cx="1" cy="2" r=".55" fill="#786448" opacity=".11"/><circle cx="5" cy="5" r=".4" fill="#786448" opacity=".1"/></pattern></defs><rect x="1" y="1" width="858" height="478" fill="url(#${id}-sky)"/><ellipse cx="430" cy="240" rx="390" ry="250" fill="url(#${id}-light)"/><circle class="stage-sun" cx="574" cy="152" r="94" fill="#bd6449" opacity=".19"/><circle cx="574" cy="152" r="107" fill="none" stroke="#b87d51" opacity=".18"/><g fill="none" stroke="#b5a17a" opacity=".35"><path d="M0 279L82 208L129 249L244 132L352 257L439 209L527 282L622 203L752 292L860 229"/><path d="M75 279L171 224L261 275L328 215L454 302L576 245L696 310L777 263L860 306"/><path d="M244 132L222 216L263 203L252 237M622 203L604 253L627 247"/></g><path d="M0 342Q123 288 244 329T478 333T710 321T860 333V480H0Z" fill="#c8b88d" opacity=".2"/><path d="M0 387Q165 344 335 379T622 373T860 389" fill="none" stroke="#a38b60" opacity=".45"/><g class="cloud cloud-one" stroke="#baa47a" fill="none" opacity=".45" stroke-width="1.3"><path d="M78 112H194Q213 112 207 101Q200 90 190 101Q181 74 159 87Q144 62 124 86Q101 79 99 99H72"/><path d="M101 120H227M68 128H148"/></g><g class="cloud cloud-two" stroke="#baa47a" fill="none" opacity=".45"><path d="M490 62H614Q631 62 622 53Q613 44 606 54Q594 27 575 44Q551 22 535 48H503M547 72H647"/></g><g fill="#5c6243" opacity=".78"><path d="M780 379Q752 245 781 104L789 100Q766 244 797 386Z"/><path d="M778 197L718 150L710 150L776 212M778 153L829 119L827 112L779 143M779 256L832 220L832 211L778 242"/><path d="M671 151Q692 125 719 127Q740 119 761 147Q720 158 671 151M749 107Q765 79 794 85Q815 67 848 105Q796 114 749 107M793 220Q822 189 858 211L860 226Z"/></g><g fill="none" stroke="#72714e" opacity=".7"><path d="M91 393L73 360M91 393L100 354M91 393L118 372M711 393L700 369M711 393L724 363"/><path d="M59 399Q93 388 126 398M677 399Q710 390 742 396"/></g><g class="actor-person" transform="translate(${single ? 427 : 310} 229) scale(1.05)">${person()}</g>${single ? '' : `<g class="actor-tiger" transform="translate(588 305) scale(.93)">${tiger()}</g>`}<g fill="none" stroke="#9e7850" opacity=".5"><path d="M20 69V20H69M791 20H840V69M20 411V460H69M791 460H840V411"/><path d="M27 57V27H57M803 27H833V57M27 423V453H57M803 453H833V423"/></g><text x="813" y="282" fill="#807151" font-family="serif" font-size="15" writing-mode="vertical-rl" letter-spacing="7">景陽岡</text><rect width="860" height="480" fill="url(#${id}-grain)" pointer-events="none"/></svg>`;
  }
  function setPose(root, left = [-81, -46], right = [102, -24], lean = 0) {
    if (!root) return;
    root.querySelectorAll('.person-body').forEach(b => b.setAttribute('transform', `rotate(${lean} 0 -33)`));
    for (const [side, point] of [['left', left], ['right', right]]) {
      root.querySelectorAll(`[data-arm="${side}"]`).forEach(g => {
        const sx = side === 'left' ? -20 : 22, sy = -16;
        let dx = point[0] - sx, dy = point[1] - sy;
        const length = Math.hypot(dx, dy) || 1, d = Math.max(10, Math.min(126, length));
        dx = dx / length * d; dy = dy / length * d;
        const hx = sx + dx, hy = sy + dy, h = Math.sqrt(65 ** 2 - (d / 2) ** 2);
        // Choose the lower elbow solution for the flat UI puppet.
        const sign = dx === 0 ? (side === 'left' ? 1 : -1) : Math.sign(dx);
        const ex = sx + dx / 2 - sign * dy / d * h, ey = sy + dy / 2 + sign * dx / d * h;
        for (const c of ['upper', 'upper-color', 'upper-trim']) g.querySelector('.' + c).setAttribute('d', `M${sx} ${sy}L${ex} ${ey}`);
        for (const c of ['lower', 'lower-color', 'lower-trim']) g.querySelector('.' + c).setAttribute('d', `M${ex} ${ey}L${hx} ${hy}`);
        for (const [c, x, y] of [['elbow', ex, ey], ['wrist', hx, hy]]) { g.querySelector('.'+c).setAttribute('cx', x); g.querySelector('.'+c).setAttribute('cy', y); }
        g.querySelector('.hand-anchor').setAttribute('transform', `translate(${hx} ${hy})`);
        g.querySelector('.rod').setAttribute('d', `M${hx} ${hy}L${hx + 18} 238`);
      });
    }
  }
  const icons = {
    play: '<path d="m9 5 11 7-11 7Z"/>',
    touch: '<circle cx="12" cy="5" r="2"/><path d="M12 10v7m-6-5 6-3 6 3M12 17l-5 5m5-5 5 5M3 6V2h4m10 0h4v4"/>',
    pose: '<circle cx="12" cy="5" r="2"/><path d="m3 9 9 3 9-3m-9 3v6m0 0-6 4m6-4 6 4"/>',
    arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    reset: '<path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/>',
    book: '<path d="M12 6Q6 2 2 5v15q5-3 10 0 5-3 10 0V5q-4-3-10 1Zm0 0v14"/>',
    spark: '<path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z"/>'
  };
  function icon(name) { return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.arrow}</svg>`; }
  window.TheatreArt = {stage, setPose, icon};
})();
