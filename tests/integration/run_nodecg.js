/* Integration-harness runner for the real NodeCG extension.
 *
 * Loads nodecg-bundle/extension/index.js with a stubbed `nodecg` object
 * (in-memory replicants, logging to stdout, sent messages recorded),
 * connects it to the live bus server, runs for NODECG_RUN_SECONDS, then
 * dumps every replicant to NODECG_SNAPSHOT_PATH as JSON and exits 0.
 *
 * The extension's `require('ws')` resolves through NODE_PATH, which the
 * harness points at tests/integration/node_modules (the stdlib `ws` shim).
 *
 * Env: MAS_GOLFS_BUS_URL (default ws://127.0.0.1:4456),
 *      NODECG_SNAPSHOT_PATH (required), NODECG_RUN_SECONDS (default 12).
 */
'use strict';

const fs = require('fs');
const path = require('path');

const BUS_URL = process.env.MAS_GOLFS_BUS_URL || 'ws://127.0.0.1:4456';
const SNAPSHOT_PATH = process.env.NODECG_SNAPSHOT_PATH;
const RUN_SECONDS = parseFloat(process.env.NODECG_RUN_SECONDS || '12', 10);

if (!SNAPSHOT_PATH) {
  console.error('NODECG_SNAPSHOT_PATH is required');
  process.exit(2);
}

const replicants = {};
const messages = [];

function makeReplicant(name, opts) {
  const rep = {
    value: opts && opts.defaultValue !== undefined ? opts.defaultValue : null,
  };
  replicants[name] = rep;
  return rep;
}

const nodecg = {
  Replicant: makeReplicant,
  log: {
    info: (...args) => console.log('[nodecg:info]', ...args),
    warn: (...args) => console.log('[nodecg:warn]', ...args),
    error: (...args) => console.log('[nodecg:error]', ...args),
    debug: (...args) => console.log('[nodecg:debug]', ...args),
  },
  sendMessage: (name, payload) => {
    messages.push({ name, payload });
  },
  listenFor: () => {},
};

const extensionPath = path.join(
  __dirname, '..', '..', 'nodecg-bundle', 'extension', 'index.js');
const extension = require(extensionPath);
extension(nodecg);

console.log(`[harness] NodeCG extension running against ${BUS_URL} for ${RUN_SECONDS}s`);

setTimeout(() => {
  const snapshot = {
    roundState: replicants.roundState ? replicants.roundState.value : null,
    shotData: replicants.shotData ? replicants.shotData.value : null,
    prediction: replicants.prediction ? replicants.prediction.value : null,
    lastShot: replicants.lastShot ? replicants.lastShot.value : null,
    lowerThird: replicants.lowerThird ? replicants.lowerThird.value : null,
    messages,
  };
  fs.mkdirSync(path.dirname(SNAPSHOT_PATH), { recursive: true });
  fs.writeFileSync(SNAPSHOT_PATH, JSON.stringify(snapshot, null, 2), 'utf8');
  console.log(`[harness] snapshot written to ${SNAPSHOT_PATH}`);
  process.exit(0);
}, RUN_SECONDS * 1000);
