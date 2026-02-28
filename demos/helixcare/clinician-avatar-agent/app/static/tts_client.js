/**
 * TTSClient v7 — streaming audio via OpenAI TTS only. No silent browser fallbacks.
 *
 * Primary path  : streamSpeak()  — WebSocket → raw PCM → Web Audio API.
 *                 First audio arrives within ~300 ms of the server receiving text.
 * Error path    : if the server sends {"type":"tts_error"}, callbacks.onError(message)
 *                 is called and the caller surfaces a visible error in the UI.
 * Legacy path   : playAudioB64() — base64 WAV over HTTP (kept for live-stream mode).
 * Optional path : speakTextFallback() — browser SpeechSynthesis; kept as explicit
 *                 opt-in for callers that want it (e.g. human-patient text-to-speech
 *                 when OPENAI_API_KEY is unavailable).
 *
 * Real-time lipsync: when PCM is playing, an AnalyserNode measures amplitude every
 * 40 ms and calls AvatarRenderer.applyViseme(rms) so mouth movement tracks actual audio.
 *
 * Barge-in: call TTSClient.cancel() at any time to stop all audio immediately.
 */
window.TTSClient = (() => {
  // ── Audio context (lazily created, requires user gesture first) ───────────
  const SAMPLE_RATE = 24000;   // OpenAI PCM output rate
  const MIN_CHUNK_SAMPLES = 2400; // 100 ms — minimum chunk before scheduling

  let _audioCtx     = null;
  let _audioUnlocked = false;

  // Streaming state
  let _ws           = null;
  let _pcmBuf       = new Uint8Array(0);
  let _nextStartAt  = 0;          // Web Audio clock for gapless scheduling
  let _activeSrcs   = [];         // AudioBufferSourceNode[]

  // Amplitude lipsync
  let _analyser     = null;
  let _analyserBuf  = null;
  let _ampTimer     = null;       // setInterval handle for amplitude polling

  // ── Audio context helpers ─────────────────────────────────────────────────

  function _ctx() {
    if (!_audioCtx) {
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: SAMPLE_RATE,
      });
    }
    if (_audioCtx.state === 'suspended') {
      _audioCtx.resume().catch(() => {});
    }
    return _audioCtx;
  }

  // ── AnalyserNode — real-time amplitude → lipsync ──────────────────────────

  function _getAnalyser() {
    if (!_analyser) {
      const ctx  = _ctx();
      _analyser  = ctx.createAnalyser();
      _analyser.fftSize = 256;
      _analyser.smoothingTimeConstant = 0.6;
      _analyserBuf = new Uint8Array(_analyser.frequencyBinCount);
      _analyser.connect(ctx.destination);
    }
    return _analyser;
  }

  function _startAmpPoller() {
    if (_ampTimer) return;
    _ampTimer = setInterval(() => {
      if (!_analyser || !_analyserBuf || !window.AvatarRenderer) return;
      _analyser.getByteTimeDomainData(_analyserBuf);
      let sum = 0;
      for (let i = 0; i < _analyserBuf.length; i++) {
        const v = (_analyserBuf[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / _analyserBuf.length);
      // Scale RMS: ~0.02 RMS at normal speech → map to ~0.8 viseme weight
      window.AvatarRenderer.applyViseme(Math.min(1, rms * 10));
    }, 40);
  }

  function _stopAmpPoller() {
    if (_ampTimer) { clearInterval(_ampTimer); _ampTimer = null; }
  }

  // ── PCM conversion ────────────────────────────────────────────────────────

  /** Convert a raw 16-bit little-endian PCM Uint8Array to Float32Array. */
  function _pcm16ToFloat32(u8) {
    const samples = u8.length >> 1;
    const f32     = new Float32Array(samples);
    const view    = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    for (let i = 0; i < samples; i++) {
      f32[i] = view.getInt16(i * 2, true) / 32768;
    }
    return f32;
  }

  // ── Gapless Web Audio scheduling ──────────────────────────────────────────

  function _scheduleFloat32(f32) {
    const ctx = _ctx();
    if (ctx.state === 'suspended') {
      // Trigger resume but DO NOT drop the chunk. AudioContext.currentTime does
      // not advance during suspension, so queued sources play in order once the
      // context resumes. Dropping here causes missing words at the start of speech.
      ctx.resume().catch(() => {});
    }
    const buf = ctx.createBuffer(1, f32.length, SAMPLE_RATE);
    buf.copyToChannel(f32, 0);

    const src = ctx.createBufferSource();
    src.buffer = buf;
    // Route through analyser for real-time amplitude measurement
    src.connect(_getAnalyser());

    const now     = ctx.currentTime;
    const startAt = Math.max(now, _nextStartAt);
    src.start(startAt);
    _nextStartAt = startAt + buf.duration;

    _activeSrcs.push(src);
    src.onended = () => {
      _activeSrcs = _activeSrcs.filter((s) => s !== src);
    };
  }

  /** Drain _pcmBuf in MIN_CHUNK_SAMPLES-sized chunks; flush remainder if force=true. */
  function _flushPcm(force = false) {
    const minBytes = MIN_CHUNK_SAMPLES * 2;
    while (_pcmBuf.length >= minBytes || (force && _pcmBuf.length >= 2)) {
      const take = force ? _pcmBuf.length & ~1 : Math.floor(_pcmBuf.length / minBytes) * minBytes;
      if (take < 2) break;
      _scheduleFloat32(_pcm16ToFloat32(_pcmBuf.subarray(0, take)));
      _pcmBuf = _pcmBuf.subarray(take);
    }
  }

  function _appendBytes(bytes) {
    const merged = new Uint8Array(_pcmBuf.length + bytes.length);
    merged.set(_pcmBuf);
    merged.set(bytes, _pcmBuf.length);
    _pcmBuf = merged;
    _flushPcm(false);
  }

  // ── Stop all active audio immediately ────────────────────────────────────

  function _stopAll() {
    _stopAmpPoller();
    const now = _audioCtx ? _audioCtx.currentTime : 0;
    _activeSrcs.forEach((s) => { try { s.stop(now); } catch (_) {} });
    _activeSrcs  = [];
    _nextStartAt = 0;
    _pcmBuf      = new Uint8Array(0);
  }

  // ── Public: barge-in ─────────────────────────────────────────────────────

  function cancel() {
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      try { _ws.send(JSON.stringify({ type: 'cancel' })); } catch (_) {}
      _ws.close();
    }
    _ws = null;
    _stopAll();
    if (window.speechSynthesis) window.speechSynthesis.cancel();
  }

  // ── Public: streaming speak ───────────────────────────────────────────────

  /**
   * Stream TTS from the backend WebSocket endpoint.
   *
   * @param {string}   text     - Text to speak.
   * @param {string}   voice    - OpenAI voice name (e.g. 'nova', 'shimmer').
   * @param {string}   token    - JWT bearer token.
   * @param {object}   callbacks
   *   onVisemes(visemes)  — called immediately with the viseme timeline.
   *   onSpeechStart()     — called when first real PCM audio starts playing.
   *   onSpeechEnd()       — called after all audio has finished.
   *   onError(message)    — called when server reports a TTS error or WebSocket fails.
   */
  function streamSpeak(text, voice, token, callbacks = {}) {
    cancel();   // barge-in: stop any current stream

    const { onVisemes, onSpeechStart, onSpeechEnd, onError } = callbacks;
    let speechStarted = false;

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl    = `${protocol}://${window.location.host}/api/tts/stream?token=${encodeURIComponent(token)}`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (_) {
      if (onError) onError('WebSocket TTS connection could not be opened');
      return;
    }

    _ws = ws;
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'speak', text, voice }));
    };

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        let msg;
        try { msg = JSON.parse(event.data); } catch (_) { return; }

        if (msg.type === 'visemes' && onVisemes) {
          onVisemes(msg.visemes || []);

        } else if (msg.type === 'meta') {
          if (!speechStarted) {
            speechStarted = true;
            if (onSpeechStart) onSpeechStart();
          }

        } else if (msg.type === 'tts_error') {
          // Server-side TTS failure — surface a visible error; do not fall back silently.
          _stopAll();
          if (onError) onError(msg.message || 'TTS error');
          if (onSpeechEnd) onSpeechEnd();
          ws.close();
          _ws = null;
          return;

        } else if (msg.type === 'end') {
          _flushPcm(true);   // drain any remaining bytes
          if (onSpeechEnd) {
            const ctx   = _ctx();
            const delay = Math.max(0, _nextStartAt - ctx.currentTime) * 1000;
            setTimeout(() => { _stopAmpPoller(); if (onSpeechEnd) onSpeechEnd(); }, delay + 80);
          }
          ws.close();
          _ws = null;
        }
      } else {
        // Binary frame — raw PCM chunk
        if (!speechStarted) {
          speechStarted = true;
          if (onSpeechStart) onSpeechStart();
        }
        // Always (re)start the poller on first binary chunk — speechStarted
        // may have been set early by the meta handler, so we can't rely on
        // !speechStarted to gate this.  _startAmpPoller() is idempotent.
        _startAmpPoller();
        _appendBytes(new Uint8Array(event.data));
      }
    };

    ws.onerror = () => {
      _ws = null;
      _stopAmpPoller();
      if (onError) onError('WebSocket TTS connection failed');
      if (onSpeechEnd) onSpeechEnd();
    };

    ws.onclose = () => {
      if (_ws === ws) _ws = null;
    };
  }

  // ── Public: legacy batch TTS (HTTP) — kept for live-stream mode ──────────

  async function synthesize(text, voice, authToken) {
    const resp = await fetch('/api/tts', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text, voice }),
    });
    if (!resp.ok) throw new Error(`TTS failed: ${resp.status}`);
    return resp.json();
  }

  // ── Public: audio unlock (must be called from a user-gesture handler) ─────

  async function enableAudio() {
    try {
      const ctx = _ctx();
      if (ctx.state === 'suspended') await ctx.resume();
    } catch (_) {}
    _audioUnlocked = true;
    return true;
  }

  // ── Public: Web Speech API last-resort fallback ───────────────────────────

  function speakTextFallback(text, voiceHint = '') {
    const clean = String(text || '').trim();
    if (!clean || !window.speechSynthesis) return null;
    const utt = new SpeechSynthesisUtterance(clean);
    utt.rate   = 0.95;
    utt.pitch  = 1.0;
    utt.volume = 1.0;
    const voices  = window.speechSynthesis.getVoices();
    const hint    = String(voiceHint || '').toLowerCase();
    const matched = hint && voices.find((v) => v.name.toLowerCase().includes(hint));
    const english = voices.find((v) => String(v.lang || '').toLowerCase().startsWith('en'));
    utt.voice = matched || english || voices[0] || null;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utt);
    return utt;
  }

  // ── Internal: browser TTS with real-time word-boundary lip sync ───────────

  function _speakBrowserTTS(text, voiceHint = '') {
    const clean = String(text || '').trim();
    if (!clean || !window.speechSynthesis) return null;

    window.speechSynthesis.cancel();

    const utt = new SpeechSynthesisUtterance(clean);
    utt.rate   = 0.92;
    utt.pitch  = 1.0;
    utt.volume = 1.0;

    function _pickVoice() {
      const voices = window.speechSynthesis.getVoices();
      const hint   = String(voiceHint || '').toLowerCase();
      const named   = hint && voices.find((v) => v.name.toLowerCase().includes(hint));
      const premium = voices.find((v) => {
        const n = v.name.toLowerCase();
        const l = String(v.lang || '').toLowerCase();
        return l.startsWith('en') && (n.includes('premium') || n.includes('enhanced') || n.includes('natural'));
      });
      const english = voices.find((v) => String(v.lang || '').toLowerCase().startsWith('en'));
      return named || premium || english || voices[0] || null;
    }

    utt.voice = _pickVoice();
    if (!utt.voice) {
      window.speechSynthesis.addEventListener('voiceschanged', () => {
        utt.voice = _pickVoice();
      }, { once: true });
    }

    // Drive the lip-sync overlay on every spoken word (boundary events)
    utt.onboundary = (evt) => {
      if (evt.name === 'word' && window.AvatarRenderer) {
        window.AvatarRenderer.applyViseme(0.85);
      }
    };

    window.speechSynthesis.speak(utt);
    return utt;
  }

  // ── Public: base64 audio playback (live-stream HTTP path) ─────────────────

  async function playAudioB64(audioB64, mimeType = 'audio/wav', fallbackText = '', voiceHint = '') {
    if (!audioB64) return speakTextFallback(fallbackText, voiceHint);
    const audio = new Audio(`data:${mimeType};base64,${audioB64}`);
    audio.volume = 1.0;
    try {
      await audio.play();
    } catch (_) {
      return speakTextFallback(fallbackText, voiceHint);
    }
    return audio;
  }

  return { synthesize, enableAudio, playAudioB64, speakTextFallback, streamSpeak, cancel };
})();
