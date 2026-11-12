/* Mas Golfs — shared graphic runtime.
   Inside NodeCG: uses the real nodecg Replicant / listenFor / sendMessage API.
   Standalone (open the HTML file in a browser): falls back to
   window.MAS_PLACEHOLDER data and a small demo loop that advances the
   round every few seconds so the graphic can be previewed alive.
   Add ?static=1 to the URL to freeze the demo loop. */
(function () {
  'use strict';

  var isNodeCG = typeof window.nodecg !== 'undefined';
  var params = new URLSearchParams(window.location.search);
  var isStatic = params.get('static') === '1';
  var PLACEHOLDER = window.MAS_PLACEHOLDER || {};

  // --- Replicant shim -------------------------------------------------------
  function makeReplicant(name, defaultValue) {
    if (isNodeCG) {
      return nodecg.Replicant(name, { defaultValue: defaultValue });
    }
    var value = (PLACEHOLDER[name] !== undefined)
      ? JSON.parse(JSON.stringify(PLACEHOLDER[name]))
      : defaultValue;
    var listeners = [];
    return {
      get value() { return value; },
      set value(v) {
        value = v;
        listeners.forEach(function (fn) { fn(v); });
      },
      on: function (event, fn) {
        if (event === 'change') listeners.push(fn);
      },
      _demoSet: function (v) { this.value = v; }
    };
  }

  // --- Message bus shim -----------------------------------------------------
  var msgListeners = {};
  function listenFor(message, fn) {
    if (isNodeCG) { nodecg.listenFor(message, fn); return; }
    (msgListeners[message] = msgListeners[message] || []).push(fn);
  }
  function sendMessage(message, data) {
    if (isNodeCG) { nodecg.sendMessage(message, data); return; }
    (msgListeners[message] || []).forEach(function (fn) { fn(data); });
  }

  // --- Formatting helpers ---------------------------------------------------
  function fmtToPar(n) {
    if (n === 0) return 'E';
    return (n > 0 ? '+' : '') + n;
  }
  function fmtScore(n) { return String(n); }
  function markSVG(size) {
    // Brand mark: gold left-handed swing arc over a dark-green ball, impact tick.
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 100 100" aria-hidden="true">'
      + '<circle cx="50" cy="62" r="16" fill="#0B3D2E" stroke="#C9A227" stroke-width="3"/>'
      + '<path d="M 18 78 A 52 52 0 0 1 86 26" fill="none" stroke="#C9A227" stroke-width="7" stroke-linecap="round"/>'
      + '<rect x="38" y="59" width="24" height="5" rx="2.5" fill="#C9A227"/>'
      + '</svg>';
  }

  // --- Standalone demo loop -------------------------------------------------
  // Cycles a believable shot sequence so graphics can be previewed alive.
  // Only runs when there is no NodeCG and ?static=1 is not set.
  var demoState = null;
  function startDemo(replicants) {
    if (isNodeCG || isStatic) return;
    var shots = [
      { club: '7-iron', ball_speed_mph: 132, launch_deg: 19, spin_rpm: 6800, apex_ft: 78, carry_yds: 158, total_yds: 164, shape: 'draw', contact: 'pure', dist_to_pin_ft: 12, lie: 'green' },
      { club: 'Driver', ball_speed_mph: 164, launch_deg: 12, spin_rpm: 2400, apex_ft: 96, carry_yds: 272, total_yds: 291, shape: 'fade', contact: 'pure', dist_to_pin_ft: 142, lie: 'fairway' },
      { club: 'Pitching wedge', ball_speed_mph: 98, launch_deg: 26, spin_rpm: 9100, apex_ft: 54, carry_yds: 121, total_yds: 128, shape: 'straight', contact: 'thin', dist_to_pin_ft: 9, lie: 'green' }
    ];
    var idx = 0;
    demoState = { shotIdx: 0 };
    setInterval(function () {
      idx = (idx + 1) % shots.length;
      if (replicants.shotData) replicants.shotData._demoSet(shots[idx]);
      if (replicants.lastShot) {
        var s = shots[idx];
        replicants.lastShot._demoSet(s.club + ' — ' + s.carry_yds + ' yd carry, ' + s.dist_to_pin_ft + ' ft to pin');
      }
      // Rotate lower-third variants for the lower-third preview.
      if (replicants.lowerThird) {
        var variants = ['shot', 'holeResult', 'milestone'];
        var v = variants[idx % variants.length];
        replicants.lowerThird._demoSet(PLACEHOLDER.lowerThirds ? PLACEHOLDER.lowerThirds[v] : null);
      }
    }, 8000);
  }

  window.MasGolfs = {
    isNodeCG: isNodeCG,
    isStatic: isStatic,
    placeholder: PLACEHOLDER,
    makeReplicant: makeReplicant,
    listenFor: listenFor,
    sendMessage: sendMessage,
    fmtToPar: fmtToPar,
    fmtScore: fmtScore,
    markSVG: markSVG,
    startDemo: startDemo
  };
})();
