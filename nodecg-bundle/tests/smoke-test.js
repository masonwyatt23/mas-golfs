'use strict';
/* Mas Golfs NodeCG bundle — stub smoke test.
 *
 * Runs the extension with a stubbed nodecg object in MAS_GOLFS_DEMO=1 mode
 * (no sim engine, no event bus, no `ws` dependency), drives two full demo
 * shot cycles (strike -> apex -> landing -> hole_end) by invoking the
 * captured interval callback, and asserts the replicant writes — including
 * the Wyatt National v3 yardages and the live-distance counter fields
 * (target_yards on strike, carry on apex, total on landing, outcome fields
 * cleared on the next strike).
 *
 * Also verifies the placeholder copies agree (placeholder.js vs
 * placeholder-data.json), the v3 course table sums, and the lower-third
 * graphic carries the live-distance counter.
 *
 * Usage: node tests/smoke-test.js   (exit 0 = pass)
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..');
let failures = 0;
function check(name, fn) {
  try {
    fn();
    console.log('PASS', name);
  } catch (err) {
    failures += 1;
    console.error('FAIL', name, '-', err.message);
  }
}

// --- 1. Placeholder copies agree --------------------------------------------
check('placeholder.js matches placeholder-data.json', () => {
  const json = JSON.parse(fs.readFileSync(path.join(ROOT, 'shared', 'placeholder-data.json'), 'utf8'));
  const sandbox = { window: {} };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, 'shared', 'placeholder.js'), 'utf8'), sandbox);
  // Round-trip through JSON: the vm context's objects carry another realm's
  // Object.prototype, which deepStrictEqual would reject on prototype
  // grounds alone even when every value matches.
  const fromJs = JSON.parse(JSON.stringify(sandbox.window.MAS_PLACEHOLDER));
  assert.deepStrictEqual(fromJs, json);
});

// --- 2. v3 course table -------------------------------------------------------
check('Wyatt National v3 course table sums to 7,602 (front 3,808 / back 3,794)', () => {
  const json = JSON.parse(fs.readFileSync(path.join(ROOT, 'shared', 'placeholder-data.json'), 'utf8'));
  const c = json.course;
  assert.strictEqual(c.name, 'Wyatt National');
  assert.strictEqual(c.par, 72);
  assert.strictEqual(c.holes.length, 18);
  const front = c.holes.slice(0, 9).reduce((s, h) => s + h.yards, 0);
  const back = c.holes.slice(9).reduce((s, h) => s + h.yards, 0);
  assert.strictEqual(front, 3808);
  assert.strictEqual(back, 3794);
  assert.strictEqual(c.yards, 7602);
  assert.strictEqual(c.holes[11].name, 'The Picture');
  assert.strictEqual(c.holes[11].par, 3);
  assert.strictEqual(c.holes[11].yards, 172);
});

// --- 3. Extension demo cycle with a stubbed nodecg ---------------------------
process.env.MAS_GOLFS_DEMO = '1';

const replicants = {};
const messages = [];
function makeReplicant(name, defaultValue) {
  let value = defaultValue;
  const listeners = [];
  const rep = {
    get value() { return value; },
    set value(v) {
      value = v;
      listeners.forEach((fn) => fn(v));
    },
    on(event, fn) { if (event === 'change') listeners.push(fn); }
  };
  replicants[name] = rep;
  return rep;
}
const nodecgStub = {
  Replicant: (name, opts) => makeReplicant(name, opts && opts.defaultValue),
  sendMessage: (msg, data) => messages.push({ msg, data }),
  listenFor: () => {},
  log: { info: () => {}, warn: () => {}, error: () => {}, debug: () => {} }
};

// Capture the demo simulator's interval instead of waiting ~36 s per cycle.
const intervals = [];
const realSetInterval = global.setInterval;
global.setInterval = (fn) => { intervals.push(fn); return intervals.length; };

require(path.join(ROOT, 'extension', 'index.js'))(nodecgStub);
global.setInterval = realSetInterval;

check('demo simulator registered one interval', () => {
  assert.strictEqual(intervals.length, 1);
});
const tick = intervals[0];

function shotData() { return replicants.shotData.value; }
function lowerThird() { return replicants.lowerThird.value; }

check('strike writes target_yards 172 and clears previous outcome fields', () => {
  tick(); // strike
  assert.strictEqual(shotData().club, '7-iron');
  assert.strictEqual(shotData().ball_speed_mph, 132);
  assert.strictEqual(shotData().target_yards, 172);
  assert.strictEqual(shotData().carry_yds, null);
  assert.strictEqual(shotData().total_yds, null);
  assert.strictEqual(lowerThird().variant, 'shot');
  assert.ok(lowerThird().title.includes('172 YDS'), lowerThird().title);
});
check('apex writes the real carry (166) and apex height', () => {
  tick(); // apex
  assert.strictEqual(shotData().apex_ft, 78);
  assert.strictEqual(shotData().carry_yds, 166);
  assert.strictEqual(shotData().shape, 'draw');
});
check('landing writes total 172 and the lastShot line', () => {
  tick(); // landing
  assert.strictEqual(shotData().total_yds, 172);
  assert.strictEqual(shotData().lie, 'green');
  assert.strictEqual(shotData().dist_to_pin_ft, 12);
  assert.ok(replicants.lastShot.value.includes('172'), replicants.lastShot.value);
});
check('hole_end advances the round and fires the hole-result lower-third', () => {
  const thruBefore = replicants.roundState.value.thru;
  tick(); // hole_end
  assert.strictEqual(replicants.roundState.value.thru, thruBefore + 1);
  assert.strictEqual(lowerThird().variant, 'holeResult');
  assert.ok(lowerThird().title.includes('HOLE 12'), lowerThird().title);
});
check('second strike clears the previous shot carry/total (counter restarts)', () => {
  tick(); // strike, second cycle
  assert.strictEqual(shotData().carry_yds, null);
  assert.strictEqual(shotData().total_yds, null);
  assert.strictEqual(shotData().target_yards, 172);
});

// --- 4. Lower-third graphic carries the live-distance counter ---------------
check('lower-third.html has the live-distance counter', () => {
  const html = fs.readFileSync(path.join(ROOT, 'graphics', 'lower-third.html'), 'utf8');
  assert.ok(html.includes('id="ltDist"'), 'missing #ltDist element');
  assert.ok(html.includes('CARRIED '), 'missing CARRIED readout');
  assert.ok(html.includes('TOTAL '), 'missing TOTAL readout');
  assert.ok(html.includes('requestAnimationFrame'), 'missing rAF animation');
  assert.ok(html.includes("makeReplicant('shotData'"), 'not subscribed to shotData');
  assert.ok(html.includes('8000'), 'shot variant should hold 8 s');
});

// --- 5. No stale v1/v2 yardage left in the bundle ----------------------------
check('no stale 164-yard hole 12 references remain', () => {
  const hits = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name === 'node_modules') continue;
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (/\.(js|json|html|md)$/.test(entry.name)) {
        const text = fs.readFileSync(p, 'utf8');
        if (p.endsWith('smoke-test.js')) continue;
        if (/164 YDS|from 164|yards":164|"yards": 164/.test(text)) hits.push(p);
      }
    }
  }
  walk(ROOT);
  assert.deepStrictEqual(hits, []);
});

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll smoke-test checks passed.');
