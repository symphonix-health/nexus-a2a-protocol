/**
 * LipSyncEngine v2
 *
 * Major realism upgrade from v1:
 *  - 15 MPEG-4 compatible viseme classes (was 5)
 *  - Full multi-parameter mouth shapes: jawOpen, mouthWidth, lipPucker,
 *    upperLipRaise, lipCornerPull, tongueShow
 *  - Co-articulation: look-ahead blending starts 40% before next viseme
 *  - Cosine-ease interpolation between shapes (not just weights)
 *  - Emphasis/stress support via weight field in timeline
 *  - Sub-phoneme timing support (80ms per phoneme vs 190ms per word)
 *
 * Viseme Classes (MPEG-4 compatible):
 *   sil  — Silence (mouth closed)
 *   PP   — Bilabial plosive (p, b, m)
 *   FF   — Labiodental fricative (f, v)
 *   TH   — Dental fricative (th)
 *   DD   — Alveolar (d, t, n, l)
 *   KK   — Velar (k, g, ng)
 *   CH   — Postalveolar (ch, j, sh, zh)
 *   SS   — Alveolar fricative (s, z)
 *   NN   — Nasal (n, m, ng — resonant)
 *   RR   — Approximant (r, w)
 *   AA   — Open vowel (a, ah, ar)
 *   EE   — Front close vowel (ee, i)
 *   IH   — Front open vowel (ih, eh, ae)
 *   OO   — Back close vowel (oo, u)
 *   OU   — Back open vowel (oh, ow, aw)
 *
 * Public API (unchanged):
 *   start(visemes)  — begin animating from a timeline
 *   stop()          — halt animation and reset mouth
 */
window.LipSyncEngine = (() => {
  let timeline = [];
  let startMs = 0;
  let timer = null;

  // ── Viseme weight table (jaw openness intensity) ────────────────────
  const VISEME_WEIGHTS = {
    sil: 0.0,
    PP:  0.15,   // lips pressed, minimal jaw
    FF:  0.25,   // lower lip tucked, slight jaw
    TH:  0.30,   // tongue between teeth, slight jaw
    DD:  0.40,   // tongue tip up, moderate jaw
    KK:  0.45,   // back tongue up, moderate jaw
    CH:  0.40,   // tongue blade up, moderate jaw
    SS:  0.25,   // teeth close, minimal jaw
    NN:  0.20,   // nasal resonance, slight jaw
    RR:  0.35,   // approximant, moderate jaw
    AA:  0.90,   // wide open
    EE:  0.55,   // spread, moderate open
    IH:  0.50,   // mid-open, slightly spread
    OO:  0.65,   // rounded, moderate open
    OU:  0.80,   // open rounded
  };

  // ── Full mouth shape parameters per viseme ──────────────────────────
  // Each shape defines the canonical mouth pose for that viseme class.
  // Parameters: jawOpen, mouthWidth, lipPucker, upperLipRaise, lipCornerPull, tongueShow
  const VISEME_SHAPES = {
    sil: { jaw: 0.0,  mw: 0.5,  lp: 0.0,  ulr: 0.0,  lcp: 0.0,   ts: 0.0  },
    PP:  { jaw: 0.08, mw: 0.35, lp: 0.25, ulr: 0.0,  lcp: -0.05, ts: 0.0  },  // pressed lips
    FF:  { jaw: 0.15, mw: 0.45, lp: 0.0,  ulr: 0.15, lcp: 0.0,   ts: 0.0  },  // lower lip in
    TH:  { jaw: 0.2,  mw: 0.5,  lp: 0.0,  ulr: 0.1,  lcp: 0.0,   ts: 0.5  },  // tongue visible
    DD:  { jaw: 0.35, mw: 0.52, lp: 0.0,  ulr: 0.05, lcp: 0.0,   ts: 0.15 },  // tongue tip up
    KK:  { jaw: 0.4,  mw: 0.48, lp: 0.0,  ulr: 0.0,  lcp: 0.0,   ts: 0.0  },  // back of mouth
    CH:  { jaw: 0.3,  mw: 0.42, lp: 0.15, ulr: 0.0,  lcp: 0.0,   ts: 0.1  },  // rounded narrow
    SS:  { jaw: 0.18, mw: 0.6,  lp: 0.0,  ulr: 0.0,  lcp: 0.05,  ts: 0.0  },  // teeth close, spread
    NN:  { jaw: 0.15, mw: 0.5,  lp: 0.0,  ulr: 0.0,  lcp: 0.0,   ts: 0.0  },  // neutral, resonant
    RR:  { jaw: 0.3,  mw: 0.38, lp: 0.3,  ulr: 0.0,  lcp: 0.0,   ts: 0.0  },  // rounded for /r/
    AA:  { jaw: 0.85, mw: 0.62, lp: 0.0,  ulr: 0.1,  lcp: 0.0,   ts: 0.1  },  // wide open
    EE:  { jaw: 0.45, mw: 0.85, lp: 0.0,  ulr: 0.05, lcp: 0.1,   ts: 0.0  },  // spread wide
    IH:  { jaw: 0.4,  mw: 0.68, lp: 0.0,  ulr: 0.05, lcp: 0.05,  ts: 0.0  },  // mid spread
    OO:  { jaw: 0.5,  mw: 0.3,  lp: 0.7,  ulr: 0.0,  lcp: -0.05, ts: 0.0  },  // tight round
    OU:  { jaw: 0.7,  mw: 0.35, lp: 0.55, ulr: 0.0,  lcp: 0.0,   ts: 0.0  },  // open round
  };

  // ── Cosine ease ─────────────────────────────────────────────────────
  function _ease(t) {
    return 0.5 - 0.5 * Math.cos(Math.PI * Math.max(0, Math.min(1, t)));
  }

  // ── Blend two shape objects ─────────────────────────────────────────
  function _blendShapes(a, b, t) {
    const e = _ease(t);
    return {
      jaw: a.jaw + (b.jaw - a.jaw) * e,
      mw:  a.mw  + (b.mw  - a.mw)  * e,
      lp:  a.lp  + (b.lp  - a.lp)  * e,
      ulr: a.ulr + (b.ulr - a.ulr) * e,
      lcp: a.lcp + (b.lcp - a.lcp) * e,
      ts:  a.ts  + (b.ts  - a.ts)  * e,
    };
  }

  // ── Get shape for a viseme entry ────────────────────────────────────
  function _getShape(entry) {
    const v = entry.viseme || 'sil';
    const base = VISEME_SHAPES[v] || VISEME_SHAPES.sil;
    // Apply weight scaling from timeline (stress/emphasis)
    const w = typeof entry.weight === 'number' ? entry.weight : (VISEME_WEIGHTS[v] || 0);
    const scale = Math.max(0, Math.min(1.5, w));
    return {
      jaw: base.jaw * scale,
      mw:  base.mw,
      lp:  base.lp,
      ulr: base.ulr * scale,
      lcp: base.lcp,
      ts:  base.ts * scale,
    };
  }

  // ── Co-articulation: look-ahead blending ────────────────────────────
  // Start transitioning to the next viseme at 60% through the current one
  // (40% anticipatory co-articulation). This mimics how real speech muscles
  // begin forming the next sound before the current one finishes.
  const COARTIC_START = 0.6;  // Start blending at 60% through current viseme

  function _interpolateTimeline(elapsed) {
    if (!timeline.length) return VISEME_SHAPES.sil;

    // Find surrounding entries
    let prevIdx = 0;
    let nextIdx = -1;

    for (let i = 0; i < timeline.length; i++) {
      if ((timeline[i].time_ms || 0) <= elapsed) {
        prevIdx = i;
        nextIdx = i + 1 < timeline.length ? i + 1 : -1;
      } else {
        break;
      }
    }

    const prev = timeline[prevIdx];
    const prevShape = _getShape(prev);

    if (nextIdx < 0) {
      // Past the last entry — hold final viseme, decay to silence
      const lastTime = prev.time_ms || 0;
      const sinceLast = elapsed - lastTime;
      if (sinceLast > 200) {
        // Blend toward silence
        const t = Math.min(1, (sinceLast - 200) / 300);
        return _blendShapes(prevShape, VISEME_SHAPES.sil, t);
      }
      return prevShape;
    }

    const next = timeline[nextIdx];
    const nextShape = _getShape(next);
    const prevTime = prev.time_ms || 0;
    const nextTime = next.time_ms || 0;
    const span = nextTime - prevTime;

    if (span <= 0) return prevShape;

    const pos = (elapsed - prevTime) / span;  // 0 to 1 within this segment

    // Co-articulation: if we're past COARTIC_START, blend toward next viseme
    if (pos >= COARTIC_START) {
      const coarticT = (pos - COARTIC_START) / (1 - COARTIC_START);
      const blended = _blendShapes(prevShape, nextShape, coarticT);

      // Also look ahead to the one AFTER next for smoother multi-phoneme transitions
      if (nextIdx + 1 < timeline.length) {
        const afterNext = timeline[nextIdx + 1];
        const afterShape = _getShape(afterNext);
        const anticipation = coarticT * 0.15;  // Very slight anticipation of two-ahead
        return _blendShapes(blended, afterShape, anticipation);
      }
      return blended;
    }

    // Within the main body of the current viseme — hold shape
    // with slight interpolation from the beginning
    const holdT = pos / COARTIC_START;  // 0 to 1 within the hold region
    if (holdT < 0.2) {
      // Ease in from previous viseme (arrival)
      // Look back: what was the viseme before prev?
      if (prevIdx > 0) {
        const beforePrev = timeline[prevIdx - 1];
        const beforeShape = _getShape(beforePrev);
        const arrivalT = 0.5 + holdT * 2.5;  // 0.5 to 1.0 in arrival phase
        return _blendShapes(beforeShape, prevShape, arrivalT);
      }
    }

    return prevShape;
  }

  // ── Start animation ─────────────────────────────────────────────────
  function start(visemes) {
    timeline = Array.isArray(visemes) ? visemes : [];
    startMs = Date.now();
    stop();
    if (!timeline.length) return;

    timer = setInterval(() => {
      const elapsed = Date.now() - startMs;
      const last = timeline[timeline.length - 1];

      // Interpolate full mouth shape from timeline
      const shape = _interpolateTimeline(elapsed);

      // Drive the avatar renderer with full parameters
      if (window.AvatarRenderer && window.AvatarRenderer.applyVisemeParams) {
        window.AvatarRenderer.applyVisemeParams({
          jawOpen: shape.jaw,
          mouthWidth: shape.mw,
          lipPucker: shape.lp,
          upperLipRaise: shape.ulr,
          lipCornerPull: shape.lcp,
          tongueShow: shape.ts,
          rms: shape.jaw,  // Use jaw as RMS proxy for speaking intensity
        });
      } else if (window.AvatarRenderer) {
        window.AvatarRenderer.applyViseme(shape.jaw);
      }

      // Stop 400ms after the last entry (slightly longer for natural tail-off)
      if (elapsed > (last ? (last.time_ms || 0) : 0) + 400) {
        stop();
      }
    }, 25);  // 40 Hz update rate (was 25 Hz / 40ms)
  }

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
    if (window.AvatarRenderer && window.AvatarRenderer.applyVisemeParams) {
      window.AvatarRenderer.applyVisemeParams({
        jawOpen: 0, mouthWidth: 0.5, lipPucker: 0,
        upperLipRaise: 0, lipCornerPull: 0, tongueShow: 0, rms: 0,
      });
    } else if (window.AvatarRenderer) {
      window.AvatarRenderer.applyViseme(0);
    }
  }

  return { start, stop };
})();
