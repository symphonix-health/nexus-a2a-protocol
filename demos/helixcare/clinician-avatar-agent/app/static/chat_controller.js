/**
 * chat_controller.js — orchestrates the avatar session UI.
 *
 * Changes vs. previous version:
 *  • sendMessage() uses TTSClient.streamSpeak() for low-latency audio (< 900 ms).
 *  • Barge-in: any new send/Enter cancels the current avatar speech immediately.
 *  • Avatar state machine: idle → thinking → speaking → idle.
 *  • #avatar-state-bar updated on every transition.
 *  • Live-stream mode (/?live=1) unchanged — still drives through handleLiveEvent().
 */
(() => {
  const chatLog       = document.getElementById('chat-log');
  const chatInput     = document.getElementById('chat-input');
  const sendBtn       = document.getElementById('send-btn');
  const startBtn      = document.getElementById('start-btn');
  const avatarSelect  = document.getElementById('avatar-select');
  const voiceSelect   = document.getElementById('voice-select');
  const statusPill    = document.getElementById('status-pill');
  const frameworkEl   = document.getElementById('framework-state');
  const audioEnableBtn = document.getElementById('audio-enable-btn');
  const stateBar      = document.getElementById('avatar-state-bar');

  let authToken  = '';
  let sessionId  = '';
  const query    = new URLSearchParams(window.location.search);
  const liveMode = query.get('live') === '1';
  const readOnly = query.get('readonly') === '1' || liveMode;
  let liveSocket = null;
  let audioEnabled = false;

  // ── Helpers ──────────────────────────────────────────────────────────────

  function _setAvatarState(state, label = '') {
    window.AvatarRenderer.setState(state);
    if (stateBar) {
      stateBar.textContent    = label || state;
      stateBar.dataset.state  = state;
    }
  }

  function normalizeText(text) {
    return String(text || '').trim()
      .replace(/\s+\?/g, '?')
      .replace(/\s+!/g, '!')
      .replace(/\s+\./g, '.')
      .replace(/\n{3,}/g, '\n\n');
  }

  function addMsg(role, text) {
    const clean = normalizeText(text);
    if (!clean) return;
    const div       = document.createElement('div');
    div.className   = `msg ${role}`;
    div.textContent = clean;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  // ── JSON-RPC helper ──────────────────────────────────────────────────────

  async function rpc(method, params) {
    const payload = { jsonrpc: '2.0', id: String(Date.now()), method, params };
    const resp = await fetch('/rpc', {
      method: 'POST',
      headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`RPC ${method} failed: ${resp.status}`);
    const body = await resp.json();
    if (body.error) throw new Error(body.error.message || 'RPC error');
    return body.result;
  }

  // ── Speaking pipeline ────────────────────────────────────────────────────

  function _speakStreaming(text, onDone) {
    _setAvatarState('speaking', 'Speaking…');
    window.TTSClient.streamSpeak(text, voiceSelect.value, authToken, {
      onVisemes(visemes) {
        // Start pre-computed timeline as a warm-up while we wait for the first
        // PCM chunk.  onSpeechStart() will stop it once real audio arrives.
        window.LipSyncEngine.start(visemes);
      },
      onSynthetic() {
        // Browser TTS is active — stop the pre-computed timeline so only
        // word-boundary events (from _speakBrowserTTS) drive the mouth glow.
        window.LipSyncEngine.stop();
      },
      onSpeechStart() {
        // Real PCM is flowing — amplitude polling (via AnalyserNode) takes over
        // lipsync, so the pre-computed viseme timeline is no longer needed.
        window.LipSyncEngine.stop();
        _setAvatarState('speaking', 'Speaking…');
      },
      onSpeechEnd() {
        window.LipSyncEngine.stop();
        _setAvatarState('idle', '');
        if (statusPill) statusPill.textContent = sessionId ? `Session: ${sessionId}` : 'Session ready';
        if (onDone) onDone();
      },
      onFallback(t) {
        window.TTSClient.speakTextFallback(t, voiceSelect.value);
        window.LipSyncEngine.stop();
        _setAvatarState('idle', '');
        if (onDone) onDone();
      },
    });
  }

  // Handles speech from a live-stream event payload that already has audio_b64
  async function _playLiveSpeech(speech, fallbackText) {
    if (!speech || typeof speech !== 'object') return;
    const visemes = Array.isArray(speech.visemes) ? speech.visemes : [];
    if (visemes.length) window.LipSyncEngine.start(visemes);
    _setAvatarState('speaking', 'Speaking…');
    await window.TTSClient.playAudioB64(
      speech.audio_b64 || '',
      speech.mime_type || 'audio/wav',
      speech.text || fallbackText || '',
      speech.voice || voiceSelect.value,
    );
    window.LipSyncEngine.stop();
    _setAvatarState('idle', '');
  }

  // ── Token acquisition ────────────────────────────────────────────────────

  /**
   * Ensure authToken is populated.
   * 1. Try GET /dev/token (works when NEXUS_JWT_SECRET is the default dev value).
   * 2. Fall back to a manual prompt so production deployments still work.
   */
  async function _ensureToken() {
    if (authToken) return true;
    try {
      const resp = await fetch('/dev/token');
      if (resp.ok) {
        const data = await resp.json();
        authToken = data.token || '';
        if (authToken) return true;
      }
    } catch (_) {}
    authToken = prompt('Paste bearer token (JWT)') || '';
    return !!authToken;
  }

  // ── Session lifecycle ────────────────────────────────────────────────────

  async function startSession() {
    if (readOnly) return;
    // Unlock AudioContext while still within the synchronous click-handler stack.
    // Must happen before the first `await`; browsers deny AudioContext.resume()
    // in async callbacks, setTimeout, WebSocket handlers, etc.
    window.TTSClient.enableAudio().catch(() => {});

    if (!await _ensureToken()) return;

    window.AvatarRenderer.setAvatar(avatarSelect.value);
    _setAvatarState('thinking', 'Starting…');

    const result = await rpc('avatar/start_session', {
      patient_case: {
        patient_profile: {
          age: 57,
          gender: 'female',
          chief_complaint: 'Chest pain and diaphoresis',
          urgency: 'critical',
        },
      },
      persona: {
        name: 'Dr. Marcus',
        specialty: 'emergency medicine',
        role: 'physician',
        style: 'calm, empathetic, and precise',
      },
    });

    sessionId = result.session_id;
    if (statusPill) statusPill.textContent = `Session: ${sessionId}`;
    if (frameworkEl) frameworkEl.textContent = JSON.stringify(result.framework_progress, null, 2);

    const greeting = result.greeting || 'Session started.';
    addMsg('assistant', greeting);

    // Speak the greeting via streaming TTS
    _speakStreaming(greeting, null);
  }

  // ── Send message (barge-in aware) ────────────────────────────────────────

  async function sendMessage() {
    if (readOnly) return;
    // Same AudioContext unlock — must be before any `await`.
    window.TTSClient.enableAudio().catch(() => {});

    const text = chatInput.value.trim();
    if (!text || !sessionId) return;
    chatInput.value = '';

    // Barge-in: cancel any avatar speech in progress
    window.TTSClient.cancel();
    window.LipSyncEngine.stop();

    addMsg('user', text);
    _setAvatarState('thinking', 'Thinking…');
    if (statusPill) statusPill.textContent = 'Processing…';

    let result;
    try {
      result = await rpc('avatar/patient_message', { session_id: sessionId, message: text });
    } catch (err) {
      _setAvatarState('idle', '');
      if (statusPill) statusPill.textContent = `Session: ${sessionId}`;
      alert(err.message);
      return;
    }

    const response = result.clinician_response || '(no response)';
    addMsg('assistant', response);
    if (frameworkEl) frameworkEl.textContent = JSON.stringify(result.framework_progress || {}, null, 2);

    _speakStreaming(response, null);
  }

  // ── Live-stream event handling ───────────────────────────────────────────

  function handleLiveEvent(evt) {
    if (!evt || !evt.type) return;

    if (evt.type === 'avatar.session_started') {
      sessionId = evt.session_id || sessionId;
      if (statusPill) statusPill.textContent = sessionId ? `Live: ${sessionId}` : 'Live session';
      if (evt.greeting) addMsg('assistant', evt.greeting);
      if (frameworkEl) frameworkEl.textContent = JSON.stringify(evt.framework_progress || {}, null, 2);
      _playLiveSpeech(evt.speech, evt.greeting || '').catch(() => {});
      return;
    }

    if (evt.type === 'avatar.patient_message') {
      if (evt.patient_message)  addMsg('user',      evt.patient_message);
      if (evt.clinician_response) addMsg('assistant', evt.clinician_response);
      if (frameworkEl) frameworkEl.textContent = JSON.stringify(evt.framework_progress || {}, null, 2);
      _playLiveSpeech(evt.speech, evt.clinician_response || '').catch(() => {});
      return;
    }

    if (evt.type === 'avatar.live.connected') {
      if (statusPill) statusPill.textContent = 'Live stream connected';
    }
  }

  // ── Live WebSocket ───────────────────────────────────────────────────────

  function connectLiveStream() {
    if (!liveMode || liveSocket) return;
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    liveSocket = new WebSocket(`${protocol}://${window.location.host}/live/ws`);

    liveSocket.onopen  = () => { if (statusPill) statusPill.textContent = 'Live stream connected'; };
    liveSocket.onclose = () => {
      if (statusPill) statusPill.textContent = 'Live stream disconnected';
      liveSocket = null;
      setTimeout(connectLiveStream, 1500);
    };
    liveSocket.onerror = () => { if (statusPill) statusPill.textContent = 'Live stream error'; };
    liveSocket.onmessage = (event) => {
      try { handleLiveEvent(JSON.parse(event.data)); } catch (_) {}
    };
  }

  // ── Audio unlock ─────────────────────────────────────────────────────────

  async function enableAudio() {
    await window.TTSClient.enableAudio();
    audioEnabled = true;
    if (statusPill) statusPill.textContent = liveMode
      ? 'Live stream connected (audio enabled)'
      : 'Audio enabled';
    if (audioEnableBtn) {
      audioEnableBtn.disabled    = true;
      audioEnableBtn.textContent = 'Audio Enabled';
    }
  }

  // ── UI mode ───────────────────────────────────────────────────────────────

  function configureUiMode() {
    if (!readOnly) return;
    if (startBtn)   startBtn.disabled  = true;
    if (sendBtn)    sendBtn.disabled   = true;
    if (chatInput)  {
      chatInput.disabled     = true;
      chatInput.placeholder  = liveMode
        ? 'Live scenario stream mode (read-only)'
        : 'Read-only mode';
    }
  }

  // ── Event wiring ─────────────────────────────────────────────────────────

  startBtn.addEventListener('click', () => startSession().catch((e) => alert(e.message)));
  sendBtn.addEventListener('click',  () => sendMessage().catch((e) => alert(e.message)));
  if (audioEnableBtn) {
    audioEnableBtn.addEventListener('click', () =>
      enableAudio().catch((e) => alert(`Audio enable failed: ${e.message}`))
    );
  }
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage().catch((err) => alert(err.message));
  });
  // Signal listening state while user is actively typing
  chatInput.addEventListener('input', () => {
    if (sessionId && chatInput.value.trim()) {
      _setAvatarState('listening', 'Listening…');
    } else if (sessionId) {
      _setAvatarState('idle', '');
    }
  });
  avatarSelect.addEventListener('change', () =>
    window.AvatarRenderer.setAvatar(avatarSelect.value)
  );

  // ── Boot ─────────────────────────────────────────────────────────────────

  window.AvatarRenderer.init('avatar-canvas');
  window.AvatarRenderer.setAvatar(avatarSelect.value);
  configureUiMode();
  connectLiveStream();

  if (!readOnly) {
    enableAudio().catch(() => {
      if (statusPill) statusPill.textContent = 'Session ready (click Enable Audio if muted)';
    });
  } else if (!audioEnabled) {
    if (statusPill) statusPill.textContent = 'Live mode (click Enable Audio)';
  }
})();
