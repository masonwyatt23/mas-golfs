'use strict';
/* Mas Golfs — Clubhouse Coins bridge tests.
 *
 * Covers the mirror in extension/coins-bridge.js: market open/close/
 * resolve from bus events, the per-shot market selection, the putt
 * refinement, the Monday 00:00 ET weekly reset boundary, the economy
 * snapshot merge, and the structural guarantee that the bridge never
 * computes payouts (it mirrors state only).
 *
 * Usage: node tests/coins-bridge-test.js   (exit 0 = pass)
 */
const assert = require('assert');
const { createCoinsBridge } = require('../extension/coins-bridge');

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

function ev(event, data, round, hole) {
  return { event, data: data || {}, round: round != null ? round : 47, hole: hole != null ? hole : 12 };
}
function makeBridge(now) {
  return createCoinsBridge({ log: { info: () => {}, warn: () => {}, debug: () => {} }, now: now || (() => new Date()) });
}
function marketsOf(b) { return b.toMarkets().markets; }
function byId(b, id) { return marketsOf(b).find((m) => m.market_id === id); }

// --- Odds math (mirror of coins/odds.py) --------------------------------------
check('opening odds have no overround (par-3 birdie rate 0.12 -> 8.33 / 1.14)', () => {
  const b = makeBridge();
  const o = b._odds.openingOdds({ yes: 0.12, no: 0.88 });
  assert.deepStrictEqual(o, { yes: 8.33, no: 1.14 });
  assert.ok(Math.abs(1 / o.yes + 1 / o.no - 1) < 0.005, 'overround too large');
});
check('adjustProbability clamps form, hole, and condition factors', () => {
  const b = makeBridge();
  assert.strictEqual(b._odds.adjustProbability(0.5, 2, 1, 1), 0.575); // form clamped to 1.15
  assert.strictEqual(b._odds.adjustProbability(0.5, 0.1, 1, 1), 0.425); // form clamped to 0.85
  assert.strictEqual(b._odds.adjustProbability(0.99, 1.15, 1.3, 1.2), 0.98); // result clamped to P_MAX
  assert.strictEqual(b._odds.adjustProbability(0.01, 0.85, 0.7, 0.8), 0.02); // result clamped to P_MIN
});
check('blended odds with empty pools equal opening odds; with pools they move at most 25%', () => {
  const b = makeBridge();
  const opening = b._odds.openingOdds({ yes: 0.6, no: 0.4 });
  assert.deepStrictEqual(b._odds.blendedOdds(opening, { yes: 0.6, no: 0.4 }, { yes: 0, no: 0 }), opening);
  const blended = b._odds.blendedOdds(opening, { yes: 0.6, no: 0.4 }, { yes: 0, no: 1000 });
  // All the money on no: yes odds may rise, but no more than 25% above opening.
  assert.ok(blended.yes <= opening.yes * 1.25 + 0.005, `yes moved too far: ${blended.yes} vs ${opening.yes}`);
  assert.ok(blended.no >= opening.no * 0.75 - 0.005, `no moved too far: ${blended.no} vs ${opening.no}`);
  assert.ok(blended.yes > opening.yes, 'heavy no-side money should lengthen yes odds');
});

// --- Per-hole market ------------------------------------------------------------
check('hole_start opens the per-hole market with the par-based rate', () => {
  const b = makeBridge();
  b.onEvent(ev('round_start', {}, 47, 1));
  b.onEvent(ev('hole_start', { par: 3, yards: 172, hole_name: 'The Picture' }, 47, 12));
  const m = byId(b, 'r47-h12-hole');
  assert.ok(m, 'per-hole market missing');
  assert.strictEqual(m.question, 'Birdie or better on 12?');
  assert.strictEqual(m.status, 'open');
  assert.deepStrictEqual(m.odds, { yes: 8.33, no: 1.14 });
  assert.strictEqual(b.toPrediction().market_id, 'r47-h12-hole');
  assert.strictEqual(b.toPrediction().open, true);
});
check('hole_start uses the par-4 (6.25 / 1.19) and par-5 (3.33 / 1.43) rates', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  assert.deepStrictEqual(byId(b, 'r47-h1-hole').odds, { yes: 6.25, no: 1.19 });
  b.onEvent(ev('hole_start', { par: 5, yards: 612 }, 47, 2));
  assert.deepStrictEqual(byId(b, 'r47-h2-hole').odds, { yes: 3.33, no: 1.43 });
});

// --- Per-shot markets: fairway --------------------------------------------------
check('tee-shot decision opens a fairway market; strike closes it; landing resolves it', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b.onEvent(ev('decision', { club: 'Driver', shot_type: 'full', target_yards: 300, lie: 'tee', risk: 'normal' }, 47, 1));
  const m = byId(b, 'r47-h1-s1');
  assert.ok(m, 'fairway market missing');
  assert.strictEqual(m.question, 'Fairway on 1?');
  assert.deepStrictEqual(m.odds, { yes: 1.74, no: 2.35 });
  assert.strictEqual(b.toPrediction().market_id, 'r47-h1-s1');
  b.onEvent(ev('strike', { club: 'Driver' }, 47, 1));
  assert.strictEqual(byId(b, 'r47-h1-s1').status, 'closed');
  assert.strictEqual(byId(b, 'r47-h1-s1').open, false);
  b.onEvent(ev('landing', { fairway_hit: true, total_yds: 291, lie: 'fairway' }, 47, 1));
  assert.strictEqual(byId(b, 'r47-h1-s1').status, 'resolved');
  assert.strictEqual(byId(b, 'r47-h1-s1').winning_outcome, 'yes');
});
check('missed fairway resolves the fairway market no', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b.onEvent(ev('decision', { club: 'Driver', shot_type: 'full', target_yards: 300, lie: 'tee' }, 47, 1));
  b.onEvent(ev('strike', {}, 47, 1));
  b.onEvent(ev('landing', { fairway_hit: false, total_yds: 262, lie: 'rough' }, 47, 1));
  assert.strictEqual(byId(b, 'r47-h1-s1').winning_outcome, 'no');
});

// --- Per-shot markets: GIR, proximity, putt --------------------------------------
check('par-3 tee shot opens a GIR market (172 yd -> 1.67 / 2.5) and landing resolves it', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 3, yards: 172 }, 47, 12));
  b.onEvent(ev('decision', { club: '7-iron', shot_type: 'full', target_yards: 172, lie: 'tee' }, 47, 12));
  assert.strictEqual(byId(b, 'r47-h12-s1').question, 'GIR on 12?');
  assert.deepStrictEqual(byId(b, 'r47-h12-s1').odds, { yes: 1.67, no: 2.5 });
  b.onEvent(ev('strike', {}, 47, 12));
  b.onEvent(ev('landing', { on_green: false, total_yds: 158, lie: 'bunker' }, 47, 12));
  assert.strictEqual(byId(b, 'r47-h12-s1').winning_outcome, 'no');
});
check('pitch opens an inside-10-ft market resolved by dist_to_pin_ft', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b.onEvent(ev('decision', { club: 'Pitching wedge', shot_type: 'pitch', target_yards: 85, lie: 'rough' }, 47, 1));
  const m = byId(b, 'r47-h1-s1');
  assert.strictEqual(m.question, 'Inside 10 ft?');
  assert.deepStrictEqual(m.odds, { yes: 3.57, no: 1.39 });
  b.onEvent(ev('strike', {}, 47, 1));
  b.onEvent(ev('landing', { dist_to_pin_ft: 9, lie: 'green' }, 47, 1));
  assert.strictEqual(byId(b, 'r47-h1-s1').winning_outcome, 'yes');
  const b2 = makeBridge();
  b2.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b2.onEvent(ev('decision', { club: 'Pitching wedge', shot_type: 'pitch', target_yards: 85, lie: 'rough' }, 47, 1));
  b2.onEvent(ev('strike', {}, 47, 1));
  b2.onEvent(ev('landing', { dist_to_pin_ft: 25, lie: 'green' }, 47, 1));
  assert.strictEqual(byId(b2, 'r47-h1-s1').winning_outcome, 'no');
});
check('putt decision opens a one-putt market; putt_read refines it; putt_result resolves it (landing does not)', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 3, yards: 172 }, 47, 12));
  b.onEvent(ev('decision', { club: 'Putter', shot_type: 'putt', target_yards: 0, lie: 'green' }, 47, 12));
  assert.strictEqual(byId(b, 'r47-h12-s1').question, 'One-putt?');
  assert.deepStrictEqual(byId(b, 'r47-h12-s1').odds, { yes: 2.5, no: 1.67 });
  b.onEvent(ev('putt_read', { dist_ft: 12, make_pct: 32 }, 47, 12));
  assert.strictEqual(byId(b, 'r47-h12-s1').question, 'One-putt from 12 ft?');
  assert.deepStrictEqual(byId(b, 'r47-h12-s1').odds, { yes: 3.13, no: 1.47 });
  b.onEvent(ev('strike', {}, 47, 12));
  b.onEvent(ev('landing', { dist_to_pin_ft: 0, lie: 'green' }, 47, 12));
  assert.strictEqual(byId(b, 'r47-h12-s1').status, 'closed', 'landing must not resolve a putt market');
  b.onEvent(ev('putt_result', { made: true, dist_ft: 12 }, 47, 12));
  assert.strictEqual(byId(b, 'r47-h12-s1').status, 'resolved');
  assert.strictEqual(byId(b, 'r47-h12-s1').winning_outcome, 'yes');
});
check('layup opens no per-shot market (the per-hole market stays featured)', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 5, yards: 612 }, 47, 2));
  b.onEvent(ev('decision', { club: '7-iron', shot_type: 'layup', target_yards: 150, lie: 'rough' }, 47, 2));
  assert.strictEqual(marketsOf(b).length, 1);
  assert.strictEqual(b.toPrediction().market_id, 'r47-h2-hole');
});

// --- Per-hole resolution and staleness -------------------------------------------
check('hole_end resolves the per-hole market (birdie yes, par no)', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 3, yards: 172 }, 47, 12));
  b.onEvent(ev('hole_end', { score: 2, par: 3, score_to_par: -1, putts: 1 }, 47, 12));
  assert.strictEqual(byId(b, 'r47-h12-hole').winning_outcome, 'yes');
  const b2 = makeBridge();
  b2.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b2.onEvent(ev('hole_end', { score: 4, par: 4, score_to_par: 0, putts: 2 }, 47, 1));
  assert.strictEqual(byId(b2, 'r47-h1-hole').winning_outcome, 'no');
});
check('a per-shot market still open at hole_end is voided, not resolved', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b.onEvent(ev('decision', { club: 'Putter', shot_type: 'putt', target_yards: 0, lie: 'green' }, 47, 1));
  b.onEvent(ev('hole_end', { score: 4, par: 4, score_to_par: 0, putts: 2 }, 47, 1));
  assert.strictEqual(byId(b, 'r47-h1-s1').status, 'void');
  assert.strictEqual(byId(b, 'r47-h1-s1').winning_outcome, null);
});
check('round_start clears the previous round markets; round_end voids open markets', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b.onEvent(ev('round_end', { new_handicap: '+3.2' }, 47, 18));
  assert.strictEqual(byId(b, 'r47-h1-hole').status, 'void');
  b.onEvent(ev('round_start', { target_score: 59 }, 48, 1));
  assert.strictEqual(marketsOf(b).length, 0);
  assert.strictEqual(b.toPrediction().open, false);
});

// --- Weekly reset: Monday 00:00 ET boundary ---------------------------------------
check('mondayOf maps Sunday 2026-11-08 to 2026-11-02 and Monday 2026-11-09 to itself', () => {
  const b = makeBridge();
  assert.strictEqual(b._mondayOf(new Date('2026-11-08T12:00:00-05:00')), '2026-11-02');
  assert.strictEqual(b._mondayOf(new Date('2026-11-09T00:00:00-05:00')), '2026-11-09');
  assert.strictEqual(b._mondayOf(new Date('2026-11-15T23:59:00-05:00')), '2026-11-09');
});
check('no rollover on Sunday 23:59 ET; rollover fires on the first event after Monday 00:00 ET', () => {
  const sunday = new Date('2026-11-08T23:59:00-05:00');
  const monday = new Date('2026-11-09T00:00:00-05:00');
  const b = makeBridge(() => sunday);
  b.applyEconomySnapshot({
    week_monday: '2026-11-02',
    bonus_pool: 4200,
    weekly_leaderboard: [
      { display_name: 'FairwayFan', balance: 2616, streak: 3 },
      { display_name: 'BirdieBelle', balance: 2140, streak: 1 }
    ],
    alltime_leaderboard: [{ display_name: 'FairwayFan', balance: 12480, streak: 3 }]
  });
  // Still Sunday: the board stands.
  b.onEvent(ev('hole_start', { par: 3, yards: 172 }, 47, 12), sunday);
  assert.strictEqual(b.toLeaderboard().weekly.length, 2);
  assert.strictEqual(b.toLeaderboard().bonus_pool, 4200);
  // First event on Monday: weekly board clears, champion archived,
  // bonus pool refills, all-time board untouched.
  b.onEvent(ev('decision', { club: '7-iron', shot_type: 'full', target_yards: 172, lie: 'tee' }, 47, 12), monday);
  const lb = b.toLeaderboard();
  assert.strictEqual(lb.weekly.length, 0);
  assert.deepStrictEqual(lb.champion, { display_name: 'FairwayFan' });
  assert.strictEqual(lb.bonus_pool, 10000);
  assert.strictEqual(lb.week_monday, '2026-11-09');
  assert.strictEqual(lb.alltime.length, 1);
  // A second Monday event does not roll again.
  b.onEvent(ev('strike', {}, 47, 12), monday);
  assert.strictEqual(b.toLeaderboard().week_monday, '2026-11-09');
});

// --- Economy snapshot merge --------------------------------------------------------
check('economy snapshot replaces mirror odds and fills the leaderboards', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 3, yards: 172 }, 47, 12));
  const changed = b.applyEconomySnapshot({
    week_monday: '2026-11-09',
    bonus_pool: 9950,
    markets: [{
      market_id: 'r47-h12-hole',
      question: 'Birdie or better on 12?',
      odds: { yes: 2.4, no: 1.6 },
      pool_coins: 1840,
      open: true,
      status: 'open',
      pools: { yes: 800, no: 1040 }
    }],
    weekly_leaderboard: [{ display_name: 'FairwayFan', balance: 2616, streak: 3 }],
    alltime_leaderboard: [{ display_name: 'FairwayFan', balance: 12480, streak: 3 }],
    champion: { display_name: 'FairwayFan' }
  });
  assert.strictEqual(changed, true);
  const m = byId(b, 'r47-h12-hole');
  assert.strictEqual(m.source, 'economy');
  assert.deepStrictEqual(m.odds, { yes: 2.4, no: 1.6 }, 'economy odds must win for display');
  assert.strictEqual(m.pool_coins, 1840);
  const lb = b.toLeaderboard();
  assert.strictEqual(lb.weekly[0].display_name, 'FairwayFan');
  assert.strictEqual(lb.weekly[0].balance, 2616);
  assert.strictEqual(lb.bonus_pool, 9950);
  assert.strictEqual(lb.week_monday, '2026-11-09');
});
check('malformed snapshots are ignored, never fatal', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 3, yards: 172 }, 47, 12));
  assert.doesNotThrow(() => {
    b.applyEconomySnapshot(null);
    b.applyEconomySnapshot('nope');
    b.applyEconomySnapshot({ markets: 'not-an-array' });
    b.applyEconomySnapshot({ markets: [{ no_id: true }, { market_id: 'x', odds: { yes: 0, no: 0 } }] });
    b.applyEconomySnapshot({ markets: [{ market_id: 'r47-h12-hole', odds: { yes: 'a', no: null } }] });
  });
  // The mirror market survives untouched (bad economy odds never applied).
  assert.deepStrictEqual(byId(b, 'r47-h12-hole').odds, { yes: 8.33, no: 1.14 });
  assert.strictEqual(byId(b, 'r47-h12-hole').source, 'mirror');
});

// --- Structural guarantees ---------------------------------------------------------
check('the bridge never computes payouts: no payout fields anywhere in its output', () => {
  const b = makeBridge();
  b.onEvent(ev('hole_start', { par: 4, yards: 432 }, 47, 1));
  b.onEvent(ev('decision', { club: 'Driver', shot_type: 'full', target_yards: 300, lie: 'tee' }, 47, 1));
  b.onEvent(ev('strike', {}, 47, 1));
  b.onEvent(ev('landing', { fairway_hit: true }, 47, 1));
  b.onEvent(ev('hole_end', { score: 3, par: 4, score_to_par: -1 }, 47, 1));
  const dump = JSON.stringify({ markets: b.toMarkets(), prediction: b.toPrediction(), leaderboard: b.toLeaderboard() });
  assert.ok(!/payout/i.test(dump), 'payout text found in bridge output');
  assert.ok(!/balance/i.test(dump), 'balance text found in bridge output');
  const keys = Object.keys(byId(b, 'r47-h1-hole')).sort();
  assert.deepStrictEqual(keys, ['hole', 'market_id', 'market_type', 'odds', 'open', 'outcomes', 'pool_coins', 'question', 'round_no', 'shot', 'source', 'status', 'winning_outcome']);
});
check('the same event sequence on two bridges produces identical replicant JSON', () => {
  const seq = [
    ev('round_start', {}, 47, 1),
    ev('hole_start', { par: 4, yards: 432 }, 47, 1),
    ev('decision', { club: 'Driver', shot_type: 'full', target_yards: 300, lie: 'tee' }, 47, 1),
    ev('strike', {}, 47, 1),
    ev('landing', { fairway_hit: true, total_yds: 291, lie: 'fairway' }, 47, 1),
    ev('hole_end', { score: 3, par: 4, score_to_par: -1, putts: 1 }, 47, 1)
  ];
  const run = () => {
    const b = makeBridge(() => new Date('2026-11-13T01:00:00-05:00'));
    seq.forEach((e) => b.onEvent(e, new Date('2026-11-13T01:00:00-05:00')));
    return JSON.stringify({ m: b.toMarkets(), p: b.toPrediction(), l: b.toLeaderboard() });
  };
  assert.strictEqual(run(), run());
});

if (failures > 0) {
  console.error(`\n${failures} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll coins-bridge checks passed.');
