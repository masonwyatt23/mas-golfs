/* Mas Golfs — Clubhouse Coins bridge (NodeCG extension side).
 *
 * This module is a MIRROR, not the economy. It owns no balances, runs no
 * payouts, and cannot move coins anywhere — there is no payout code in
 * this file, by design. The Clubhouse Coins economy itself lives in
 * `coins/` (Python) and is the only authority on wallets, stakes, and
 * payouts. This bridge turns sim event-bus events into the market
 * replicants the graphics read, using the same base-rate tables and odds
 * math as `coins/odds.py`, so the screen is right even before the
 * economy process exists.
 *
 * How the real economy feeds it (the bridge contract — see the bundle
 * README "Coins bridge contract" for the full version):
 *   - The economy process writes a JSON snapshot (markets in
 *     `Market.to_replicant()` shape, leaderboards, week, bonus pool)
 *     atomically to the file in `MAS_GOLFS_COINS_SNAPSHOT`. The
 *     extension polls that file and calls `applyEconomySnapshot()`.
 *   - Economy-fed values always win over the local mirror: a market in
 *     the snapshot replaces the mirror market with the same id, and
 *     economy pools drive the blended displayed odds.
 *   - With no economy process running, the mirror prices display odds
 *     from the base tables with empty pools (displayed odds == opening
 *     odds) and the leaderboard is empty — the graphic says so honestly.
 *
 * Market lifecycle (driven by bus envelope events):
 *   hole_start  -> open the per-hole market ("Birdie or better on N?")
 *   decision    -> open the per-shot market (fairway / GIR / proximity /
 *                  one-putt, from the shot's lie, club, and distance)
 *   putt_read   -> refine an open one-putt market with the real distance
 *                  and make % (the decision has no distance to the pin)
 *   strike      -> close the open per-shot market (stakes lock at the swing)
 *   landing     -> resolve the per-shot market (fairway_hit / on_green /
 *                  dist_to_pin_ft) — putt markets wait for putt_result
 *   putt_result -> resolve the open one-putt market (made -> yes)
 *   hole_end    -> resolve the per-hole market (birdie or better -> yes),
 *                  void any per-shot market still open
 *   round_start -> clear the previous round's markets
 *   round_end   -> void any market still open
 *
 * The weekly reset (Monday 00:00 ET) is checked on every event
 * (`maybeRollover`): when the ET week Monday advances, the weekly
 * leaderboard clears, the week's winner is archived as Clubhouse
 * Champion, and the bonus pool refills to 10,000 CC.
 */
'use strict';

// --- Base rates: mirror of coins/odds.py ------------------------------------
// Starting calibration from coins-economy.md §5.2. The economy re-derives
// these from Mas's rolling stats; the bridge uses the same tables so its
// display odds match the economy's opening odds.
const BASE_SHOT_RATES = {
  fairway_par45_tee: 0.575,
  gir_approach_100yd: 0.68,
  gir_approach_150yd: 0.60,
  gir_approach_200yd: 0.45,
  proximity_10ft_100yd: 0.28,
  proximity_10ft_150yd: 0.20,
  proximity_10ft_200yd: 0.12,
  up_and_down_bunker: 0.45,
  up_and_down_rough_short: 0.55,
  one_putt_inside_6ft: 0.85,
  one_putt_10ft: 0.40,
  one_putt_20ft: 0.14
};

const BASE_HOLE_RATES = {
  birdie_or_better_par5: 0.30,
  birdie_or_better_par4: 0.16,
  birdie_or_better_par3: 0.12,
  par_or_better_any: 0.72,
  bogey_or_worse_any: 0.28
};

const FORM_MIN = 0.85;
const FORM_MAX = 1.15;
const HOLE_MIN = 0.70;
const HOLE_MAX = 1.30;
const CONDITION_MIN = 0.80;
const CONDITION_MAX = 1.20;
const P_MIN = 0.02;
const P_MAX = 0.98;
const MOVE_CAP = 0.25; // displayed odds move at most ±25% from opening
const MODEL_WEIGHT = 0.5; // 50/50 model/pool blend for displayed odds

const BONUS_POOL_WEEKLY_SEED = 10000; // coins-economy.md §6.6
const MAX_KEPT_MARKETS = 12; // keep the current round's markets, drop older

// --- Odds math: mirror of coins/odds.py (pure functions) --------------------

function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

function adjustProbability(pBase, form, hole, condition) {
  form = clamp(form === undefined ? 1 : form, FORM_MIN, FORM_MAX);
  hole = clamp(hole === undefined ? 1 : hole, HOLE_MIN, HOLE_MAX);
  condition = clamp(condition === undefined ? 1 : condition, CONDITION_MIN, CONDITION_MAX);
  return clamp(pBase * form * hole * condition, P_MIN, P_MAX);
}

function normalizeProbs(probs) {
  const total = Object.values(probs).reduce((s, p) => s + p, 0);
  if (total <= 0) throw new Error('probabilities must sum to a positive number');
  const out = {};
  for (const k of Object.keys(probs)) out[k] = probs[k] / total;
  return out;
}

function decimalOdds(p) {
  if (p <= 0) throw new Error('probability must be positive');
  return Math.round((1.0 / p) * 100) / 100;
}

function openingOdds(probs) {
  const norm = normalizeProbs(probs);
  const out = {};
  for (const k of Object.keys(norm)) out[k] = decimalOdds(norm[k]);
  return out;
}

function blendedOdds(opening, modelProbs, pools) {
  const model = normalizeProbs(modelProbs);
  const totalPool = Object.values(pools).reduce((s, v) => s + v, 0);
  const out = {};
  for (const outcome of Object.keys(model)) {
    let pDisplay = model[outcome];
    if (totalPool > 0) {
      const poolShare = (pools[outcome] || 0) / totalPool;
      pDisplay = MODEL_WEIGHT * model[outcome] + (1 - MODEL_WEIGHT) * poolShare;
    }
    let odds = 1.0 / pDisplay;
    odds = clamp(odds, opening[outcome] * (1 - MOVE_CAP), opening[outcome] * (1 + MOVE_CAP));
    out[outcome] = Math.round(odds * 100) / 100;
  }
  return out;
}

// --- Eastern-time week math --------------------------------------------------
// Monday 00:00 ET is the weekly reset (coins-economy.md §7.1). Work in
// calendar dates via Intl so DST never shifts the boundary.

function etParts(date) {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York',
    year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short'
  });
  const parts = {};
  for (const p of fmt.formatToParts(date)) parts[p.type] = p.value;
  return parts; // { year, month, day, weekday: 'Sun'..'Sat' }
}

const WEEKDAY_NUM = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

function mondayOf(date) {
  const parts = etParts(date);
  const y = Number(parts.year);
  const m = Number(parts.month);
  const d = Number(parts.day);
  const wd = WEEKDAY_NUM[parts.weekday];
  // Monday of this week: step back (wd + 6) % 7 days (Sunday -> 6 back).
  const monday = new Date(Date.UTC(y, m - 1, d - ((wd + 6) % 7)));
  return monday.toISOString().slice(0, 10); // YYYY-MM-DD
}

function isValidDateString(s) {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s + 'T00:00:00Z'));
}

// --- Market selection ---------------------------------------------------------

function perHoleBaseProb(par) {
  if (par === 5) return BASE_HOLE_RATES.birdie_or_better_par5;
  if (par === 4) return BASE_HOLE_RATES.birdie_or_better_par4;
  return BASE_HOLE_RATES.birdie_or_better_par3;
}

// Pick the per-shot market for a decision. Returns null when the shot has
// no clean yes/no market (layup, bunker recovery): the per-hole market
// stays featured and no per-shot market opens.
function perShotMarketSpec(decision) {
  const data = decision || {};
  const shotType = data.shot_type || '';
  const club = String(data.club || '').toLowerCase();
  const lie = String(data.lie || '').toLowerCase();
  const yards = data.target_yards;

  if (shotType === 'putt' || club === 'putter' || lie === 'green') {
    // Distance unknown until putt_read refines it; open on the 10 ft rate.
    return { kind: 'one_putt', question: 'One-putt?', baseProb: BASE_SHOT_RATES.one_putt_10ft };
  }
  if (lie === 'tee') {
    // Par-3 tee shot is an approach at the green, not a fairway market.
    const par = data.par;
    if (par === 3) return girSpec(yards);
    // The hole number is added by the caller (it lives on the envelope,
    // not in the decision data) — keep the question hole-free here.
    return { kind: 'fairway', question: 'Fairway?', baseProb: BASE_SHOT_RATES.fairway_par45_tee };
  }
  if (shotType === 'pitch' || shotType === 'chip') {
    const baseProb = yards == null ? BASE_SHOT_RATES.proximity_10ft_100yd
      : yards <= 110 ? BASE_SHOT_RATES.proximity_10ft_100yd
      : yards <= 175 ? BASE_SHOT_RATES.proximity_10ft_150yd
      : BASE_SHOT_RATES.proximity_10ft_200yd;
    return { kind: 'proximity', question: 'Inside 10 ft?', baseProb };
  }
  if (shotType === 'layup' || shotType === 'bunker_splash' || shotType === 'bunker_pick') {
    return null;
  }
  // Full swings, knockdowns, draws, fades: the approach question.
  return girSpec(yards);
}

function girSpec(yards) {
  const baseProb = yards == null ? BASE_SHOT_RATES.gir_approach_150yd
    : yards <= 110 ? BASE_SHOT_RATES.gir_approach_100yd
    : yards <= 175 ? BASE_SHOT_RATES.gir_approach_150yd
    : BASE_SHOT_RATES.gir_approach_200yd;
  return { kind: 'gir', question: 'GIR?', baseProb };
}

function onePuttBaseProb(distFt) {
  if (distFt == null) return BASE_SHOT_RATES.one_putt_10ft;
  if (distFt <= 6) return BASE_SHOT_RATES.one_putt_inside_6ft;
  if (distFt <= 10) return BASE_SHOT_RATES.one_putt_10ft;
  if (distFt <= 20) return BASE_SHOT_RATES.one_putt_20ft;
  return 0.05; // long lag putt: no table rate, honest long shot
}

// --- The bridge ---------------------------------------------------------------

function createCoinsBridge(opts) {
  opts = opts || {};
  const log = opts.log || { info: () => {}, warn: () => {}, debug: () => {} };
  const nowFn = opts.now || (() => new Date());

  // Mirror state. `markets` is insertion-ordered (oldest first).
  let markets = [];
  let leaderboard = {
    week_monday: null,
    weekly: [],
    alltime: [],
    champion: null,
    bonus_pool: BONUS_POOL_WEEKLY_SEED
  };
  let weekMonday = null; // ET Monday string for the current week, or null
  let shotCounter = {}; // hole -> shots decided this hole (market ids)
  let currentPar = null; // par of the hole in play (from hole_start)

  function findMarket(marketId) {
    return markets.find((m) => m.market_id === marketId) || null;
  }

  function openMarket(market) {
    // Market ids are unique per round+hole(+shot): opening a market with
    // an id that already exists (the demo simulator repeats hole 12)
    // replaces the old one instead of duplicating it.
    const dup = markets.findIndex((m) => m.market_id === market.market_id);
    if (dup >= 0) markets.splice(dup, 1);
    markets.push(market);
    if (markets.length > MAX_KEPT_MARKETS) markets = markets.slice(-MAX_KEPT_MARKETS);
    return market;
  }

  function newMarket(marketId, marketType, question, baseProb, ctx) {
    const modelProbs = normalizeProbs({ yes: baseProb, no: 1 - baseProb });
    return {
      market_id: marketId,
      market_type: marketType,
      question,
      outcomes: ['yes', 'no'],
      kind: ctx.kind || null,
      model_probs: modelProbs,
      opening: openingOdds(modelProbs),
      pools: { yes: 0, no: 0 },
      pool_coins: 0,
      status: 'open',
      winning_outcome: null,
      round_no: ctx.round_no != null ? ctx.round_no : null,
      hole: ctx.hole != null ? ctx.hole : null,
      shot: ctx.shot != null ? ctx.shot : null,
      source: 'mirror'
    };
  }

  function marketOdds(market) {
    // Economy-fed odds always win for display; the mirror's blended odds
    // are only used until the economy process is running.
    if (market.economy_odds
      && typeof market.economy_odds.yes === 'number'
      && typeof market.economy_odds.no === 'number') {
      return { yes: market.economy_odds.yes, no: market.economy_odds.no };
    }
    return blendedOdds(market.opening, market.model_probs, market.pools);
  }

  function publicMarket(market) {
    // The replicant shape: Market.to_replicant() plus the fields the
    // coins graphic needs. Deliberately no payout fields — the bridge
    // never computes payouts; the economy settles them.
    return {
      market_id: market.market_id,
      market_type: market.market_type,
      question: market.question,
      outcomes: market.outcomes.slice(),
      odds: marketOdds(market),
      pool_coins: market.pool_coins,
      open: market.status === 'open',
      status: market.status,
      winning_outcome: market.winning_outcome,
      round_no: market.round_no,
      hole: market.hole,
      shot: market.shot,
      source: market.source
    };
  }

  function openPerHoleMarket(roundNo, hole, par) {
    const marketId = 'r' + roundNo + '-h' + hole + '-hole';
    const existing = findMarket(marketId);
    if (existing && existing.status === 'open') return existing;
    const baseProb = perHoleBaseProb(par);
    return openMarket(newMarket(marketId, 'per_hole', 'Birdie or better on ' + hole + '?', baseProb, {
      kind: 'birdie_or_better', round_no: roundNo, hole
    }));
  }

  function openPerShotMarket(roundNo, hole, decision) {
    // The decision carries no par — the par comes from the hole_start
    // that opened the hole (a par-3 tee shot is an approach, not a
    // fairway market). Default to the fairway market when unknown.
    const spec = perShotMarketSpec(Object.assign({}, decision, {
      hole,
      par: decision.par !== undefined ? decision.par : currentPar
    }));
    if (!spec) return null;
    const n = (shotCounter[hole] || 0) + 1;
    shotCounter[hole] = n;
    const marketId = 'r' + roundNo + '-h' + hole + '-s' + n;
    const question = spec.kind === 'fairway' || spec.kind === 'gir'
      ? spec.question.replace('?', ' on ' + hole + '?')
      : spec.question;
    return openMarket(newMarket(marketId, 'per_shot', question, spec.baseProb, {
      kind: spec.kind, round_no: roundNo, hole, shot: n
    }));
  }

  function openPerShotMarketForHole() {
    return markets.filter((m) => m.market_type === 'per_shot' && m.status === 'open').pop() || null;
  }

  function openPerHoleMarketForHole() {
    return markets.filter((m) => m.market_type === 'per_hole' && m.status === 'open').pop() || null;
  }

  function closeMarket(market) {
    if (market && market.status === 'open') market.status = 'closed';
  }

  function resolveMarket(market, winningOutcome) {
    if (!market || market.status === 'resolved' || market.status === 'void') return;
    market.status = 'resolved';
    market.winning_outcome = winningOutcome;
  }

  function voidMarket(market) {
    if (!market || market.status === 'resolved' || market.status === 'void') return;
    market.status = 'void';
    market.winning_outcome = null;
  }

  function voidOpenMarkets() {
    markets.forEach((m) => { if (m.status === 'open' || m.status === 'closed') voidMarket(m); });
  }

  // --- Weekly reset -----------------------------------------------------------
  function maybeRollover(now) {
    const monday = mondayOf(now || nowFn());
    if (weekMonday === null) {
      weekMonday = monday;
      if (!leaderboard.week_monday) leaderboard.week_monday = monday;
      return false;
    }
    if (monday <= weekMonday) return false;
    // Monday 00:00 ET crossed: archive the champion, clear the weekly
    // board, refill the bonus pool. The all-time board never resets.
    const champion = leaderboard.weekly.length > 0 ? leaderboard.weekly[0] : null;
    if (champion) leaderboard.champion = { display_name: champion.display_name };
    leaderboard.weekly = [];
    leaderboard.bonus_pool = BONUS_POOL_WEEKLY_SEED;
    leaderboard.week_monday = monday;
    weekMonday = monday;
    log.info('Clubhouse Coins weekly reset — new week ' + monday + (champion ? ', champion ' + champion.display_name : ''));
    return true;
  }

  // --- Economy snapshot merge ---------------------------------------------------
  // Snapshot shape (see bundle README "Coins bridge contract"):
  //   { week_monday, bonus_pool,
  //     markets: [ { market_id, question, odds, pool_coins, open, status,
  //                  winning_outcome?, pools? } ],   // Market.to_replicant()
  //     weekly_leaderboard: [ { display_name, balance, streak } ],
  //     alltime_leaderboard: [ { display_name, balance, streak } ],
  //     champion: { display_name } | null }
  // Malformed entries are skipped, never fatal.
  function applyEconomySnapshot(snap) {
    if (!snap || typeof snap !== 'object') return false;
    let changed = false;
    if (Array.isArray(snap.markets)) {
      for (const incoming of snap.markets) {
        if (!incoming || typeof incoming.market_id !== 'string') continue;
        const existing = findMarket(incoming.market_id);
        const econOdds = (incoming.odds && typeof incoming.odds === 'object'
          && typeof incoming.odds.yes === 'number' && incoming.odds.yes > 1
          && typeof incoming.odds.no === 'number' && incoming.odds.no > 1)
          ? { yes: incoming.odds.yes, no: incoming.odds.no } : null;
        if (existing) {
          // Only a merge that actually carried a valid field flips the
          // market to economy-sourced; a malformed entry leaves the
          // mirror untouched.
          let merged = false;
          if (typeof incoming.question === 'string') { existing.question = incoming.question; merged = true; }
          if (econOdds) { existing.economy_odds = econOdds; merged = true; }
          if (typeof incoming.pool_coins === 'number') { existing.pool_coins = incoming.pool_coins; merged = true; }
          if (incoming.pools && typeof incoming.pools === 'object') {
            existing.pools = {
              yes: incoming.pools.yes || 0,
              no: incoming.pools.no || 0
            };
            merged = true;
          }
          if (typeof incoming.status === 'string') { existing.status = incoming.status; merged = true; }
          if (incoming.winning_outcome !== undefined) { existing.winning_outcome = incoming.winning_outcome; merged = true; }
          if (merged) existing.source = 'economy';
        } else if (typeof incoming.question === 'string' || econOdds) {
          // A market the mirror never opened (e.g. a skin or season
          // market created by the economy): adopt it as economy-sourced.
          const modelProbs = econOdds
            ? normalizeProbs({ yes: 1 / econOdds.yes, no: 1 / econOdds.no })
            : { yes: 0.5, no: 0.5 };
          const adopted = {
            market_id: incoming.market_id,
            market_type: incoming.market_type || 'per_hole',
            question: incoming.question || 'Clubhouse market',
            outcomes: ['yes', 'no'],
            kind: null,
            model_probs: modelProbs,
            opening: openingOdds(modelProbs),
            pools: (incoming.pools && typeof incoming.pools === 'object')
              ? { yes: incoming.pools.yes || 0, no: incoming.pools.no || 0 }
              : { yes: 0, no: 0 },
            pool_coins: typeof incoming.pool_coins === 'number' ? incoming.pool_coins : 0,
            status: typeof incoming.status === 'string' ? incoming.status : 'open',
            winning_outcome: incoming.winning_outcome || null,
            round_no: incoming.round_no != null ? incoming.round_no : null,
            hole: incoming.hole != null ? incoming.hole : null,
            shot: incoming.shot != null ? incoming.shot : null,
            source: 'economy'
          };
          if (econOdds) {
            adopted.economy_odds = { yes: econOdds.yes, no: econOdds.no };
          }
          openMarket(adopted);
        }
        changed = true;
      }
    }
    if (Array.isArray(snap.weekly_leaderboard)) {
      leaderboard.weekly = snap.weekly_leaderboard.slice(0, 5).map((row, i) => ({
        rank: i + 1,
        display_name: String(row.display_name || 'Viewer'),
        balance: typeof row.balance === 'number' ? row.balance : 0,
        streak: typeof row.streak === 'number' ? row.streak : 0
      }));
      changed = true;
    }
    if (Array.isArray(snap.alltime_leaderboard)) {
      leaderboard.alltime = snap.alltime_leaderboard.slice(0, 5).map((row, i) => ({
        rank: i + 1,
        display_name: String(row.display_name || 'Viewer'),
        balance: typeof row.balance === 'number' ? row.balance : 0,
        streak: typeof row.streak === 'number' ? row.streak : 0
      }));
      changed = true;
    }
    if (snap.champion && typeof snap.champion.display_name === 'string') {
      leaderboard.champion = { display_name: snap.champion.display_name };
      changed = true;
    }
    if (typeof snap.bonus_pool === 'number') {
      leaderboard.bonus_pool = snap.bonus_pool;
      changed = true;
    }
    if (isValidDateString(snap.week_monday)) {
      leaderboard.week_monday = snap.week_monday;
      weekMonday = snap.week_monday;
      changed = true;
    }
    return changed;
  }

  // --- Event routing ------------------------------------------------------------
  function onEvent(evt, now) {
    if (!evt || typeof evt !== 'object' || !evt.event) return false;
    maybeRollover(now);
    const data = evt.data || {};
    const roundNo = evt.round != null ? evt.round : 0;
    const hole = evt.hole != null ? evt.hole : 0;
    let changed = false;

    switch (evt.event) {
      case 'round_start':
        markets = [];
        shotCounter = {};
        currentPar = null;
        changed = true;
        break;
      case 'hole_start': {
        // A new hole: any per-shot market left open from the last hole is
        // voided (its shot never resolved), then the per-hole market opens.
        if (data.par !== undefined) currentPar = data.par;
        const stale = openPerShotMarketForHole();
        if (stale) { voidMarket(stale); changed = true; }
        if (data.par !== undefined) {
          openPerHoleMarket(roundNo, hole, data.par);
          changed = true;
        }
        break;
      }
      case 'decision': {
        const stale = openPerShotMarketForHole();
        if (stale) { voidMarket(stale); changed = true; }
        const opened = openPerShotMarket(roundNo, hole, data);
        if (opened) changed = true;
        break;
      }
      case 'putt_read': {
        // Refine an open one-putt market with the real distance + make %.
        const market = openPerShotMarketForHole();
        if (market && market.kind === 'one_putt') {
          const distFt = data.dist_ft;
          if (distFt != null) {
            market.question = 'One-putt from ' + Math.round(distFt) + ' ft?';
          }
          const makePct = data.make_pct;
          if (typeof makePct === 'number' && makePct > 0 && makePct < 100) {
            const p = makePct / 100;
            market.model_probs = normalizeProbs({ yes: p, no: 1 - p });
            market.opening = openingOdds(market.model_probs);
          } else if (distFt != null) {
            const p = onePuttBaseProb(distFt);
            market.model_probs = normalizeProbs({ yes: p, no: 1 - p });
            market.opening = openingOdds(market.model_probs);
          }
          changed = true;
        }
        break;
      }
      case 'strike': {
        const market = openPerShotMarketForHole();
        if (market) { closeMarket(market); changed = true; }
        break;
      }
      case 'landing': {
        const market = markets.filter((m) => m.market_type === 'per_shot'
          && (m.status === 'closed' || m.status === 'open')).pop() || null;
        // Putt markets resolve on putt_result, never on landing.
        if (market && market.kind !== 'one_putt') {
          let win = null;
          if (market.kind === 'fairway') win = data.fairway_hit ? 'yes' : 'no';
          else if (market.kind === 'gir') win = data.on_green ? 'yes' : 'no';
          else if (market.kind === 'proximity') {
            win = (data.dist_to_pin_ft != null && data.dist_to_pin_ft <= 10) ? 'yes' : 'no';
          }
          if (win) { resolveMarket(market, win); changed = true; }
        }
        break;
      }
      case 'putt_result': {
        const market = markets.filter((m) => m.market_type === 'per_shot'
          && (m.status === 'closed' || m.status === 'open')).pop() || null;
        if (market && market.kind === 'one_putt') {
          resolveMarket(market, data.made ? 'yes' : 'no');
          changed = true;
        }
        break;
      }
      case 'hole_end': {
        const perHole = markets.filter((m) => m.market_type === 'per_hole'
          && (m.status === 'open' || m.status === 'closed')).pop() || null;
        if (perHole && data.score !== undefined && data.par !== undefined) {
          resolveMarket(perHole, (data.score - data.par) <= -1 ? 'yes' : 'no');
          changed = true;
        }
        const stale = openPerShotMarketForHole();
        if (stale) { voidMarket(stale); changed = true; }
        break;
      }
      case 'round_end':
        voidOpenMarkets();
        changed = true;
        break;
      default:
        break;
    }
    return changed;
  }

  // --- Replicant views ------------------------------------------------------------
  function featuredMarket() {
    // The live call first: an open per-shot market; else the open
    // per-hole market; else the most recently resolved market.
    return openPerShotMarketForHole()
      || openPerHoleMarketForHole()
      || markets[markets.length - 1]
      || null;
  }

  function toPrediction() {
    const market = featuredMarket();
    if (!market) {
      return {
        question: '', odds: {}, pool_coins: 0, closes_in_s: null,
        open: false, market_id: null, status: 'closed'
      };
    }
    const pub = publicMarket(market);
    return {
      question: pub.question,
      odds: pub.odds,
      pool_coins: pub.pool_coins,
      // The mirror never knows the seconds to the swing or the hole end,
      // so closes_in_s stays null ("closes at the swing / at hole end").
      closes_in_s: null,
      open: pub.open,
      market_id: pub.market_id,
      status: pub.status
    };
  }

  function toMarkets() {
    return {
      markets: markets.map(publicMarket),
      active_market_id: featuredMarket() ? featuredMarket().market_id : null
    };
  }

  function toLeaderboard() {
    return {
      week_monday: leaderboard.week_monday,
      weekly: leaderboard.weekly.map((r) => Object.assign({}, r)),
      alltime: leaderboard.alltime.map((r) => Object.assign({}, r)),
      champion: leaderboard.champion ? Object.assign({}, leaderboard.champion) : null,
      bonus_pool: leaderboard.bonus_pool
    };
  }

  function toRoundStateCoins() {
    // No markets seen yet (no hole_start since boot): return null so the
    // extension leaves the placeholder coins block alone.
    if (markets.length === 0) return null;
    const market = featuredMarket();
    if (!market) return { prediction_open: false, question: '', odds: {} };
    return {
      prediction_open: market.status === 'open',
      question: market.question,
      odds: marketOdds(market)
    };
  }

  return {
    onEvent,
    maybeRollover,
    applyEconomySnapshot,
    toPrediction,
    toMarkets,
    toLeaderboard,
    toRoundStateCoins,
    // Exposed for tests: the pure odds math and the ET week math.
    _odds: { adjustProbability, normalizeProbs, openingOdds, blendedOdds, BASE_SHOT_RATES, BASE_HOLE_RATES },
    _mondayOf: mondayOf
  };
}

module.exports = { createCoinsBridge };
