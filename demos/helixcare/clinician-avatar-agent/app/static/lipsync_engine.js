/**
 * LipSyncEngine
 *
 * Drives window.AvatarRenderer.applyViseme() on a 40 ms tick, translating the
 * server-provided viseme timeline into a smooth [0..1] weight signal.
 *
 * The engine applies a cosine envelope between adjacent visemes so transitions
 * feel organic rather than stepwise.
 */
window.LipSyncEngine = (() => {
  let timeline    = [];
  let startMs     = 0;
  let timer       = null;

  // Canonical weight for each viseme class
  function _visemeWeight(v) {
    if (!v || v === 'sil') return 0;
    if (v === 'PP' || v === 'FV') return 0.55;
    if (v === 'EE')               return 0.70;
    if (v === 'OW')               return 0.85;
    return 0.65;
  }

  // Cosine ease between two weights at normalised position t ∈ [0, 1]
  function _blend(from, to, t) {
    const ease = 0.5 - 0.5 * Math.cos(Math.PI * t);
    return from + (to - from) * ease;
  }

  function start(visemes) {
    timeline = Array.isArray(visemes) ? visemes : [];
    startMs  = Date.now();
    stop();
    if (!timeline.length) return;

    timer = setInterval(() => {
      const elapsed = Date.now() - startMs;
      const last    = timeline[timeline.length - 1];

      // Locate the two surrounding entries for interpolation
      let prevEntry = { time_ms: 0, viseme: 'sil', weight: 0 };
      let nextEntry = null;

      for (let i = 0; i < timeline.length; i++) {
        if ((timeline[i].time_ms || 0) <= elapsed) {
          prevEntry = timeline[i];
          nextEntry = timeline[i + 1] || null;
        } else {
          break;
        }
      }

      let w;
      if (nextEntry) {
        const span = (nextEntry.time_ms || 0) - (prevEntry.time_ms || 0);
        const pos  = span > 0 ? Math.min(1, (elapsed - (prevEntry.time_ms || 0)) / span) : 1;
        const wA   = typeof prevEntry.weight === 'number' ? prevEntry.weight : _visemeWeight(prevEntry.viseme);
        const wB   = typeof nextEntry.weight === 'number' ? nextEntry.weight : _visemeWeight(nextEntry.viseme);
        w = _blend(wA, wB, pos);
      } else {
        w = typeof prevEntry.weight === 'number' ? prevEntry.weight : _visemeWeight(prevEntry.viseme);
      }

      window.AvatarRenderer.applyViseme(w);

      // Stop 300 ms after the last entry
      if (elapsed > (last ? (last.time_ms || 0) : 0) + 300) {
        stop();
      }
    }, 40);
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    window.AvatarRenderer.applyViseme(0);
  }

  return { start, stop };
})();
