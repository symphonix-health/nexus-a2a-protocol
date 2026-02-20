window.LipSyncEngine = (() => {
  let timeline = [];
  let startMs = 0;
  let timer = null;

  function visemeWeight(v) {
    if (!v) return 0;
    if (v === "sil") return 0;
    if (v === "PP" || v === "FV") return 0.55;
    if (v === "EE") return 0.7;
    if (v === "OW") return 0.85;
    return 0.65;
  }

  function start(visemes) {
    timeline = Array.isArray(visemes) ? visemes : [];
    startMs = Date.now();
    stop();
    timer = setInterval(() => {
      const elapsed = Date.now() - startMs;
      let active = timeline[timeline.length - 1] || { viseme: "sil", weight: 0 };
      for (const t of timeline) {
        if (elapsed >= (t.time_ms || 0)) {
          active = t;
        } else {
          break;
        }
      }
      const w = typeof active.weight === "number" ? active.weight : visemeWeight(active.viseme);
      window.AvatarRenderer.applyViseme(w);
      if (elapsed > ((timeline[timeline.length - 1] || {}).time_ms || 0) + 250) {
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
