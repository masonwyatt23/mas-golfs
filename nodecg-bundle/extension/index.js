/* Mas Golfs — NodeCG server extension.
 *
 * Subscribes to the sim event bus (local WebSocket, ws://localhost:4456),
 * writes the four replicants the graphics read (roundState, shotData,
 * prediction, lastShot), and fires one-shot lower-third messages.
 *
 * If the event bus is unreachable it keeps serving the placeholder data
 * (shared/placeholder-data.json) and retries with backoff. With
 * MAS_GOLFS_DEMO=1 it runs a local simulator that emits a believable shot
 * cycle on a timer, so the whole bundle can be demoed with no sim engine.
 *
 * Manual overrides from the dashboard are logged only — the dashboard
 * cannot change scores, stats, or outcomes.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const BUS_URL = process.env.MAS_GOLFS_BUS_URL || 'ws://localhost:4456';
const DEMO_MODE = process.env.MAS_GOLFS_DEMO === '1';
const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 30000;

module.exports = function (nodecg) {
  const placeholderPath = path.join(__dirname, '..', 'shared', 'placeholder-data.json');
  let placeholder = {};
  try {
    placeholder = JSON.parse(fs.readFileSync(placeholderPath, 'utf8'));
  } catch (err) {
    nodecg.log.warn('Could not read placeholder data, starting empty:', err.message);
  }

  const roundState = nodecg.Replicant('roundState', { defaultValue: placeholder.roundState || {} });
  const shotData = nodecg.Replicant('shotData', { defaultValue: placeholder.shotData || {} });
  const prediction = nodecg.Replicant('prediction', { defaultValue: placeholder.prediction || {} });
  const lastShot = nodecg.Replicant('lastShot', { defaultValue: placeholder.lastShot || '' });
  const lowerThird = nodecg.Replicant('lowerThird', { defaultValue: null });

  // --- Event routing --------------------------------------------------------
  // Mirrors the event schema in docs/broadcast-stack.md §1.2 / §1.3.
  function handleEvent(evt) {
    if (!evt || typeof evt !== 'object' || !evt.event) return;
    const data = evt.data || {};
    switch (evt.event) {
      case 'round_state':
      case 'round_start':
        if (data.round_state) roundState.value = data.round_state;
        if (evt.event === 'round_start') {
          nodecg.log.info(`Round ${evt.round} started — target ${data.target_score || 59}`);
        }
        break;
      case 'hole_start':
        roundState.value = Object.assign({}, roundState.value, {
          hole: evt.hole,
          hole_par: data.par,
          current_hole: { name: data.hole_name, par: data.par, yards: data.yards }
        });
        if (data.wind_mph !== undefined) {
          nodecg.log.info(`Hole ${evt.hole} "${data.hole_name}" — ${data.par}, ${data.yards} yds, wind ${data.wind_mph} mph`);
        }
        break;
      case 'decision':
        prediction.value = Object.assign({}, prediction.value, { open: true });
        break;
      case 'strike':
        shotData.value = Object.assign({}, shotData.value, {
          club: data.club || shotData.value.club,
          ball_speed_mph: data.ball_speed_mph,
          launch_deg: data.launch_deg,
          spin_rpm: data.spin_rpm,
          smash_factor: data.smash_factor,
          contact: data.contact
        });
        showLowerThird({
          variant: 'shot',
          title: `${(data.club || 'CLUB').toUpperCase()} · ${data.target_yards || ''} YDS`.trim(),
          body: `Ball ${data.ball_speed_mph || '—'} mph · Launch ${data.launch_deg || '—'}° · Spin ${(data.spin_rpm || 0).toLocaleString()}`
        });
        break;
      case 'apex':
        shotData.value = Object.assign({}, shotData.value, {
          apex_ft: data.apex_ft,
          carry_yds: data.carry_yds,
          shape: data.shape
        });
        break;
      case 'landing':
        shotData.value = Object.assign({}, shotData.value, {
          total_yds: data.total_yds,
          lie: data.lie,
          dist_to_pin_ft: data.dist_to_pin_ft
        });
        lastShot.value = `${shotData.value.club || 'Shot'} from ${data.total_yds || '—'} — ${data.dist_to_pin_ft || '—'} ft, ${data.result || ''}`.trim();
        break;
      case 'hole_end':
        roundState.value = Object.assign({}, roundState.value, {
          thru: (roundState.value.thru || 0) + 1,
          score_to_par: (roundState.value.score_to_par || 0) + (data.score_to_par || 0)
        });
        showLowerThird({
          variant: 'holeResult',
          title: `HOLE ${evt.hole} — ${scoreName(data.score, data.par)}`,
          body: `${fmtToPar(roundState.value.score_to_par)} thru ${roundState.value.thru} · ${data.putts || '—'} putts`
        });
        break;
      case 'milestone':
        showLowerThird({
          variant: 'milestone',
          title: (data.type || 'MILESTONE').replace(/_/g, ' ').toUpperCase(),
          body: data.detail || ''
        });
        break;
      case 'round_end':
        roundState.value = Object.assign({}, roundState.value, {
          handicap: data.new_handicap || roundState.value.handicap
        });
        break;
      default:
        nodecg.log.debug(`Unhandled event: ${evt.event}`);
    }
  }

  function scoreName(score, par) {
    if (score === undefined || par === undefined) return 'HOLE COMPLETE';
    const d = score - par;
    if (d <= -3) return 'ALBATROSS';
    if (d === -2) return 'EAGLE';
    if (d === -1) return 'BIRDIE';
    if (d === 0) return 'PAR';
    if (d === 1) return 'BOGEY';
    return 'DOUBLE BOGEY+';
  }

  function fmtToPar(n) {
    if (n === 0) return 'E';
    return (n > 0 ? '+' : '') + n;
  }

  function showLowerThird(payload) {
    lowerThird.value = payload;
    nodecg.sendMessage('showLowerThird', payload);
  }

  // --- Dashboard manual overrides (logged, emergency-only) ------------------
  nodecg.listenFor('manualOverride', (data) => {
    nodecg.log.warn('Manual override requested (logged only, no state changed):', JSON.stringify(data));
  });

  // --- Event bus client ------------------------------------------------------
  let ws = null;
  let reconnectDelay = RECONNECT_BASE_MS;
  let demoTimer = null;

  function connectBus() {
    if (DEMO_MODE) {
      nodecg.log.info('MAS_GOLFS_DEMO=1 — running local demo simulator, no event bus.');
      startDemoSimulator();
      return;
    }
    let WebSocket;
    try {
      WebSocket = require('ws');
    } catch (err) {
      nodecg.log.error('The "ws" package is missing — run `npm install` in the bundle directory.');
      return;
    }
    nodecg.log.info(`Connecting to sim event bus at ${BUS_URL} ...`);
    ws = new WebSocket(BUS_URL);
    ws.on('open', () => {
      nodecg.log.info('Connected to sim event bus.');
      reconnectDelay = RECONNECT_BASE_MS;
      ws.send(JSON.stringify({ type: 'subscribe', events: '*' }));
    });
    ws.on('message', (raw) => {
      try {
        handleEvent(JSON.parse(raw.toString()));
      } catch (err) {
        nodecg.log.warn('Dropping unparsable bus message:', err.message);
      }
    });
    ws.on('close', () => {
      nodecg.log.warn(`Event bus disconnected — retrying in ${reconnectDelay / 1000}s.`);
      scheduleReconnect();
    });
    ws.on('error', (err) => {
      nodecg.log.warn('Event bus error:', err.message);
    });
  }

  function scheduleReconnect() {
    setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
      connectBus();
    }, reconnectDelay);
  }

  // --- Demo simulator (no sim engine needed) ---------------------------------
  function startDemoSimulator() {
    if (demoTimer) return;
    const cycle = [
      { event: 'strike', data: { club: '7-iron', ball_speed_mph: 132, launch_deg: 19, spin_rpm: 6800, smash_factor: 1.42, contact: 'pure', target_yards: 164 } },
      { event: 'apex', data: { apex_ft: 78, carry_yds: 158, shape: 'draw' } },
      { event: 'landing', data: { total_yds: 164, lie: 'green', dist_to_pin_ft: 12, result: 'green_hit' } },
      { event: 'hole_end', data: { score: 2, par: 3, score_to_par: -1, putts: 1 } }
    ];
    let i = 0;
    demoTimer = setInterval(() => {
      const evt = Object.assign({ seq: i, ts: new Date().toISOString(), round: 47, hole: 12 }, cycle[i % cycle.length]);
      handleEvent(evt);
      i += 1;
    }, 9000);
    nodecg.log.info('Demo simulator running — one shot cycle every ~36 s.');
  }

  connectBus();
};
