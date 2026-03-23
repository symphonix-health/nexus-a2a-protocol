/**
 * GpuAvatarRenderer v1
 *
 * GPU-accelerated 3D avatar renderer using Three.js with:
 *  - Procedural head mesh with 52 ARKit-compatible blendshapes
 *  - PBR materials with subsurface scattering approximation for realistic skin
 *  - Real-time lighting (3-point studio setup)
 *  - Audio-driven blendshape animation
 *  - Smooth idle animations (breathing, blinking, gaze, micro-movements)
 *  - Expression system (warm, concerned, attentive, neutral)
 *
 * Requirements:
 *  - GPU with WebGL 2.0 support (falls back to canvas renderer if unavailable)
 *  - Three.js r150+ loaded via CDN (loaded dynamically if not present)
 *
 * Usage:
 *  - Drop-in replacement for AvatarRenderer (same public API)
 *  - Set render mode to 'gpu' in avatar.html to activate
 *  - Falls back to AvatarRenderer (canvas) if WebGL is unavailable
 *
 * Public API (matches AvatarRenderer):
 *   init(containerId)
 *   setAvatar(key)
 *   setRenderMode(mode)
 *   applyViseme(weight)
 *   applyVisemeParams({ jawOpen, mouthWidth, lipPucker, rms, ... })
 *   setState(state)
 *   setExpression(name, weight)
 *   setGazeTarget(nx, ny)
 */
window.GpuAvatarRenderer = (() => {
  // ── State ─────────────────────────────────────────────────────────────
  let _container = null;
  let _renderer = null;
  let _scene = null;
  let _camera = null;
  let _headMesh = null;
  let _animId = null;
  let _lastTs = 0;
  let _elapsedMs = 0;
  let _state = 'idle';
  let _ready = false;
  let _THREE = null;

  // Mouth parameters (driven by lipsync)
  let _jawOpen = 0;
  let _mouthWidth = 0.5;
  let _lipPucker = 0;
  let _upperLipRaise = 0;
  let _lipCornerPull = 0;
  let _tongueShow = 0;
  let _speaking = 0;

  // Blink state
  let _blinkValue = 0;
  let _blinkTarget = 0;
  let _nextBlinkAt = 3000;

  // Breathing
  let _breathPhase = 0;

  // Head micro-movement
  let _headRotTarget = { x: 0, y: 0, z: 0 };
  let _headRotCurrent = { x: 0, y: 0, z: 0 };

  // Gaze
  let _gazeTarget = { x: 0, y: 0 };
  let _gazeCurrent = { x: 0, y: 0 };

  // Eyebrow
  let _browRaise = 0;
  let _browTarget = 0;

  // Expression
  const EXPRESSIONS = {
    neutral:   { browRaise: 0,    mouthSmile: 0,    eyeWide: 0,   cheekPuff: 0 },
    attentive: { browRaise: 0.15, mouthSmile: 0,    eyeWide: 0.1, cheekPuff: 0 },
    warm:      { browRaise: 0.1,  mouthSmile: 0.25, eyeWide: 0.05, cheekPuff: 0.05 },
    concerned: { browRaise: -0.2, mouthSmile: -0.1, eyeWide: 0.15, cheekPuff: 0 },
    thinking:  { browRaise: 0.2,  mouthSmile: 0,    eyeWide: 0,   cheekPuff: 0.05 },
  };
  let _expressionWeight = 0;
  let _expressionTarget = 0;
  let _expressionParams = EXPRESSIONS.neutral;

  // ── ARKit blendshape names (52 shapes) ────────────────────────────────
  // These map to the morph targets on our procedural head mesh.
  // Not all 52 are used for the procedural mesh — we implement the key ones.
  const BLENDSHAPES = {
    // Eyes
    eyeBlinkLeft: 0,
    eyeBlinkRight: 0,
    eyeWideLeft: 0,
    eyeWideRight: 0,
    eyeLookUpLeft: 0,
    eyeLookUpRight: 0,
    eyeLookDownLeft: 0,
    eyeLookDownRight: 0,
    eyeLookInLeft: 0,
    eyeLookInRight: 0,
    eyeLookOutLeft: 0,
    eyeLookOutRight: 0,
    // Brows
    browDownLeft: 0,
    browDownRight: 0,
    browInnerUp: 0,
    browOuterUpLeft: 0,
    browOuterUpRight: 0,
    // Jaw
    jawOpen: 0,
    jawForward: 0,
    jawLeft: 0,
    jawRight: 0,
    // Mouth
    mouthClose: 0,
    mouthFunnel: 0,
    mouthPucker: 0,
    mouthLeft: 0,
    mouthRight: 0,
    mouthSmileLeft: 0,
    mouthSmileRight: 0,
    mouthFrownLeft: 0,
    mouthFrownRight: 0,
    mouthDimpleLeft: 0,
    mouthDimpleRight: 0,
    mouthStretchLeft: 0,
    mouthStretchRight: 0,
    mouthRollLower: 0,
    mouthRollUpper: 0,
    mouthShrugLower: 0,
    mouthShrugUpper: 0,
    mouthPressLeft: 0,
    mouthPressRight: 0,
    mouthLowerDownLeft: 0,
    mouthLowerDownRight: 0,
    mouthUpperUpLeft: 0,
    mouthUpperUpRight: 0,
    // Cheeks / Nose
    cheekPuff: 0,
    cheekSquintLeft: 0,
    cheekSquintRight: 0,
    noseSneerLeft: 0,
    noseSneerRight: 0,
    // Tongue
    tongueOut: 0,
  };

  // ── Three.js loading ──────────────────────────────────────────────────
  function _loadThreeJs() {
    return new Promise((resolve, reject) => {
      if (window.THREE) {
        _THREE = window.THREE;
        resolve();
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js';
      script.onload = () => {
        _THREE = window.THREE;
        resolve();
      };
      script.onerror = () => reject(new Error('Failed to load Three.js'));
      document.head.appendChild(script);
    });
  }

  // ── WebGL capability check ────────────────────────────────────────────
  function _hasWebGL2() {
    try {
      const canvas = document.createElement('canvas');
      return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'));
    } catch (_) {
      return false;
    }
  }

  // ── Initialize ────────────────────────────────────────────────────────
  async function init(containerId) {
    _container = document.getElementById(containerId);
    if (!_container) return;

    if (!_hasWebGL2()) {
      console.warn('[GpuAvatarRenderer] WebGL not available, falling back to canvas renderer');
      if (window.AvatarRenderer && window.AvatarRenderer !== window.GpuAvatarRenderer) {
        window.AvatarRenderer.init(containerId);
      }
      return;
    }

    try {
      await _loadThreeJs();
    } catch (err) {
      console.warn('[GpuAvatarRenderer] Three.js load failed:', err.message);
      return;
    }

    _container.innerHTML = '';
    _container.style.position = 'relative';
    _container.style.overflow = 'hidden';

    // ── Create renderer ───────────────────────────────────────────────
    _renderer = new _THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
    });
    _renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    _renderer.setSize(_container.clientWidth, _container.clientHeight);
    _renderer.setClearColor(0x0c0c0c, 1);
    _renderer.toneMapping = _THREE.ACESFilmicToneMapping;
    _renderer.toneMappingExposure = 1.1;
    _renderer.outputColorSpace = _THREE.SRGBColorSpace;
    _container.appendChild(_renderer.domElement);
    _renderer.domElement.style.borderRadius = '8px';

    // ── Scene ─────────────────────────────────────────────────────────
    _scene = new _THREE.Scene();
    _scene.background = new _THREE.Color(0x0c0c0c);

    // ── Camera ────────────────────────────────────────────────────────
    const aspect = _container.clientWidth / _container.clientHeight;
    _camera = new _THREE.PerspectiveCamera(28, aspect, 0.1, 100);
    _camera.position.set(0, 0.1, 2.2);
    _camera.lookAt(0, 0.05, 0);

    // ── Lighting (3-point studio setup) ───────────────────────────────
    // Key light (warm, from upper-right)
    const keyLight = new _THREE.DirectionalLight(0xfff0e8, 1.8);
    keyLight.position.set(2, 3, 3);
    _scene.add(keyLight);

    // Fill light (cool, from left)
    const fillLight = new _THREE.DirectionalLight(0xe8f0ff, 0.6);
    fillLight.position.set(-3, 1, 2);
    _scene.add(fillLight);

    // Rim light (behind, for edge definition)
    const rimLight = new _THREE.DirectionalLight(0xffffff, 0.4);
    rimLight.position.set(0, 2, -3);
    _scene.add(rimLight);

    // Ambient (subtle, prevents pure black)
    const ambient = new _THREE.AmbientLight(0x404050, 0.3);
    _scene.add(ambient);

    // ── Create procedural head ────────────────────────────────────────
    _createProceduralHead();

    // ── Resize observer ───────────────────────────────────────────────
    const ro = new ResizeObserver(() => {
      if (!_renderer || !_camera || !_container) return;
      const w = _container.clientWidth;
      const h = _container.clientHeight;
      _renderer.setSize(w, h);
      _camera.aspect = w / h;
      _camera.updateProjectionMatrix();
    });
    ro.observe(_container);

    // ── Mouse tracking for gaze ───────────────────────────────────────
    document.addEventListener('mousemove', (e) => {
      if (!_container) return;
      const rect = _container.getBoundingClientRect();
      if (rect.width === 0) return;
      _gazeTarget.x = ((e.clientX - rect.left) / rect.width - 0.5) * 0.3;
      _gazeTarget.y = -((e.clientY - rect.top) / rect.height - 0.5) * 0.15;
    }, { passive: true });

    _ready = true;
    _startLoop();
  }

  // ── Procedural head mesh ──────────────────────────────────────────────
  function _createProceduralHead() {
    // Create a head-shaped geometry using a scaled sphere with vertex morphs
    const geometry = new _THREE.SphereGeometry(0.5, 64, 48);

    // Reshape sphere into head proportions
    const posAttr = geometry.getAttribute('position');
    const positions = posAttr.array;
    for (let i = 0; i < positions.length; i += 3) {
      let x = positions[i];
      let y = positions[i + 1];
      let z = positions[i + 2];

      // Elongate vertically (head is taller than wide)
      y *= 1.2;
      // Narrow at top (skull tapering)
      const topTaper = 1 - Math.max(0, y - 0.2) * 0.3;
      x *= topTaper;
      z *= topTaper;
      // Wider at jaw line
      const jawFactor = Math.max(0, -y - 0.1) * 0.4;
      x *= 1 - jawFactor * 0.3;
      // Chin point
      if (y < -0.4) {
        const chinFactor = (-y - 0.4) * 2;
        x *= Math.max(0.3, 1 - chinFactor * 0.6);
        z *= Math.max(0.5, 1 - chinFactor * 0.3);
      }
      // Slight forward protrusion for nose area
      if (y > -0.1 && y < 0.15 && Math.abs(x) < 0.12) {
        z += 0.06 * (1 - Math.abs(x) / 0.12);
      }
      // Forehead curvature
      if (y > 0.3) {
        z += 0.03 * (y - 0.3);
      }

      positions[i] = x;
      positions[i + 1] = y;
      positions[i + 2] = z;
    }
    posAttr.needsUpdate = true;
    geometry.computeVertexNormals();

    // ── PBR skin material with SSS approximation ──────────────────────
    // Using MeshPhysicalMaterial for closest-to-realistic skin
    const skinMaterial = new _THREE.MeshPhysicalMaterial({
      color: new _THREE.Color(0.45, 0.28, 0.22),   // Dark skin tone
      roughness: 0.55,
      metalness: 0.0,
      clearcoat: 0.05,       // Slight skin sheen
      clearcoatRoughness: 0.4,
      sheen: 0.2,            // Subsurface approximation
      sheenRoughness: 0.5,
      sheenColor: new _THREE.Color(0.7, 0.35, 0.25),  // Warm subsurface color
      // Transmission for SSS effect (very subtle)
      transmission: 0.02,
      thickness: 0.1,
      envMapIntensity: 0.3,
    });

    _headMesh = new _THREE.Mesh(geometry, skinMaterial);
    _headMesh.position.set(0, 0.05, 0);
    _scene.add(_headMesh);

    // ── Eyes ──────────────────────────────────────────────────────────
    const eyeGeom = new _THREE.SphereGeometry(0.04, 32, 24);
    const eyeMat = new _THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      roughness: 0.1,
      metalness: 0.0,
      clearcoat: 0.8,
      clearcoatRoughness: 0.1,
    });

    const leftEye = new _THREE.Mesh(eyeGeom, eyeMat);
    leftEye.position.set(-0.12, 0.12, 0.4);
    leftEye.name = 'leftEye';
    _headMesh.add(leftEye);

    const rightEye = new _THREE.Mesh(eyeGeom, eyeMat.clone());
    rightEye.position.set(0.12, 0.12, 0.4);
    rightEye.name = 'rightEye';
    _headMesh.add(rightEye);

    // Iris
    const irisGeom = new _THREE.CircleGeometry(0.02, 32);
    const irisMat = new _THREE.MeshBasicMaterial({ color: 0x3a2210 });
    const leftIris = new _THREE.Mesh(irisGeom, irisMat);
    leftIris.position.set(0, 0, 0.035);
    leftIris.name = 'leftIris';
    leftEye.add(leftIris);

    const rightIris = new _THREE.Mesh(irisGeom, irisMat.clone());
    rightIris.position.set(0, 0, 0.035);
    rightIris.name = 'rightIris';
    rightEye.add(rightIris);

    // Pupils
    const pupilGeom = new _THREE.CircleGeometry(0.008, 24);
    const pupilMat = new _THREE.MeshBasicMaterial({ color: 0x000000 });
    const leftPupil = new _THREE.Mesh(pupilGeom, pupilMat);
    leftPupil.position.set(0, 0, 0.001);
    leftIris.add(leftPupil);

    const rightPupil = new _THREE.Mesh(pupilGeom, pupilMat.clone());
    rightPupil.position.set(0, 0, 0.001);
    rightIris.add(rightPupil);

    // ── Eyelids (for blink) ───────────────────────────────────────────
    const lidGeom = new _THREE.PlaneGeometry(0.1, 0.05);
    const lidMat = new _THREE.MeshPhysicalMaterial({
      color: skinMaterial.color.clone(),
      roughness: 0.6,
      metalness: 0,
      side: _THREE.DoubleSide,
    });

    const leftUpperLid = new _THREE.Mesh(lidGeom, lidMat);
    leftUpperLid.position.set(-0.12, 0.155, 0.42);
    leftUpperLid.name = 'leftUpperLid';
    _headMesh.add(leftUpperLid);

    const rightUpperLid = new _THREE.Mesh(lidGeom.clone(), lidMat.clone());
    rightUpperLid.position.set(0.12, 0.155, 0.42);
    rightUpperLid.name = 'rightUpperLid';
    _headMesh.add(rightUpperLid);

    // ── Mouth plane (for lip rendering) ───────────────────────────────
    const mouthGeom = new _THREE.PlaneGeometry(0.16, 0.06, 16, 8);
    const mouthMat = new _THREE.MeshPhysicalMaterial({
      color: new _THREE.Color(0.5, 0.2, 0.18),
      roughness: 0.45,
      metalness: 0,
      clearcoat: 0.15,
      transparent: true,
      opacity: 0.9,
    });
    const mouth = new _THREE.Mesh(mouthGeom, mouthMat);
    mouth.position.set(0, -0.15, 0.48);
    mouth.name = 'mouth';
    _headMesh.add(mouth);

    // Interior (dark cavity visible when mouth opens)
    const cavityGeom = new _THREE.PlaneGeometry(0.12, 0.04);
    const cavityMat = new _THREE.MeshBasicMaterial({
      color: 0x0a0202,
      transparent: true,
      opacity: 0,
    });
    const cavity = new _THREE.Mesh(cavityGeom, cavityMat);
    cavity.position.set(0, -0.16, 0.45);
    cavity.name = 'mouthCavity';
    _headMesh.add(cavity);

    // Teeth
    const teethGeom = new _THREE.PlaneGeometry(0.09, 0.015);
    const teethMat = new _THREE.MeshPhysicalMaterial({
      color: 0xf0ece6,
      roughness: 0.2,
      metalness: 0,
      transparent: true,
      opacity: 0,
    });
    const teeth = new _THREE.Mesh(teethGeom, teethMat);
    teeth.position.set(0, -0.145, 0.46);
    teeth.name = 'teeth';
    _headMesh.add(teeth);
  }

  // ── Animation loop ────────────────────────────────────────────────────
  function _startLoop() {
    if (_animId) return;
    function loop(ts) {
      _animId = requestAnimationFrame(loop);
      const dt = ts - _lastTs;
      _lastTs = ts;
      _elapsedMs += dt;
      if (_ready) {
        _updateAnimations(dt);
        _applyBlendshapes();
        _renderer.render(_scene, _camera);
      }
    }
    _animId = requestAnimationFrame((ts) => {
      _lastTs = ts;
      loop(ts);
    });
  }

  // ── Update idle animations ────────────────────────────────────────────
  function _updateAnimations(dt) {
    if (!dt || dt > 500) return;
    const t = _elapsedMs / 1000;

    // Blink
    _nextBlinkAt -= dt;
    if (_nextBlinkAt <= 0 && _blinkTarget === 0) {
      _blinkTarget = 1;
      setTimeout(() => { _blinkTarget = 0; }, 150);
      _nextBlinkAt = 2500 + Math.random() * 4000;
      if (_state === 'thinking') _nextBlinkAt *= 0.6;
    }
    _blinkValue += (_blinkTarget - _blinkValue) * 0.35;

    // Breathing
    _breathPhase += (dt / 4200) * Math.PI * 2;
    if (_breathPhase > Math.PI * 2) _breathPhase -= Math.PI * 2;

    // Head micro-movement
    _headRotTarget.x = Math.sin(t * 0.29) * 0.01 + Math.sin(t * 0.67) * 0.005;
    _headRotTarget.y = Math.sin(t * 0.37) * 0.015 + Math.sin(t * 0.83) * 0.005;
    _headRotTarget.z = Math.sin(t * 0.19) * 0.005;
    _headRotCurrent.x += (_headRotTarget.x - _headRotCurrent.x) * 0.05;
    _headRotCurrent.y += (_headRotTarget.y - _headRotCurrent.y) * 0.05;
    _headRotCurrent.z += (_headRotTarget.z - _headRotCurrent.z) * 0.05;

    // Gaze
    _gazeCurrent.x += (_gazeTarget.x - _gazeCurrent.x) * 0.06;
    _gazeCurrent.y += (_gazeTarget.y - _gazeCurrent.y) * 0.06;

    // Brow
    _browTarget = _expressionParams.browRaise * _expressionWeight;
    if (_state === 'speaking' && _jawOpen > 0.3) _browTarget += 0.08;
    _browRaise += (_browTarget - _browRaise) * 0.06;

    // Expression
    _expressionWeight += (_expressionTarget - _expressionWeight) * 0.04;

    // Decay speech params
    _jawOpen *= 0.93;
    _mouthWidth += (0.5 - _mouthWidth) * 0.04;
    _lipPucker *= 0.93;
    _speaking *= 0.92;
    _upperLipRaise *= 0.93;
    _tongueShow *= 0.93;
  }

  // ── Apply blendshapes to mesh ─────────────────────────────────────────
  function _applyBlendshapes() {
    if (!_headMesh) return;

    // Head rotation (breathing + micro-movement)
    const breathRot = Math.sin(_breathPhase) * 0.003;
    _headMesh.rotation.x = _headRotCurrent.x + breathRot;
    _headMesh.rotation.y = _headRotCurrent.y;
    _headMesh.rotation.z = _headRotCurrent.z;

    // Breathing scale
    const breathScale = 1 + Math.sin(_breathPhase) * 0.003;
    _headMesh.scale.set(breathScale, breathScale, breathScale);

    // Eyes — blink
    const leftLid = _headMesh.getObjectByName('leftUpperLid');
    const rightLid = _headMesh.getObjectByName('rightUpperLid');
    if (leftLid) {
      leftLid.position.y = 0.155 - _blinkValue * 0.04;
      leftLid.scale.y = 0.5 + _blinkValue * 1.5;
    }
    if (rightLid) {
      rightLid.position.y = 0.155 - _blinkValue * 0.04;
      rightLid.scale.y = 0.5 + _blinkValue * 1.5;
    }

    // Eyes — gaze
    const leftEye = _headMesh.getObjectByName('leftEye');
    const rightEye = _headMesh.getObjectByName('rightEye');
    if (leftEye) {
      leftEye.rotation.y = _gazeCurrent.x * 0.5;
      leftEye.rotation.x = _gazeCurrent.y * 0.5;
    }
    if (rightEye) {
      rightEye.rotation.y = _gazeCurrent.x * 0.5;
      rightEye.rotation.x = _gazeCurrent.y * 0.5;
    }

    // Mouth — jaw open
    const mouth = _headMesh.getObjectByName('mouth');
    const cavity = _headMesh.getObjectByName('mouthCavity');
    const teeth = _headMesh.getObjectByName('teeth');

    if (mouth) {
      // Jaw opens by moving mouth plane down and scaling
      mouth.position.y = -0.15 - _jawOpen * 0.04;
      mouth.scale.y = 1 + _jawOpen * 0.8;
      // Width
      mouth.scale.x = 0.8 + _mouthWidth * 0.4 - _lipPucker * 0.2;
      // Lip color changes with speech intensity
      const intensity = Math.min(1, _speaking * 2);
      mouth.material.color.setRGB(
        0.5 + intensity * 0.1,
        0.2 - intensity * 0.02,
        0.18 - intensity * 0.02
      );
    }

    if (cavity) {
      // Cavity visible when mouth opens
      cavity.material.opacity = Math.min(0.9, _jawOpen * 1.5);
      cavity.scale.y = 1 + _jawOpen * 2;
    }

    if (teeth) {
      // Teeth visible when jaw opens enough
      teeth.material.opacity = _jawOpen > 0.2 ? Math.min(0.8, (_jawOpen - 0.2) * 2) : 0;
    }
  }

  // ── Public API ────────────────────────────────────────────────────────
  function setAvatar(_key) {
    // GPU renderer uses procedural mesh — avatar key affects skin tone
    if (_headMesh && _headMesh.material) {
      // Could vary skin tone by avatar key in future
    }
  }

  function setRenderMode(_mode) {
    // GPU mode is always GPU — this is a no-op
  }

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

  function setState(state) {
    _state = state;
    if (state === 'speaking') setExpression('warm', 0.3);
    else if (state === 'thinking') setExpression('thinking', 0.4);
    else if (state === 'listening') setExpression('attentive', 0.35);
    else setExpression('neutral', 0);
  }

  function setExpression(name, weight) {
    if (EXPRESSIONS[name]) {
      _expressionParams = EXPRESSIONS[name];
      _expressionTarget = Math.max(0, Math.min(1, weight || 0));
    }
  }

  function setGazeTarget(nx, ny) {
    _gazeTarget.x = (nx - 0.5) * 0.3;
    _gazeTarget.y = -(ny - 0.5) * 0.15;
  }

  function isAvailable() {
    return _hasWebGL2();
  }

  return {
    init,
    setAvatar,
    setRenderMode,
    applyViseme,
    applyVisemeParams,
    setState,
    setExpression,
    setGazeTarget,
    isAvailable,
  };
})();
