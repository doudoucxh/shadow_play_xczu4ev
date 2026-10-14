const {test} = require('node:test');
const assert = require('node:assert/strict');
const {rods, humanIds, resolveHuman, projectHuman} = require('./rig.js');
const rest = {wusong_right:[65,184],wusong_left:[235,184],wusong_neck:[150,136]};
const close = (actual, expected) => assert.ok(Math.abs(actual-expected)<1e-8, `${actual} != ${expected}`);

test('physical topology has three human rods and two tiger rods, without pelvis or feet controls', () => {
  assert.deepEqual(Object.keys(rods).sort(), ['tiger_head','tiger_tail','wusong_left','wusong_neck','wusong_right']);
  assert.equal(humanIds.length,3);
  assert.equal(rods.wusong_right.side,'left');
  assert.equal(rods.wusong_left.side,'right');
  assert.deepEqual(rods.wusong_neck.anchor,[0,-33]);
});

test('moving the neck moves the neck anchor while reachable wrist handles retain their world positions', () => {
  const shifted={...rest,wusong_neck:[164,124]};
  const points=resolveHuman(shifted), mapped=projectHuman(points);
  close(mapped.offset[0],14*1.05);
  close(mapped.offset[1],-12*1.05);
  for(const [id,side] of [['wusong_right','left'],['wusong_left','right']]) {
    close(mapped.hands[side][0]+mapped.offset[0],(rest[id][0]-150)*1.05);
    close(mapped.hands[side][1]+mapped.offset[1],(rest[id][1]-136)*1.05-33);
  }
  assert.deepEqual(rest.wusong_neck,[150,136]);
});

test('unreachable UI handles are constrained together with illustrated wrists', () => {
  const points=resolveHuman({wusong_right:[-100,600],wusong_left:[800,-200],wusong_neck:[200,50]});
  const mapped=projectHuman(points);
  assert.deepEqual(points.wusong_neck,[175,116]);
  for(const [id,side] of [['wusong_right','left'],['wusong_left','right']]) {
    const wrist=mapped.hands[side],shoulder=rods[id].shoulder;
    assert.ok(Math.hypot(wrist[0]-shoulder[0],wrist[1]-shoulder[1])<=126+1e-8);
    close((wrist[0]+mapped.offset[0])/1.05+150,points[id][0]);
    close((wrist[1]+mapped.offset[1]+33)/1.05+136,points[id][1]);
  }
});
