/* Screen-space illustration rig, not calibration or hardware commands.
 * Rod identities follow docs/hardware_motor_protocol.md.
 * Human controller is front-facing: character-right appears screen-left.
 */
(() => {
  const scale = 1.05;
  const neckOrigin = [150, 136];
  const neckAnchor = [0, -33];
  const rods = Object.freeze({
    wusong_right: {label: '右手', side: 'left', shoulder: [-20, -16]},
    wusong_left: {label: '左手', side: 'right', shoulder: [22, -16]},
    wusong_neck: {label: '颈部主杆', anchor: neckAnchor},
    tiger_head: {label: '耳部头杆', anchor: [-100, -75]},
    tiger_tail: {label: '尾部后端杆', anchor: [157, -118]}
  });
  const humanIds = ['wusong_right', 'wusong_left', 'wusong_neck'];
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function resolveHuman(input) {
    const points = Object.fromEntries(humanIds.map(id => [id, [...input[id]]]));
    const neck = points.wusong_neck;
    neck[0] = clamp(neck[0], 125, 175);
    neck[1] = clamp(neck[1], 116, 156);
    for (const id of humanIds.slice(0, 2)) {
      const shoulder = rods[id].shoulder;
      const sx = neck[0] + shoulder[0] / scale;
      const sy = neck[1] + (shoulder[1] - neckAnchor[1]) / scale;
      const point = points[id];
      point[0] = clamp(point[0], 28, 272);
      point[1] = clamp(point[1], 40, 260);
      const dx = point[0] - sx, dy = point[1] - sy, d = Math.hypot(dx, dy);
      // Clamp the visible handle as well as the drawing, avoiding false point correspondence.
      if (d > 126 / scale) {
        point[0] = sx + dx / d * 126 / scale;
        point[1] = sy + dy / d * 126 / scale;
      }
    }
    return points;
  }
  function projectHuman(points) {
    const offset = points.wusong_neck.map((v, i) => (v - neckOrigin[i]) * scale);
    const hands = {};
    for (const id of humanIds.slice(0, 2)) {
      hands[rods[id].side] = points[id].map((v, i) => (v - neckOrigin[i]) * scale + neckAnchor[i] - offset[i]);
    }
    return {offset, hands};
  }
  const rig = {rods, humanIds, scale, neckOrigin, neckAnchor, resolveHuman, projectHuman};
  if (typeof module !== 'undefined' && module.exports) module.exports = rig;
  else window.TheatreRig = rig;
})();
