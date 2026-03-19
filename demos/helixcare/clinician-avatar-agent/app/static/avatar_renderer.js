/**
 * AvatarRenderer v11
 *
 * Major realism upgrade:
 *  - Natural eye blinking (random 3-7s intervals, 200ms close, double-blink chance)
 *  - Breathing animation (subtle scale + vertical shift, 4s cycle)
 *  - Micro head movement (multi-frequency sine oscillation)
 *  - Eye gaze tracking (follows mouse cursor, drifts during idle)
 *  - Eyebrow animation (raises during questions, furrows during concern)
 *  - Expression system (neutral, attentive, warm, concerned)
 *  - Enhanced mouth geometry (15-param lips, moisture highlight, lip corners)
 *  - Nasolabial fold deepening during speech
 *  - Better skin-adaptive blending (multi-layer gradient)
 *  - MediaPipe face landmark integration for eye/brow/mouth positioning
 *
 * Public API (unchanged):
 *   init(containerId)
 *   setAvatar(key)
 *   setRenderMode(mode)
 *   applyViseme(weight)
 *   applyVisemeParams({ jawOpen, mouthWidth, lipPucker, rms, ... })
 *   setState(state)
 *
 * New public API:
 *   setExpression(name, weight)  — blend facial expression
 *   setGazeTarget(nx, ny)        — direct eye gaze (0-1 normalized)
 */
window.AvatarRenderer = (() => {
  // ── Avatar sources ──────────────────────────────────────────────────────
  const AVATAR_SOURCES = {
    male_black: {
      idle: '/media/Black%20male%20clinician.mp4',
      speaking: '/media/Black%20male%20clinician%202.mp4',
      static: '/media/Black%20male%20clinician%20front.png',
    },
    male_white: {
      idle: '/media/Black%20male%20clinician.mp4',
      speaking: '/media/Black%20male%20clinician%202.mp4',
      static: '/media/Black%20male%20clinician%20left.png',
    },
    female_black: {
      idle: '/media/Black%20male%20clinician.mp4',
      speaking: '/media/Black%20male%20clinician%202.mp4',
      static: '/media/Black%20male%20clinician%20back.png',
    },
    female_white: {
      idle: '/media/Black%20male%20clinician.mp4',
      speaking: '/media/Black%20male%20clinician%202.mp4',
      static: '/media/Black%20male%20clinician%20front.png',
    },
  };

  let _currentSources = AVATAR_SOURCES.male_black;
  let _renderMode = 'static';

  let videoEl = null;
  let imageEl = null;
  let canvasEl = null;
  let ctx = null;

  let _animId = null;
  let _state = 'idle';
  let _lastTs = 0;
  let _elapsedMs = 0;
  let _cover = null;

  // ── Mouth parameters (driven by lipsync / amplitude) ──────────────────
  let _speaking = 0;
  let _jawOpen = 0;
  let _mouthWidth = 0.5;
  let _lipPucker = 0;
  let _upperLipRaise = 0;
  let _lipCornerPull = 0;
  let _tongueShow = 0;

  // ── Skin colour cache ─────────────────────────────────────────────────
  let _skinRGB = null;
  let _skinSampleFrame = 0;

  // ── MediaPipe face mesh ───────────────────────────────────────────────
  let _faceMesh = null;
  let _meshReady = false;
  let _mouthLm = null;
  let _eyeLandmarks = null;   // { leftEye: {cx,cy,w,h}, rightEye: {cx,cy,w,h} }
  let _browLandmarks = null;  // { leftBrow: {cx,cy}, rightBrow: {cx,cy} }
  let _noseLandmark = null;   // { cx, cy }
  let _detectTimer = null;

  // ── Eye blink state ───────────────────────────────────────────────────
  const BLINK_MIN_INTERVAL = 2500;
  const BLINK_MAX_INTERVAL = 6500;
  const BLINK_CLOSE_MS = 90;
  const BLINK_HOLD_MS = 40;
  const BLINK_OPEN_MS = 130;
  const DOUBLE_BLINK_CHANCE = 0.15;

  let _blinkState = {
    nextBlinkAt: _randomBlinkInterval(),
    phase: 'open',       // open | closing | closed | opening
    phaseStart: 0,
    closedness: 0,       // 0 = fully open, 1 = fully closed
    doubleBlinkPending: false,
  };

  function _randomBlinkInterval() {
    return BLINK_MIN_INTERVAL + Math.random() * (BLINK_MAX_INTERVAL - BLINK_MIN_INTERVAL);
  }

  // ── Breathing state ───────────────────────────────────────────────────
  const BREATH_CYCLE_MS = 4200;  // full inhale+exhale
  let _breathPhase = 0;

  // ── Micro head movement ───────────────────────────────────────────────
  let _headOffset = { x: 0, y: 0, rot: 0 };

  // ── Eye gaze ──────────────────────────────────────────────────────────
  let _gazeTarget = { x: 0.5, y: 0.45 };
  let _gazeCurrent = { x: 0.5, y: 0.45 };
  let _gazeMode = 'auto';  // 'auto' (follows mouse / drifts) or 'manual'
  let _gazeDriftPhase = 0;

  // ── Eyebrow state ─────────────────────────────────────────────────────
  let _browTarget = 0;    // -1 = furrowed, 0 = neutral, 1 = raised
  let _browCurrent = 0;

  // ── Expression system ─────────────────────────────────────────────────
  // Expressions blend multiple face parameters for emotional realism
  const EXPRESSIONS = {
    neutral:   { browRaise: 0,    lipCornerPull: 0,    eyeWiden: 0 },
    attentive: { browRaise: 0.15, lipCornerPull: 0,    eyeWiden: 0.1 },
    warm:      { browRaise: 0.1,  lipCornerPull: 0.25, eyeWiden: 0.05 },
    concerned: { browRaise: -0.2, lipCornerPull: -0.1, eyeWiden: 0.15 },
    thinking:  { browRaise: 0.2,  lipCornerPull: 0,    eyeWiden: 0 },
  };
  let _expressionName = 'neutral';
  let _expressionWeight = 0;
  let _expressionTarget = 0;
  let _expressionParams = EXPRESSIONS.neutral;

  // ── Fallback positions (% of canvas) ──────────────────────────────────
  function _fallbackMouthLm(w, h) {
    return { cx: w * 0.5, cy: h * 0.655, halfW: w * 0.1 };
  }

  function _fallbackEyeLandmarks(w, h) {
    return {
      leftEye:  { cx: w * 0.385, cy: h * 0.42, w: w * 0.065, h: w * 0.028 },
      rightEye: { cx: w * 0.615, cy: h * 0.42, w: w * 0.065, h: w * 0.028 },
    };
  }

  function _fallbackBrowLandmarks(w, h) {
    return {
      leftBrow:  { cx: w * 0.385, cy: h * 0.375 },
      rightBrow: { cx: w * 0.615, cy: h * 0.375 },
    };
  }

  // ── Initialization ────────────────────────────────────────────────────
  function init(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = '';
    container.style.position = 'relative';
    container.style.overflow = 'hidden';

    videoEl = document.createElement('video');
    videoEl.id = 'avatar-video';
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.playsInline = true;
    videoEl.autoplay = true;
    videoEl.style.cssText = 'display:none;';
    container.appendChild(videoEl);
    videoEl.addEventListener('loadedmetadata', () => { _cover = null; }, { passive: true });

    imageEl = document.createElement('img');
    imageEl.alt = 'Clinician avatar';
    imageEl.style.cssText = 'display:none;';
    container.appendChild(imageEl);
    imageEl.addEventListener('load', () => { _cover = null; }, { passive: true });

    canvasEl = document.createElement('canvas');
    canvasEl.style.cssText =
      'width:100%;height:100%;display:block;border-radius:8px;background:#0c0c0c;';
    container.appendChild(canvasEl);
    ctx = canvasEl.getContext('2d');

    const ro = new ResizeObserver(() => {
      _cover = null;
      _mouthLm = null;
      _eyeLandmarks = null;
      _browLandmarks = null;
      _resizeCanvas(container);
    });
    ro.observe(container);
    _resizeCanvas(container);

    _loadVideoSrc(_currentSources.idle);
    _loadImageSrc(_currentSources.static || _currentSources.idle);

    const fromQuery = new URLSearchParams(window.location.search).get('render');
    if (fromQuery === 'video' || fromQuery === 'static') {
      _renderMode = fromQuery;
    }

    videoEl.playbackRate = 0.85;

    // Track mouse for eye gaze
    document.addEventListener('mousemove', _onMouseMove, { passive: true });

    _startLoop();
    _initFaceMesh();
  }

  function _onMouseMove(e) {
    if (_gazeMode !== 'auto' || !canvasEl) return;
    const rect = canvasEl.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    // Normalize mouse position relative to canvas (0-1)
    const nx = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const ny = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    // Dampen the gaze — don't track 1:1, use a subtle range
    _gazeTarget.x = 0.35 + nx * 0.3;
    _gazeTarget.y = 0.35 + ny * 0.3;
  }

  function _resizeCanvas(container) {
    if (!canvasEl) return;
    canvasEl.width = container.clientWidth;
    canvasEl.height = container.clientHeight;
    _cover = null;
  }

  // ── MediaPipe FaceMesh ────────────────────────────────────────────────
  function _initFaceMesh() {
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
        refineLandmarks: true,  // v11: enable iris landmarks for better eye tracking
        minDetectionConfidence: 0.5,
        minTrackingConfidence: 0.5,
      });
      _faceMesh.onResults(_onMeshResults);
      _faceMesh.initialize().then(() => {
        _meshReady = true;
        _detectTimer = setInterval(_runDetection, 2000);
        _runDetection();
      }).catch(() => {});
    } catch (_) {}
  }

  function _onMeshResults(results) {
    const lms = results.multiFaceLandmarks?.[0];
    if (!lms || !canvasEl || canvasEl.width === 0) return;

    const w = canvasEl.width;
    const h = canvasEl.height;

    const vw = _renderMode === 'video'
      ? (videoEl ? (videoEl.videoWidth || w) : w)
      : (imageEl ? (imageEl.naturalWidth || w) : w);
    const vh = _renderMode === 'video'
      ? (videoEl ? (videoEl.videoHeight || h) : h)
      : (imageEl ? (imageEl.naturalHeight || h) : h);

    const { sx, sy, sw, sh } = _getCoverRect(w, h);
    function _pt(i) {
      const px = lms[i].x * vw;
      const py = lms[i].y * vh;
      return {
        x: ((px - sx) / (sw || 1)) * w,
        y: ((py - sy) / (sh || 1)) * h,
      };
    }

    // Mouth landmarks
    const leftCorner = _pt(61);
    const rightCorner = _pt(291);
    const upperLipTop = _pt(0);
    const cx = (leftCorner.x + rightCorner.x) / 2;
    const cy = upperLipTop.y;
    const halfW = Math.max(20, (rightCorner.x - leftCorner.x) / 2);
    if (cx > 0 && cx < w && cy > 0 && cy < h) {
      _mouthLm = { cx, cy, halfW };
    }

    // Eye landmarks (approximate using key points)
    // Left eye: 33 (outer), 133 (inner), 159 (top), 145 (bottom)
    // Right eye: 362 (outer), 263 (inner), 386 (top), 374 (bottom)
    try {
      const le33 = _pt(33), le133 = _pt(133), le159 = _pt(159), le145 = _pt(145);
      const re362 = _pt(362), re263 = _pt(263), re386 = _pt(386), re374 = _pt(374);
      _eyeLandmarks = {
        leftEye: {
          cx: (le33.x + le133.x) / 2,
          cy: (le159.y + le145.y) / 2,
          w: Math.abs(le133.x - le33.x),
          h: Math.abs(le145.y - le159.y),
        },
        rightEye: {
          cx: (re362.x + re263.x) / 2,
          cy: (re386.y + re374.y) / 2,
          w: Math.abs(re263.x - re362.x),
          h: Math.abs(re374.y - re386.y),
        },
      };
    } catch (_) {}

    // Brow landmarks (approximate)
    // Left brow: 70 (center), Right brow: 300 (center)
    try {
      const lb = _pt(70);
      const rb = _pt(300);
      _browLandmarks = {
        leftBrow: { cx: lb.x, cy: lb.y },
        rightBrow: { cx: rb.x, cy: rb.y },
      };
    } catch (_) {}

    // Nose tip: 1
    try {
      const nt = _pt(1);
      _noseLandmark = { cx: nt.x, cy: nt.y };
    } catch (_) {}
  }

  async function _runDetection() {
    if (!_meshReady) return;
    // Use image for static mode, video for video mode
    const source = _renderMode === 'video'
      ? (videoEl && videoEl.readyState >= 2 ? videoEl : null)
      : (imageEl && imageEl.complete && imageEl.naturalWidth > 0 ? imageEl : null);
    if (!source) return;
    try {
      await _faceMesh.send({ image: source });
    } catch (_) {}
  }

  // ── Cover rect calculation ────────────────────────────────────────────
  function _getCoverRect(w, h) {
    if (_cover) return _cover;

    const vw = _renderMode === 'video'
      ? (videoEl ? videoEl.videoWidth : 0)
      : (imageEl ? imageEl.naturalWidth : 0);
    const vh = _renderMode === 'video'
      ? (videoEl ? videoEl.videoHeight : 0)
      : (imageEl ? imageEl.naturalHeight : 0);

    if (!vw || !vh) return { sx: 0, sy: 0, sw: w, sh: h };

    const cAR = w / h;
    const vAR = vw / vh;
    let sx, sy, sw, sh;

    if (cAR > vAR) {
      sw = vw;
      sh = Math.round(vw / cAR);
      sx = 0;
      sy = Math.round((vh - sh) * 0.5);
    } else {
      sh = vh;
      sw = Math.round(vh * cAR);
      sx = Math.round((vw - sw) / 2);
      sy = 0;
    }

    _cover = { sx, sy, sw, sh };
    return _cover;
  }

  // ── Source management ─────────────────────────────────────────────────
  function setAvatar(avatarKey) {
    _currentSources = AVATAR_SOURCES[avatarKey] || AVATAR_SOURCES.male_black;
    _loadVideoSrc(_state === 'speaking' ? _currentSources.speaking : _currentSources.idle);
    _loadImageSrc(_currentSources.static || _currentSources.idle);
  }

  function setRenderMode(mode) {
    const normalized = String(mode || '').trim().toLowerCase();
    _renderMode = normalized === 'video' ? 'video' : 'static';
    _cover = null;
    if (videoEl) {
      if (_renderMode === 'video') {
        videoEl.play().catch(() => {});
      } else {
        try { videoEl.pause(); } catch (_) {}
      }
    }
  }

  function _loadVideoSrc(src) {
    if (!videoEl || !src) return;
    const abs = new URL(src, window.location.href).href;
    if (videoEl.src === abs) return;
    const t = videoEl.currentTime;
    videoEl.src = src;
    videoEl.load();
    videoEl.currentTime = t % 5;
    videoEl.play().catch(() => {});
    _cover = null;
  }

  function _loadImageSrc(src) {
    if (!imageEl || !src) return;
    const abs = new URL(src, window.location.href).href;
    if (imageEl.src === abs) return;
    imageEl.src = src;
    _cover = null;
  }

  // ── State management ──────────────────────────────────────────────────
  function setState(state) {
    const prev = _state;
    _state = state;
    if (!_currentSources) return;
    if (state === 'speaking' && prev !== 'speaking') {
      _loadVideoSrc(_currentSources.speaking);
      if (videoEl) videoEl.playbackRate = 1.0;
      // Warm expression during speaking
      setExpression('warm', 0.3);
    } else if (state === 'thinking' && prev !== 'thinking') {
      setExpression('thinking', 0.4);
    } else if (state === 'listening' && prev !== 'listening') {
      setExpression('attentive', 0.35);
    } else if (state !== 'speaking' && prev === 'speaking') {
      _loadVideoSrc(_currentSources.idle);
      if (videoEl) videoEl.playbackRate = 0.85;
      setExpression('neutral', 0);
    } else if (state === 'idle' && prev !== 'idle') {
      setExpression('neutral', 0);
    }
  }

  // ── Viseme application (API unchanged) ────────────────────────────────
  function applyViseme(weight) {
    const target = Math.max(0, Math.min(1, weight || 0));
    _speaking += (target - _speaking) * 0.25;
    _jawOpen += (target - _jawOpen) * 0.4;
  }

  function applyVisemeParams({
    jawOpen = 0, mouthWidth = 0.5, lipPucker = 0, rms = 0,
    upperLipRaise = 0, lipCornerPull = 0, tongueShow = 0,
  } = {}) {
    _jawOpen += (Math.min(1, jawOpen) - _jawOpen) * 0.4;
    _mouthWidth += (Math.min(1, mouthWidth) - _mouthWidth) * 0.3;
    _lipPucker += (Math.min(1, lipPucker) - _lipPucker) * 0.25;
    _speaking += (Math.min(1, rms) - _speaking) * 0.25;
    _upperLipRaise += (Math.min(1, upperLipRaise) - _upperLipRaise) * 0.3;
    _lipCornerPull += (Math.max(-1, Math.min(1, lipCornerPull)) - _lipCornerPull) * 0.25;
    _tongueShow += (Math.min(1, tongueShow) - _tongueShow) * 0.3;
  }

  // ── Expression system ─────────────────────────────────────────────────
  function setExpression(name, weight) {
    if (EXPRESSIONS[name]) {
      _expressionName = name;
      _expressionParams = EXPRESSIONS[name];
      _expressionTarget = Math.max(0, Math.min(1, weight || 0));
    }
  }

  function setGazeTarget(nx, ny) {
    _gazeMode = 'manual';
    _gazeTarget.x = Math.max(0, Math.min(1, nx));
    _gazeTarget.y = Math.max(0, Math.min(1, ny));
  }

  // ── Animation loop ────────────────────────────────────────────────────
  function _startLoop() {
    if (_animId) return;
    function loop(ts) {
      _animId = requestAnimationFrame(loop);
      const dt = ts - _lastTs;
      _lastTs = ts;
      _elapsedMs += dt;
      _updateIdleAnimations(dt);
      _drawFrame();
    }
    _animId = requestAnimationFrame((ts) => {
      _lastTs = ts;
      loop(ts);
    });
  }

  // ── Idle animation update (runs every frame) ─────────────────────────
  function _updateIdleAnimations(dt) {
    if (!dt || dt > 500) return; // Skip huge jumps (tab was hidden)

    // ── 1. Eye blinking ───────────────────────────────────────────────
    _blinkState.nextBlinkAt -= dt;

    switch (_blinkState.phase) {
      case 'open':
        if (_blinkState.nextBlinkAt <= 0) {
          _blinkState.phase = 'closing';
          _blinkState.phaseStart = 0;
          _blinkState.doubleBlinkPending = Math.random() < DOUBLE_BLINK_CHANCE;
        }
        _blinkState.closedness += (0 - _blinkState.closedness) * 0.3;
        break;

      case 'closing':
        _blinkState.phaseStart += dt;
        _blinkState.closedness += (1 - _blinkState.closedness) * 0.35;
        if (_blinkState.phaseStart >= BLINK_CLOSE_MS) {
          _blinkState.phase = 'closed';
          _blinkState.phaseStart = 0;
          _blinkState.closedness = 1;
        }
        break;

      case 'closed':
        _blinkState.phaseStart += dt;
        _blinkState.closedness = 1;
        if (_blinkState.phaseStart >= BLINK_HOLD_MS) {
          _blinkState.phase = 'opening';
          _blinkState.phaseStart = 0;
        }
        break;

      case 'opening':
        _blinkState.phaseStart += dt;
        _blinkState.closedness += (0 - _blinkState.closedness) * 0.3;
        if (_blinkState.phaseStart >= BLINK_OPEN_MS) {
          if (_blinkState.doubleBlinkPending) {
            _blinkState.doubleBlinkPending = false;
            _blinkState.phase = 'closing';
            _blinkState.phaseStart = 0;
          } else {
            _blinkState.phase = 'open';
            _blinkState.closedness = 0;
            _blinkState.nextBlinkAt = _randomBlinkInterval();
            // Blink more during thinking
            if (_state === 'thinking') {
              _blinkState.nextBlinkAt *= 0.6;
            }
          }
        }
        break;
    }

    // ── 2. Breathing ──────────────────────────────────────────────────
    _breathPhase += (dt / BREATH_CYCLE_MS) * Math.PI * 2;
    if (_breathPhase > Math.PI * 2) _breathPhase -= Math.PI * 2;

    // ── 3. Micro head movement (multi-frequency Perlin-like) ──────────
    const t = _elapsedMs / 1000;
    _headOffset.x = Math.sin(t * 0.37) * 1.2 + Math.sin(t * 0.83) * 0.5;
    _headOffset.y = Math.sin(t * 0.29) * 0.7 + Math.sin(t * 0.67) * 0.3 + Math.cos(t * 1.1) * 0.2;
    _headOffset.rot = Math.sin(t * 0.19) * 0.15 + Math.sin(t * 0.53) * 0.08;

    // ── 4. Eye gaze drift (when not tracking mouse) ───────────────────
    if (_gazeMode === 'auto') {
      _gazeDriftPhase += dt * 0.001;
      // Subtle autonomous gaze drift
      const baseDriftX = 0.5 + Math.sin(_gazeDriftPhase * 0.4) * 0.05 + Math.sin(_gazeDriftPhase * 0.13) * 0.03;
      const baseDriftY = 0.45 + Math.sin(_gazeDriftPhase * 0.3) * 0.03;
      // Blend: mouse tracking (if active) vs. drift
      const mouseActive = Date.now() - _lastMouseMove < 3000;
      if (!mouseActive) {
        _gazeTarget.x = baseDriftX;
        _gazeTarget.y = baseDriftY;
      }
    }
    // Smooth gaze interpolation
    _gazeCurrent.x += (_gazeTarget.x - _gazeCurrent.x) * 0.08;
    _gazeCurrent.y += (_gazeTarget.y - _gazeCurrent.y) * 0.08;

    // ── 5. Eyebrow ────────────────────────────────────────────────────
    // Brow target from expression
    _browTarget = _expressionParams.browRaise * _expressionWeight;
    // Add subtle brow movement during speech
    if (_state === 'speaking' && _jawOpen > 0.3) {
      _browTarget += 0.08;
    }
    _browCurrent += (_browTarget - _browCurrent) * 0.06;

    // ── 6. Expression blend ───────────────────────────────────────────
    _expressionWeight += (_expressionTarget - _expressionWeight) * 0.04;
    // Apply expression lip corner pull
    const exprCorner = _expressionParams.lipCornerPull * _expressionWeight;
    _lipCornerPull += (exprCorner - _lipCornerPull) * 0.03;
  }

  let _lastMouseMove = 0;
  const _origOnMouseMove = _onMouseMove;
  // Patch mouse move to track recency
  function _onMouseMovePatched(e) {
    _lastMouseMove = Date.now();
    _origOnMouseMove(e);
  }

  // ── Main draw frame ───────────────────────────────────────────────────
  function _drawFrame() {
    if (!ctx || !canvasEl || canvasEl.width === 0) return;
    const w = canvasEl.width;
    const h = canvasEl.height;
    ctx.clearRect(0, 0, w, h);

    // ── Apply breathing + micro head movement as canvas transform ──────
    const breathScale = 1 + Math.sin(_breathPhase) * 0.002;
    const breathY = Math.sin(_breathPhase) * -0.8;  // slight rise on inhale
    const hx = _headOffset.x;
    const hy = _headOffset.y + breathY;
    const hRot = _headOffset.rot * (Math.PI / 180);

    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.rotate(hRot);
    ctx.scale(breathScale, breathScale);
    ctx.translate(-w / 2 + hx, -h / 2 + hy);

    // ── Draw base image or video ──────────────────────────────────────
    if (_renderMode === 'video' && videoEl && videoEl.readyState >= 2) {
      const { sx, sy, sw, sh } = _getCoverRect(w, h);
      ctx.save();
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(0, 0, w, h, 8);
      else ctx.rect(0, 0, w, h);
      ctx.clip();
      ctx.drawImage(videoEl, sx, sy, sw, sh, 0, 0, w, h);
      ctx.restore();
    } else if (imageEl && imageEl.complete && imageEl.naturalWidth > 0) {
      const { sx, sy, sw, sh } = _getCoverRect(w, h);
      ctx.save();
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(0, 0, w, h, 8);
      else ctx.rect(0, 0, w, h);
      ctx.clip();
      ctx.drawImage(imageEl, sx, sy, sw, sh, 0, 0, w, h);
      ctx.restore();
    }

    // ── Draw eye blinks ───────────────────────────────────────────────
    if (_blinkState.closedness > 0.05) {
      _drawEyeBlink(w, h);
    }

    // ── Draw eyebrow animation ────────────────────────────────────────
    if (Math.abs(_browCurrent) > 0.02) {
      _drawBrowShift(w, h);
    }

    // ── Draw eye gaze shift (pupil highlights) ────────────────────────
    _drawGazeHighlight(w, h);

    // ── Draw mouth ────────────────────────────────────────────────────
    const activeLm = _mouthLm || _fallbackMouthLm(w, h);
    if (_jawOpen > 0.015 || _lipCornerPull > 0.02) {
      _drawMouth(activeLm.cx, activeLm.cy, activeLm.halfW, w, h);
    }

    // ── Draw nasolabial folds (deepen during speech/smile) ────────────
    if (_jawOpen > 0.1 || _lipCornerPull > 0.05) {
      _drawNasolabialFolds(activeLm.cx, activeLm.cy, activeLm.halfW, w, h);
    }

    ctx.restore();  // Undo breathing/head transform

    // ── State indicators (drawn OUTSIDE the head transform) ───────────
    if (_state === 'thinking') {
      const pulse = 0.5 + 0.5 * Math.sin(_elapsedMs / 400);
      ctx.save();
      const tlm = _mouthLm || _fallbackMouthLm(w, h);
      ctx.strokeStyle = `rgba(56,189,248,${(0.55 * pulse).toFixed(3)})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(tlm.cx, tlm.cy, 28 + pulse * 8, 12 + pulse * 4, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (_state === 'listening') {
      const pulse = 0.6 + 0.4 * Math.sin(_elapsedMs / 300);
      ctx.save();
      ctx.fillStyle = `rgba(52,211,153,${pulse.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(w * 0.88, h * 0.06, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    if (_state === 'speaking' && _speaking > 0.01) {
      _drawSpeakingBars(w, h);
    }

    // ── Decay parameters ──────────────────────────────────────────────
    _jawOpen *= 0.93;
    _mouthWidth += (0.5 - _mouthWidth) * 0.04;
    _lipPucker *= 0.93;
    _speaking *= 0.92;
    _upperLipRaise *= 0.93;
    _tongueShow *= 0.93;
  }

  // ── Eye blink overlay ─────────────────────────────────────────────────
  function _drawEyeBlink(w, h) {
    const eyes = _eyeLandmarks || _fallbackEyeLandmarks(w, h);
    const closedness = Math.min(1, _blinkState.closedness);
    if (closedness < 0.05) return;

    // Sample skin color near each eye for the eyelid
    const sr = _skinRGB ? _skinRGB.r : 85;
    const sg = _skinRGB ? _skinRGB.g : 58;
    const sb = _skinRGB ? _skinRGB.b : 48;

    // Slightly darker for eyelid crease
    const lr = Math.round(sr * 0.88);
    const lg = Math.round(sg * 0.88);
    const lb = Math.round(sb * 0.88);

    ctx.save();

    for (const eye of [eyes.leftEye, eyes.rightEye]) {
      const eyeW = eye.w * 1.4;
      const eyeH = eye.h * 2.2;
      const lidDrop = closedness * eyeH * 0.5;

      // Upper eyelid descending
      const grad = ctx.createRadialGradient(
        eye.cx, eye.cy - eyeH * 0.15, eyeW * 0.15,
        eye.cx, eye.cy - eyeH * 0.15, eyeW * 0.7
      );
      grad.addColorStop(0, `rgba(${sr},${sg},${sb},${(closedness * 0.95).toFixed(2)})`);
      grad.addColorStop(0.6, `rgba(${sr},${sg},${sb},${(closedness * 0.85).toFixed(2)})`);
      grad.addColorStop(1, `rgba(${sr},${sg},${sb},0)`);

      ctx.fillStyle = grad;
      ctx.beginPath();
      // Draw eyelid as arc that descends
      ctx.ellipse(eye.cx, eye.cy - eyeH * 0.2 + lidDrop * 0.4, eyeW * 0.65, eyeH * 0.5 * closedness, 0, 0, Math.PI);
      ctx.fill();

      // Eyelid crease line (subtle)
      if (closedness > 0.3) {
        ctx.strokeStyle = `rgba(${lr},${lg},${lb},${(closedness * 0.35).toFixed(2)})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.ellipse(eye.cx, eye.cy - eyeH * 0.15 + lidDrop * 0.3, eyeW * 0.55, eyeH * 0.15 * closedness, 0, 0.1, Math.PI - 0.1);
        ctx.stroke();
      }

      // Lower eyelid rising slightly
      if (closedness > 0.5) {
        const lowerLidRise = (closedness - 0.5) * 2; // 0-1
        const lGrad = ctx.createRadialGradient(
          eye.cx, eye.cy + eyeH * 0.3, eyeW * 0.1,
          eye.cx, eye.cy + eyeH * 0.3, eyeW * 0.6
        );
        lGrad.addColorStop(0, `rgba(${sr},${sg},${sb},${(lowerLidRise * 0.7).toFixed(2)})`);
        lGrad.addColorStop(1, `rgba(${sr},${sg},${sb},0)`);
        ctx.fillStyle = lGrad;
        ctx.beginPath();
        ctx.ellipse(eye.cx, eye.cy + eyeH * 0.25 - lowerLidRise * eyeH * 0.15, eyeW * 0.55, eyeH * 0.3 * lowerLidRise, 0, Math.PI, 0);
        ctx.fill();
      }
    }

    ctx.restore();
  }

  // ── Eyebrow shift overlay ─────────────────────────────────────────────
  function _drawBrowShift(w, h) {
    if (!_skinRGB) return;
    const brows = _browLandmarks || _fallbackBrowLandmarks(w, h);
    const shift = _browCurrent;  // positive = raise, negative = furrow
    const sr = _skinRGB.r, sg = _skinRGB.g, sb = _skinRGB.b;

    ctx.save();

    for (const brow of [brows.leftBrow, brows.rightBrow]) {
      const browW = w * 0.065;
      const browH = w * 0.015;
      const offsetY = -shift * w * 0.008; // Raise/lower the brow area

      // Draw a subtle skin-tone overlay above the brow to simulate movement
      // This creates the illusion of the brow shifting
      const grad = ctx.createRadialGradient(
        brow.cx, brow.cy + offsetY, browW * 0.2,
        brow.cx, brow.cy + offsetY, browW * 0.8
      );
      const intensity = Math.abs(shift) * 0.25;
      // Slightly lighter when raised (more forehead visible), darker when furrowed
      const mod = shift > 0 ? 1.05 : 0.92;
      grad.addColorStop(0, `rgba(${Math.round(sr * mod)},${Math.round(sg * mod)},${Math.round(sb * mod)},${intensity.toFixed(2)})`);
      grad.addColorStop(1, `rgba(${sr},${sg},${sb},0)`);

      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(brow.cx, brow.cy + offsetY * 0.5, browW, browH * 3, 0, 0, Math.PI * 2);
      ctx.fill();

      // Furrow crease lines (when browCurrent < -0.1)
      if (shift < -0.1) {
        const creaseAlpha = Math.min(0.2, Math.abs(shift) * 0.3);
        ctx.strokeStyle = `rgba(${Math.round(sr * 0.7)},${Math.round(sg * 0.7)},${Math.round(sb * 0.7)},${creaseAlpha.toFixed(2)})`;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(brow.cx - browW * 0.3, brow.cy + browH * 2);
        ctx.quadraticCurveTo(brow.cx, brow.cy + browH * 1.5, brow.cx + browW * 0.3, brow.cy + browH * 2);
        ctx.stroke();
      }
    }

    ctx.restore();
  }

  // ── Eye gaze highlight ────────────────────────────────────────────────
  function _drawGazeHighlight(w, h) {
    const eyes = _eyeLandmarks || _fallbackEyeLandmarks(w, h);
    // Gaze offset: how far the pupil shifts (very subtle, 1-3px)
    const gazeX = (_gazeCurrent.x - 0.5) * 3;
    const gazeY = (_gazeCurrent.y - 0.45) * 2;

    ctx.save();
    ctx.globalCompositeOperation = 'soft-light';

    for (const eye of [eyes.leftEye, eyes.rightEye]) {
      // Tiny specular highlight that shifts with gaze direction
      const hlX = eye.cx + gazeX;
      const hlY = eye.cy + gazeY;
      const hlR = eye.w * 0.08;

      const hlGrad = ctx.createRadialGradient(hlX, hlY, 0, hlX, hlY, hlR);
      hlGrad.addColorStop(0, 'rgba(255,255,255,0.15)');
      hlGrad.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = hlGrad;
      ctx.beginPath();
      ctx.arc(hlX, hlY, hlR, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }

  // ── Nasolabial folds ──────────────────────────────────────────────────
  function _drawNasolabialFolds(cx, cy, halfW, w, h) {
    if (!_skinRGB) return;
    const sr = _skinRGB.r, sg = _skinRGB.g, sb = _skinRGB.b;
    const depth = Math.min(0.2, (_jawOpen * 0.15 + Math.max(0, _lipCornerPull) * 0.2));
    if (depth < 0.02) return;

    ctx.save();
    ctx.strokeStyle = `rgba(${Math.round(sr * 0.7)},${Math.round(sg * 0.7)},${Math.round(sb * 0.7)},${depth.toFixed(2)})`;
    ctx.lineWidth = 1.2;
    ctx.lineCap = 'round';

    // Left nasolabial fold
    const noseY = _noseLandmark ? _noseLandmark.cy : cy - halfW * 1.2;
    const foldStartY = noseY + halfW * 0.3;

    ctx.beginPath();
    ctx.moveTo(cx - halfW * 0.6, foldStartY);
    ctx.quadraticCurveTo(
      cx - halfW * 0.85, foldStartY + halfW * 0.6,
      cx - halfW * 0.7, cy + halfW * 0.3
    );
    ctx.stroke();

    // Right nasolabial fold
    ctx.beginPath();
    ctx.moveTo(cx + halfW * 0.6, foldStartY);
    ctx.quadraticCurveTo(
      cx + halfW * 0.85, foldStartY + halfW * 0.6,
      cx + halfW * 0.7, cy + halfW * 0.3
    );
    ctx.stroke();

    ctx.restore();
  }

  // ── Enhanced mouth drawing ────────────────────────────────────────────
  function _drawMouth(cx, cy, halfW, w, h) {
    // Adaptive skin-colour sampling
    if (!_skinRGB || ++_skinSampleFrame % 60 === 0) {
      try {
        const sy = Math.max(0, Math.round(cy - halfW * 0.55));
        const sx = Math.round(cx);
        if (sx > 0 && sx < w && sy > 0 && sy < h) {
          const p = ctx.getImageData(sx, sy, 1, 1).data;
          _skinRGB = { r: p[0], g: p[1], b: p[2] };
        }
      } catch (_e) {}
      if (!_skinRGB) _skinRGB = { r: 85, g: 58, b: 48 };
    }

    const jaw = _jawOpen;
    const spread = _mouthWidth;
    const pucker = _lipPucker;
    const ulRaise = _upperLipRaise;
    const cornerPull = _lipCornerPull;

    // Dynamic mouth geometry
    const baseW = halfW * 1.05;
    const lipW = baseW * (0.55 + spread * 0.45) * (1 - pucker * 0.35);
    // Corner pull widens the mouth slightly
    const cornerWiden = Math.max(0, cornerPull) * baseW * 0.1;
    const effectiveLipW = lipW + cornerWiden;
    const maxOpen = halfW * 0.55;
    const openH = jaw * maxOpen * (1 - pucker * 0.15);
    if (openH < 1 && Math.abs(cornerPull) < 0.02) return;

    const mCY = cy + openH * 0.3;
    const sr = _skinRGB.r, sg = _skinRGB.g, sb = _skinRGB.b;

    ctx.save();

    // 1 — Feathered skin-tone patch (improved multi-layer blending)
    const maskR = effectiveLipW * 1.4;
    const maskH = Math.max(openH * 1.5, halfW * 0.3);

    // Layer 1: broad soft blend
    const mGrad1 = ctx.createRadialGradient(cx, mCY, maskR * 0.1, cx, mCY, maskR * 1.1);
    mGrad1.addColorStop(0, `rgba(${sr},${sg},${sb},0.88)`);
    mGrad1.addColorStop(0.35, `rgba(${sr},${sg},${sb},0.75)`);
    mGrad1.addColorStop(0.65, `rgba(${sr},${sg},${sb},0.35)`);
    mGrad1.addColorStop(0.85, `rgba(${sr},${sg},${sb},0.1)`);
    mGrad1.addColorStop(1, `rgba(${sr},${sg},${sb},0)`);
    ctx.fillStyle = mGrad1;
    ctx.beginPath();
    ctx.ellipse(cx, mCY, maskR * 1.05, maskH * 1.1, 0, 0, Math.PI * 2);
    ctx.fill();

    // Layer 2: tighter center patch for clean mouth area
    const mGrad2 = ctx.createRadialGradient(cx, mCY, 0, cx, mCY, maskR * 0.7);
    mGrad2.addColorStop(0, `rgba(${sr},${sg},${sb},0.95)`);
    mGrad2.addColorStop(0.7, `rgba(${sr},${sg},${sb},0.6)`);
    mGrad2.addColorStop(1, `rgba(${sr},${sg},${sb},0)`);
    ctx.fillStyle = mGrad2;
    ctx.beginPath();
    ctx.ellipse(cx, mCY, maskR * 0.75, maskH * 0.8, 0, 0, Math.PI * 2);
    ctx.fill();

    // 2 — Mouth cavity
    const cavW = effectiveLipW * 0.82;
    const cavH = Math.max(openH * 0.62, 1);
    if (cavW > 1 && openH > 1) {
      // Inner mouth gradient with depth
      const cGrad = ctx.createRadialGradient(cx, mCY, 0, cx, mCY, Math.max(cavW, cavH));
      cGrad.addColorStop(0, 'rgba(6,1,1,0.97)');
      cGrad.addColorStop(0.3, 'rgba(12,4,3,0.94)');
      cGrad.addColorStop(0.6, 'rgba(22,8,6,0.85)');
      cGrad.addColorStop(1, 'rgba(35,15,10,0)');
      ctx.fillStyle = cGrad;
      ctx.beginPath();
      ctx.ellipse(cx, mCY, cavW, cavH, 0, 0, Math.PI * 2);
      ctx.fill();

      // Upper teeth — visible when jaw > 0.18 (lowered threshold for more visibility)
      if (jaw > 0.18) {
        const ta = Math.min(0.85, (jaw - 0.18) / 0.5);
        // Individual tooth suggestions via slight gradient variation
        const teethW = cavW * 0.72;
        const teethH = cavH * 0.24;
        const teethY = mCY - cavH * 0.5;

        ctx.fillStyle = `rgba(240,236,230,${ta.toFixed(2)})`;
        ctx.beginPath();
        ctx.ellipse(cx, teethY, teethW, teethH, 0, Math.PI, 0);
        ctx.fill();

        // Tooth separation lines (very subtle)
        if (jaw > 0.3 && ta > 0.3) {
          ctx.strokeStyle = `rgba(200,195,188,${(ta * 0.25).toFixed(2)})`;
          ctx.lineWidth = 0.5;
          const toothCount = 6;
          const toothSpan = teethW * 1.6;
          const startX = cx - toothSpan / 2;
          for (let i = 1; i < toothCount; i++) {
            const tx = startX + (toothSpan / toothCount) * i;
            ctx.beginPath();
            ctx.moveTo(tx, teethY - teethH * 0.6);
            ctx.lineTo(tx, teethY + teethH * 0.1);
            ctx.stroke();
          }
        }

        // Lower teeth hint at wide open
        if (jaw > 0.45) {
          const lta = Math.min(0.5, (jaw - 0.45) / 0.5);
          ctx.fillStyle = `rgba(235,231,225,${lta.toFixed(2)})`;
          ctx.beginPath();
          ctx.ellipse(cx, mCY + cavH * 0.4, teethW * 0.6, teethH * 0.7, 0, 0, Math.PI);
          ctx.fill();
        }
      }

      // Tongue — visible when jaw > 0.35 or tongueShow > 0
      const tongueVis = Math.max(jaw > 0.35 ? (jaw - 0.35) / 0.5 : 0, _tongueShow);
      if (tongueVis > 0.02) {
        const tA = Math.min(0.65, tongueVis * 0.65);
        // Tongue with gradient for depth
        const tGrad = ctx.createRadialGradient(
          cx, mCY + cavH * 0.15, cavW * 0.1,
          cx, mCY + cavH * 0.25, cavW * 0.45
        );
        tGrad.addColorStop(0, `rgba(185,95,85,${tA.toFixed(2)})`);
        tGrad.addColorStop(0.7, `rgba(165,78,68,${(tA * 0.8).toFixed(2)})`);
        tGrad.addColorStop(1, `rgba(145,65,55,0)`);
        ctx.fillStyle = tGrad;
        ctx.beginPath();
        ctx.ellipse(cx, mCY + cavH * 0.2, cavW * 0.42, cavH * 0.32, 0, 0, Math.PI);
        ctx.fill();
      }
    }

    // 3 — Lip curves (enhanced with more anatomical detail)
    const lr = Math.round(sr * 0.55 + 130 * 0.45);
    const lg = Math.round(sg * 0.35 + 48 * 0.65);
    const lb = Math.round(sb * 0.35 + 42 * 0.65);
    const lt = Math.max(1.5, halfW * 0.058);

    // Corner pull adjusts lip endpoint Y positions (smile lifts corners)
    const cornerLiftY = -Math.max(0, cornerPull) * lt * 2;
    const cornerDropY = Math.max(0, -cornerPull) * lt * 1.5;
    const cornerEndY = cy + cornerLiftY + cornerDropY;

    // Upper lip — cupid's bow via cubic bezier (with upper lip raise)
    const ulOffset = -ulRaise * lt * 0.8;
    ctx.beginPath();
    ctx.moveTo(cx - effectiveLipW, cornerEndY);
    ctx.bezierCurveTo(
      cx - effectiveLipW * 0.55, cy - lt * 1.0 + ulOffset,
      cx - effectiveLipW * 0.15, cy - lt * 0.6 + ulOffset,
      cx, cy - lt * 0.25 + ulOffset,
    );
    ctx.bezierCurveTo(
      cx + effectiveLipW * 0.15, cy - lt * 0.6 + ulOffset,
      cx + effectiveLipW * 0.55, cy - lt * 1.0 + ulOffset,
      cx + effectiveLipW, cornerEndY,
    );
    ctx.strokeStyle = `rgba(${lr},${lg},${lb},0.72)`;
    ctx.lineWidth = lt;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();

    // Upper lip fill (subtle volume)
    if (openH > 2) {
      ctx.fillStyle = `rgba(${lr},${lg},${lb},0.18)`;
      ctx.fill();
    }

    // Lower lip — fuller, slightly wider arc
    const lowY = cy + openH * 0.65;
    ctx.beginPath();
    ctx.moveTo(cx - effectiveLipW * 0.88, lowY + cornerLiftY * 0.4);
    ctx.quadraticCurveTo(cx, lowY + lt * 1.4, cx + effectiveLipW * 0.88, lowY + cornerLiftY * 0.4);
    ctx.strokeStyle = `rgba(${lr},${lg},${lb},0.58)`;
    ctx.lineWidth = lt * 1.2;
    ctx.stroke();

    // Lower lip moisture highlight (specular)
    if (openH > 3) {
      const hlGrad = ctx.createLinearGradient(cx - effectiveLipW * 0.4, lowY, cx + effectiveLipW * 0.4, lowY);
      hlGrad.addColorStop(0, 'rgba(255,255,255,0)');
      hlGrad.addColorStop(0.3, `rgba(255,255,255,${(0.08 + _speaking * 0.04).toFixed(2)})`);
      hlGrad.addColorStop(0.5, `rgba(255,255,255,${(0.12 + _speaking * 0.06).toFixed(2)})`);
      hlGrad.addColorStop(0.7, `rgba(255,255,255,${(0.08 + _speaking * 0.04).toFixed(2)})`);
      hlGrad.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.strokeStyle = hlGrad;
      ctx.lineWidth = lt * 0.4;
      ctx.beginPath();
      ctx.moveTo(cx - effectiveLipW * 0.5, lowY + lt * 0.3);
      ctx.quadraticCurveTo(cx, lowY + lt * 0.8, cx + effectiveLipW * 0.5, lowY + lt * 0.3);
      ctx.stroke();
    }

    // Lip corner commissures (subtle shadow at mouth corners)
    if (openH > 2) {
      const commAlpha = Math.min(0.25, jaw * 0.2 + Math.abs(cornerPull) * 0.15);
      ctx.fillStyle = `rgba(${Math.round(sr * 0.6)},${Math.round(sg * 0.5)},${Math.round(sb * 0.5)},${commAlpha.toFixed(2)})`;

      // Left commissure
      ctx.beginPath();
      ctx.arc(cx - effectiveLipW * 0.95, cornerEndY + openH * 0.15, lt * 0.6, 0, Math.PI * 2);
      ctx.fill();

      // Right commissure
      ctx.beginPath();
      ctx.arc(cx + effectiveLipW * 0.95, cornerEndY + openH * 0.15, lt * 0.6, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }

  // ── Speaking indicator bars ───────────────────────────────────────────
  function _drawSpeakingBars(w, h) {
    const intensity = _speaking;
    const BAR_COUNT = 12;
    const BAR_W = Math.max(3, w / (BAR_COUNT * 4));
    const BAR_GAP = BAR_W * 0.6;
    const totalW = BAR_COUNT * (BAR_W + BAR_GAP) - BAR_GAP;
    const startX = (w - totalW) / 2;
    const BASE_Y = h - 10;
    const MAX_H = h * 0.1;
    ctx.save();
    for (let i = 0; i < BAR_COUNT; i++) {
      const phase = _elapsedMs / 180 + (i / BAR_COUNT) * Math.PI * 2;
      const wave = 0.45 + 0.55 * Math.abs(Math.sin(phase));
      const barH = Math.max(3, MAX_H * intensity * wave);
      const x = startX + i * (BAR_W + BAR_GAP);
      const alpha = 0.55 + intensity * 0.45;
      const grad = ctx.createLinearGradient(x, BASE_Y - barH, x, BASE_Y);
      grad.addColorStop(0, `rgba(99,232,255,${alpha.toFixed(2)})`);
      grad.addColorStop(1, `rgba(56,189,248,${(alpha * 0.4).toFixed(2)})`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x, BASE_Y - barH, BAR_W, barH, 2);
      else ctx.rect(x, BASE_Y - barH, BAR_W, barH);
      ctx.fill();
    }
    ctx.restore();
  }

  // ── Patch mouse handler on init ───────────────────────────────────────
  // Replace with patched version that tracks recency
  function _setupMouseTracking() {
    document.removeEventListener('mousemove', _onMouseMove, { passive: true });
    document.addEventListener('mousemove', _onMouseMovePatched, { passive: true });
  }

  // Override init to also set up mouse tracking
  const _origInit = init;
  function _patchedInit(containerId) {
    _origInit(containerId);
    _setupMouseTracking();
  }

  return {
    init: _patchedInit,
    setAvatar,
    setRenderMode,
    applyViseme,
    applyVisemeParams,
    setState,
    setExpression,
    setGazeTarget,
  };
})();
