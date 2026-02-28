/**
 * AvatarRenderer
 * - Supports static image mode (default) and video loop mode.
 * - Uses amplitude-driven jaw morph and visual overlays.
 * - Keeps MediaPipe landmark enhancement when available.
 */
window.AvatarRenderer = (() => {
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
  let _speaking = 0;
  let _state = 'idle';
  let _blinkT = 0;
  let _lastTs = 0;
  let _cover = null;

  let _faceMesh = null;
  let _meshReady = false;
  let _mouthLm = null;
  let _detectTimer = null;

  function _fallbackMouthLm(w, h) {
    return { cx: w * 0.5, cy: h * 0.655, halfW: w * 0.1 };
  }

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
    videoEl.addEventListener('loadedmetadata', () => {
      _cover = null;
    }, { passive: true });

    imageEl = document.createElement('img');
    imageEl.alt = 'Clinician avatar';
    imageEl.style.cssText = 'display:none;';
    container.appendChild(imageEl);
    imageEl.addEventListener('load', () => {
      _cover = null;
    }, { passive: true });

    canvasEl = document.createElement('canvas');
    canvasEl.style.cssText =
      'width:100%;height:100%;display:block;border-radius:8px;background:#0c0c0c;';
    container.appendChild(canvasEl);
    ctx = canvasEl.getContext('2d');

    const ro = new ResizeObserver(() => {
      _cover = null;
      _mouthLm = null;
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
    _startLoop();
    _initFaceMesh();
  }

  function _resizeCanvas(container) {
    if (!canvasEl) return;
    canvasEl.width = container.clientWidth;
    canvasEl.height = container.clientHeight;
    _cover = null;
  }

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
        refineLandmarks: false,
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

    const leftCorner = _pt(61);
    const rightCorner = _pt(291);
    const upperLipTop = _pt(0);

    const cx = (leftCorner.x + rightCorner.x) / 2;
    const cy = upperLipTop.y;
    const halfW = Math.max(20, (rightCorner.x - leftCorner.x) / 2);

    if (cx < 0 || cx > w || cy < 0 || cy > h) return;
    _mouthLm = { cx, cy, halfW };
  }

  async function _runDetection() {
    if (!_meshReady || !videoEl || videoEl.readyState < 2) return;
    try {
      await _faceMesh.send({ image: videoEl });
    } catch (_) {}
  }

  function _getCoverRect(w, h) {
    if (_cover) return _cover;

    const vw = _renderMode === 'video'
      ? (videoEl ? videoEl.videoWidth : 0)
      : (imageEl ? imageEl.naturalWidth : 0);
    const vh = _renderMode === 'video'
      ? (videoEl ? videoEl.videoHeight : 0)
      : (imageEl ? imageEl.naturalHeight : 0);

    if (!vw || !vh) {
      return { sx: 0, sy: 0, sw: w, sh: h };
    }

    const cAR = w / h;
    const vAR = vw / vh;
    let sx;
    let sy;
    let sw;
    let sh;

    if (cAR > vAR) {
      sw = vw;
      sh = Math.round(vw / cAR);
      sx = 0;
      // Bias crop 10% lower than center to give headroom above the avatar
      sy = Math.round((vh - sh) * 0.4);
    } else {
      sh = vh;
      sw = Math.round(vh * cAR);
      sx = Math.round((vw - sw) / 2);
      sy = 0;
    }

    _cover = { sx, sy, sw, sh };
    return _cover;
  }

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
        try {
          videoEl.pause();
        } catch (_) {}
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

  function setState(state) {
    const prev = _state;
    _state = state;
    if (!_currentSources) return;
    if (state === 'speaking' && prev !== 'speaking') {
      _loadVideoSrc(_currentSources.speaking);
      if (videoEl) videoEl.playbackRate = 1.0;
    } else if (state !== 'speaking' && prev === 'speaking') {
      _loadVideoSrc(_currentSources.idle);
      if (videoEl) videoEl.playbackRate = 0.85;
    }
  }

  function applyViseme(weight) {
    const target = Math.max(0, Math.min(1, weight || 0));
    _speaking += (target - _speaking) * 0.25;
  }

  function _startLoop() {
    if (_animId) return;
    function loop(ts) {
      _animId = requestAnimationFrame(loop);
      _blinkT += ts - _lastTs;
      _lastTs = ts;
      _drawFrame();
    }
    _animId = requestAnimationFrame((ts) => {
      _lastTs = ts;
      loop(ts);
    });
  }

  function _drawFrame() {
    if (!ctx || !canvasEl || canvasEl.width === 0) return;
    const w = canvasEl.width;
    const h = canvasEl.height;
    ctx.clearRect(0, 0, w, h);

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

    const intensity = _speaking;
    const activeLm = _mouthLm || _fallbackMouthLm(w, h);

    if (intensity > 0.02) {
      _applyJawMorph(activeLm.cx, activeLm.cy, activeLm.halfW, w, h, intensity);
    }

    if (_state === 'thinking') {
      const pulse = 0.5 + 0.5 * Math.sin(_blinkT / 400);
      ctx.save();
      ctx.strokeStyle = `rgba(56,189,248,${(0.65 * pulse).toFixed(3)})`;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.ellipse(activeLm.cx, activeLm.cy, 30 + pulse * 9, 13 + pulse * 5, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (_state === 'listening') {
      const pulse = 0.6 + 0.4 * Math.sin(_blinkT / 300);
      ctx.save();
      ctx.fillStyle = `rgba(52,211,153,${pulse.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(w * 0.88, h * 0.06, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    if (_state === 'speaking' && intensity > 0.01) {
      const BAR_COUNT = 12;
      const BAR_W = Math.max(3, w / (BAR_COUNT * 4));
      const BAR_GAP = BAR_W * 0.6;
      const totalW = BAR_COUNT * (BAR_W + BAR_GAP) - BAR_GAP;
      const startX = (w - totalW) / 2;
      const BASE_Y = h - 10;
      const MAX_H = h * 0.1;
      ctx.save();
      for (let i = 0; i < BAR_COUNT; i++) {
        const phase = _blinkT / 180 + (i / BAR_COUNT) * Math.PI * 2;
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

    _speaking *= 0.92;
  }

  function _applyJawMorph(cx, cy, halfW, w, h, intensity) {
    const jawDrop = Math.round(Math.min(intensity * h * 0.048, 32));
    if (jawDrop < 2) return;

    const regionW = Math.round(halfW * 2.6 + 24);
    const regionH = Math.round(h * 0.15);
    const mx = Math.max(0, Math.round(cx - regionW / 2));
    const my = Math.round(cy + 1);

    const safeW = Math.min(regionW, w - mx);
    const safeH = Math.min(regionH, h - my - jawDrop - 1);
    if (safeW < 4 || safeH < 4 || my < 0 || mx < 0) return;

    const pixels = ctx.getImageData(mx, my, safeW, safeH);

    const cavHalfH = jawDrop * 0.72;
    const cavHalfW = halfW * 0.88;
    const grad = ctx.createRadialGradient(
      cx,
      my + jawDrop * 0.32,
      0,
      cx,
      my + jawDrop * 0.55,
      Math.max(cavHalfW, 1),
    );
    grad.addColorStop(0, 'rgba(4,1,1,0.97)');
    grad.addColorStop(0.5, 'rgba(14,5,3,0.92)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');

    ctx.save();
    ctx.beginPath();
    ctx.ellipse(cx, my + cavHalfH * 0.55, cavHalfW, cavHalfH, 0, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    if (intensity > 0.28) {
      const ta = Math.min(1, (intensity - 0.28) / 0.55);
      ctx.beginPath();
      ctx.ellipse(cx, my + cavHalfH * 0.2, cavHalfW * 0.7, cavHalfH * 0.38, 0, Math.PI, 0);
      ctx.fillStyle = `rgba(248,244,240,${(ta * 0.88).toFixed(2)})`;
      ctx.fill();
    }
    ctx.restore();

    ctx.putImageData(pixels, mx, my + jawDrop);
  }

  return { init, setAvatar, setRenderMode, applyViseme, setState };
})();
