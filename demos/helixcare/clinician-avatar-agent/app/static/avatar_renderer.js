/**
 * AvatarRenderer — Phase 3: landmark-driven jaw morphing.
 *
 * MediaPipe FaceMesh (loaded from CDN) detects 468 face landmarks on the
 * looping reference video.  The mouth region landmarks are used to find the
 * EXACT position and width of the lips in each frame.  When the avatar is
 * speaking, a strip of pixels below the lip line is physically shifted
 * downward (getImageData / putImageData) in proportion to the live audio
 * amplitude coming from TTSClient's AnalyserNode.  A dark oral-cavity
 * gradient is painted in the exposed gap, and an upper-teeth crescent fades
 * in above 30 % intensity.
 *
 * Progressive enhancement:
 *   • MediaPipe unavailable → falls back to hardcoded MOUTH_CX / MOUTH_CY.
 *   • Landmark outside canvas bounds → same fallback.
 *   • Detection runs every 2 s (face is stable in a looping clip).
 *
 * Render layers (bottom → top):
 *   1. Video frame      — object-fit:cover via canvas drawImage
 *   2. Jaw pixel shift  — lower lip strip shifted down + dark cavity + teeth
 *   3. State rings      — thinking pulse, listening dot
 *   4. Wave bars        — amplitude visualiser strip (speaking only)
 */
window.AvatarRenderer = (() => {
  // Per-avatar { idle, speaking } video sources (served by /media/ route)
  const AVATAR_SOURCES = {
    male_black: {
      idle:     '/media/Black%20male%20clinician.mp4',
      speaking: '/media/Black%20male%20clinician%202.mp4',
    },
    male_white:   { idle: '/media/Black%20male%20clinician.mp4', speaking: '/media/Black%20male%20clinician%202.mp4' },
    female_black: { idle: '/media/Black%20male%20clinician.mp4', speaking: '/media/Black%20male%20clinician%202.mp4' },
    female_white: { idle: '/media/Black%20male%20clinician.mp4', speaking: '/media/Black%20male%20clinician%202.mp4' },
  };

  let _currentSources = AVATAR_SOURCES.male_black;

  // Fallback mouth position used until MediaPipe detects real landmarks.
  // Proportional to canvas size so it works at any resolution.
  // Calibrated for the standard head-shot clinician videos (face centred,
  // mouth at ~65 % of canvas height, ~10 % half-width).
  function _fallbackMouthLm(w, h) {
    return { cx: w * 0.50, cy: h * 0.655, halfW: w * 0.100 };
  }

  // ── Core state ─────────────────────────────────────────────────────────────
  let videoEl  = null;
  let canvasEl = null;
  let ctx      = null;
  let _animId  = null;
  let _speaking = 0;
  let _state   = 'idle';
  let _blinkT  = 0;
  let _lastTs  = 0;
  let _cover   = null;   // cached cover-crop rect

  // ── MediaPipe FaceMesh state ───────────────────────────────────────────────
  let _faceMesh    = null;
  let _meshReady   = false;
  let _mouthLm     = null;   // { cx, cy, halfW } in canvas px — null = use fallback
  let _detectTimer = null;

  // ── DOM setup ────────────────────────────────────────────────────────────────

  function init(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    container.style.position = 'relative';
    container.style.overflow = 'hidden';

    // Video: hidden source — decoded continuously, drawn each rAF via canvas
    videoEl = document.createElement('video');
    videoEl.id = 'avatar-video';
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.playsInline = true;
    videoEl.autoplay = true;
    videoEl.style.cssText = 'display:none;';
    container.appendChild(videoEl);
    videoEl.addEventListener('loadedmetadata', () => { _cover = null; }, { passive: true });

    // Canvas: sole visible renderer
    canvasEl = document.createElement('canvas');
    canvasEl.style.cssText =
      'width:100%;height:100%;display:block;border-radius:8px;background:#0c0c0c;';
    container.appendChild(canvasEl);
    ctx = canvasEl.getContext('2d');

    const ro = new ResizeObserver(() => { _cover = null; _mouthLm = null; _resizeCanvas(container); });
    ro.observe(container);
    _resizeCanvas(container);

    _loadVideoSrc(_currentSources.idle);
    videoEl.playbackRate = 0.85;

    _startLoop();
    _initFaceMesh();
  }

  function _resizeCanvas(container) {
    if (!canvasEl) return;
    canvasEl.width  = container.clientWidth;
    canvasEl.height = container.clientHeight;
    _cover = null;
  }

  // ── MediaPipe FaceMesh ────────────────────────────────────────────────────

  function _initFaceMesh() {
    // Retry until the CDN script has defined FaceMesh (async CDN load)
    if (typeof FaceMesh === 'undefined') {
      setTimeout(_initFaceMesh, 800);
      return;
    }
    try {
      _faceMesh = new FaceMesh({
        locateFile: (f) =>
          `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh@0.4.1633559619/${f}`,
      });
      _faceMesh.setOptions({
        maxNumFaces: 1,
        refineLandmarks: false,          // 468 pts, faster than 478
        minDetectionConfidence: 0.5,
        minTrackingConfidence: 0.5,
      });
      _faceMesh.onResults(_onMeshResults);
      _faceMesh.initialize().then(() => {
        _meshReady = true;
        // Run every 2 s — face is stable in a looping clip
        _detectTimer = setInterval(_runDetection, 2000);
        _runDetection();
      }).catch(() => { /* WASM load failed — use fallback */ });
    } catch (_) { /* FaceMesh constructor failed */ }
  }

  function _onMeshResults(results) {
    const lms = results.multiFaceLandmarks?.[0];
    if (!lms || !canvasEl || canvasEl.width === 0) return;

    const w  = canvasEl.width;
    const h  = canvasEl.height;
    const vw = videoEl ? (videoEl.videoWidth  || w) : w;
    const vh = videoEl ? (videoEl.videoHeight || h) : h;

    // Convert a MediaPipe normalised landmark to canvas pixel coords,
    // accounting for the cover-crop transform applied during drawImage.
    const { sx, sy, sw, sh } = _getCoverRect(w, h);
    function _pt(i) {
      const px = lms[i].x * vw;
      const py = lms[i].y * vh;
      return {
        x: ((px - sx) / (sw || 1)) * w,
        y: ((py - sy) / (sh || 1)) * h,
      };
    }

    // MediaPipe 468-pt mesh — outer lip corners: 61 (left), 291 (right)
    // Upper lip top centre: 0 — used as the pivot / lip-line Y
    const leftCorner  = _pt(61);
    const rightCorner = _pt(291);
    const upperLipTop = _pt(0);

    const cx    = (leftCorner.x + rightCorner.x) / 2;
    const cy    = upperLipTop.y;
    const halfW = Math.max(20, (rightCorner.x - leftCorner.x) / 2);

    // Sanity check: centre must be inside the canvas
    if (cx < 0 || cx > w || cy < 0 || cy > h) return;

    _mouthLm = { cx, cy, halfW };
  }

  async function _runDetection() {
    if (!_meshReady || !videoEl || videoEl.readyState < 2) return;
    try { await _faceMesh.send({ image: videoEl }); } catch (_) {}
  }

  // ── Cover-crop helper ─────────────────────────────────────────────────────

  function _getCoverRect(w, h) {
    if (_cover) return _cover;
    const vw = videoEl ? videoEl.videoWidth  : 0;
    const vh = videoEl ? videoEl.videoHeight : 0;
    if (!vw || !vh) { return { sx: 0, sy: 0, sw: w, sh: h }; }
    const cAR = w / h;
    const vAR = vw / vh;
    let sx, sy, sw, sh;
    if (cAR > vAR) {
      sw = vw; sh = Math.round(vw / cAR); sx = 0; sy = Math.round((vh - sh) / 2);
    } else {
      sh = vh; sw = Math.round(vh * cAR); sx = Math.round((vw - sw) / 2); sy = 0;
    }
    _cover = { sx, sy, sw, sh };
    return _cover;
  }

  // ── Avatar switching ──────────────────────────────────────────────────────

  function setAvatar(avatarKey) {
    _currentSources = AVATAR_SOURCES[avatarKey] || AVATAR_SOURCES.male_black;
    _loadVideoSrc(_state === 'speaking' ? _currentSources.speaking : _currentSources.idle);
  }

  function _loadVideoSrc(src) {
    if (!videoEl) return;
    const abs = new URL(src, window.location.href).href;
    if (videoEl.src === abs) return;
    const t = videoEl.currentTime;
    videoEl.src = src;
    videoEl.load();
    videoEl.currentTime = t % 5;
    videoEl.play().catch(() => {});
    _cover = null;
  }

  // ── State machine ─────────────────────────────────────────────────────────

  function setState(state) {
    const prev = _state;
    _state = state;
    if (!videoEl || !_currentSources) return;
    if (state === 'speaking' && prev !== 'speaking') {
      _loadVideoSrc(_currentSources.speaking);
      videoEl.playbackRate = 1.0;
    } else if (state !== 'speaking' && prev === 'speaking') {
      _loadVideoSrc(_currentSources.idle);
      videoEl.playbackRate = 0.85;
    }
  }

  // ── Viseme intensity ──────────────────────────────────────────────────────

  function applyViseme(weight) {
    const target = Math.max(0, Math.min(1, weight || 0));
    _speaking += (target - _speaking) * 0.25;
  }

  // ── Render loop ───────────────────────────────────────────────────────────

  function _startLoop() {
    if (_animId) return;
    function loop(ts) {
      _animId = requestAnimationFrame(loop);
      _blinkT += ts - _lastTs;
      _lastTs  = ts;
      _drawFrame();
    }
    _animId = requestAnimationFrame((ts) => { _lastTs = ts; loop(ts); });
  }

  function _drawFrame() {
    if (!ctx || !canvasEl || canvasEl.width === 0) return;
    const w = canvasEl.width;
    const h = canvasEl.height;
    ctx.clearRect(0, 0, w, h);

    // ── Layer 1: video frame (object-fit:cover) ───────────────────────────
    if (videoEl && videoEl.readyState >= 2) {
      const { sx, sy, sw, sh } = _getCoverRect(w, h);
      ctx.save();
      ctx.beginPath();
      if (ctx.roundRect) { ctx.roundRect(0, 0, w, h, 8); }
      else { ctx.rect(0, 0, w, h); }
      ctx.clip();
      ctx.drawImage(videoEl, sx, sy, sw, sh, 0, 0, w, h);
      ctx.restore();
    }

    const intensity = _speaking;
    const activeLm  = _mouthLm || _fallbackMouthLm(w, h);

    // ── Layer 2: driven jaw morph ─────────────────────────────────────────────
    if (intensity > 0.02) {
      _applyJawMorph(activeLm.cx, activeLm.cy, activeLm.halfW, w, h, intensity);
    }

    // ── Layer 3a: thinking — pulsing cyan ellipse ─────────────────────────────
    if (_state === 'thinking') {
      const pulse = 0.5 + 0.5 * Math.sin(_blinkT / 400);
      ctx.save();
      ctx.strokeStyle = `rgba(56,189,248,${(0.65 * pulse).toFixed(3)})`;
      ctx.lineWidth   = 2.5;
      ctx.beginPath();
      ctx.ellipse(activeLm.cx, activeLm.cy, 30 + pulse * 9, 13 + pulse * 5, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // ── Layer 3b: listening — green dot (top-right) ───────────────────────
    if (_state === 'listening') {
      const pulse = 0.6 + 0.4 * Math.sin(_blinkT / 300);
      ctx.save();
      ctx.fillStyle = `rgba(52,211,153,${pulse.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(w * 0.88, h * 0.06, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    // ── Layer 4: voice-wave bars ──────────────────────────────────────────
    if (_state === 'speaking' && intensity > 0.01) {
      const BAR_COUNT = 12;
      const BAR_W     = Math.max(3, w / (BAR_COUNT * 4));
      const BAR_GAP   = BAR_W * 0.6;
      const totalW    = BAR_COUNT * (BAR_W + BAR_GAP) - BAR_GAP;
      const startX    = (w - totalW) / 2;
      const BASE_Y    = h - 10;
      const MAX_H     = h * 0.10;
      ctx.save();
      for (let i = 0; i < BAR_COUNT; i++) {
        const phase = _blinkT / 180 + (i / BAR_COUNT) * Math.PI * 2;
        const wave  = 0.45 + 0.55 * Math.abs(Math.sin(phase));
        const barH  = Math.max(3, MAX_H * intensity * wave);
        const x     = startX + i * (BAR_W + BAR_GAP);
        const alpha = 0.55 + intensity * 0.45;
        const grad  = ctx.createLinearGradient(x, BASE_Y - barH, x, BASE_Y);
        grad.addColorStop(0,   `rgba(99,232,255,${alpha.toFixed(2)})`);
        grad.addColorStop(1,   `rgba(56,189,248,${(alpha * 0.4).toFixed(2)})`);
        ctx.fillStyle = grad;
        ctx.beginPath();
        if (ctx.roundRect) { ctx.roundRect(x, BASE_Y - barH, BAR_W, barH, 2); }
        else { ctx.rect(x, BASE_Y - barH, BAR_W, barH); }
        ctx.fill();
      }
      ctx.restore();
    }

    // Natural decay
    _speaking *= 0.92;
  }

  // ── Pixel-level jaw morph ─────────────────────────────────────────────────
  /**
   * Physically moves a strip of pixels (the lower lip + chin region) downward
   * by `jawDrop` pixels, then fills the exposed gap with a dark mouth-interior
   * gradient and a teeth crescent.
   *
   * This is the "true driven" effect: the actual face pixels shift, not just
   * a painted overlay.
   *
   * @param {number} cx      Mouth centre X (canvas px)
   * @param {number} cy      Lip-line Y — top of lower-jaw strip (canvas px)
   * @param {number} halfW   Half-width of the mouth ellipse (canvas px)
   * @param {number} w       Canvas width
   * @param {number} h       Canvas height
   * @param {number} intensity  Smoothed amplitude [0..1]
   */
  function _applyJawMorph(cx, cy, halfW, w, h, intensity) {
    // How far the jaw drops (px). Capped at 30 px so it doesn't look alien.
    const jawDrop = Math.round(Math.min(intensity * h * 0.048, 32));
    if (jawDrop < 2) return;

    // Strip of pixels to shift: from just below the lip-line downward.
    // Width is generous (2.6× halfW) so the chin stays attached.
    const regionW = Math.round(halfW * 2.6 + 24);
    const regionH = Math.round(h * 0.15);          // 15 % of canvas height
    const mx      = Math.max(0, Math.round(cx - regionW / 2));
    const my      = Math.round(cy + 1);            // 1 px below lip-line

    // Clamp to canvas bounds — putImageData would throw otherwise
    const safeW = Math.min(regionW, w - mx);
    const safeH = Math.min(regionH, h - my - jawDrop - 1);
    if (safeW < 4 || safeH < 4 || my < 0 || mx < 0) return;

    // 1. Save the lower-jaw pixel strip
    const pixels = ctx.getImageData(mx, my, safeW, safeH);

    // 2. Dark oral-cavity gradient in the exposed gap
    const cavHalfH = jawDrop * 0.72;
    const cavHalfW = halfW * 0.88;
    const grad = ctx.createRadialGradient(
      cx, my + jawDrop * 0.32, 0,
      cx, my + jawDrop * 0.55, Math.max(cavHalfW, 1)
    );
    grad.addColorStop(0,    'rgba(4,1,1,0.97)');
    grad.addColorStop(0.50, 'rgba(14,5,3,0.92)');
    grad.addColorStop(1,    'rgba(0,0,0,0)');

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(cx, my + cavHalfH * 0.55, cavHalfW, cavHalfH, 0, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    // 3. Upper-teeth crescent — fades in above 28 % intensity
    if (intensity > 0.28) {
      const ta = Math.min(1, (intensity - 0.28) / 0.55);
      ctx.beginPath();
      // Upper arc of the cavity ellipse = teeth row
      ctx.ellipse(cx, my + cavHalfH * 0.20, cavHalfW * 0.70, cavHalfH * 0.38, 0, Math.PI, 0);
      ctx.fillStyle = `rgba(248,244,240,${(ta * 0.88).toFixed(2)})`;
      ctx.fill();
    }
    ctx.restore();

    // 4. Restore jaw pixels shifted down — this is what makes the face move
    ctx.putImageData(pixels, mx, my + jawDrop);
  }

  // ── Public API ────────────────────────────────────────────────────────────

  return { init, setAvatar, applyViseme, setState };
})();
