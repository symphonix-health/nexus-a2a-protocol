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
  const renderModeSelect = document.getElementById('render-mode-select');
  const voiceSelect   = document.getElementById('voice-select');
  const micBtn        = document.getElementById('mic-btn');
  const audioUploadInput = document.getElementById('audio-upload-input');
  const scriptLineSelect = document.getElementById('script-line-select');
  const scriptLineMeta = document.getElementById('script-line-meta');
  const useScriptBtn = document.getElementById('use-script-btn');
  const playScriptClipBtn = document.getElementById('play-script-clip-btn');
  const registrationFirstToggle = document.getElementById('registration-first-toggle');
  const nondeterministicToggle = document.getElementById('nondeterministic-toggle');
  const temperatureInput = document.getElementById('temperature-input');
  const temperatureValue = document.getElementById('temperature-value');
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
  let speechRecognition = null;
  let isSpeechListening = false;
  let scriptPack = [];

  function _flattenScriptPack(payload) {
    const flattened = [];

    const topLevelLines = Array.isArray(payload?.lines) ? payload.lines : [];
    topLevelLines.forEach((line) => {
      if (typeof line === 'string') {
        flattened.push({ text: line, phase: 'clinical', intent: 'generic' });
      } else if (line && typeof line === 'object') {
        flattened.push({
          scenario_title: 'General',
          ...line,
          text: String(line.text || '').trim(),
        });
      }
    });

    const scenarios = Array.isArray(payload?.scenarios) ? payload.scenarios : [];
    scenarios.forEach((scenario) => {
      const lines = Array.isArray(scenario?.lines) ? scenario.lines : [];
      lines.forEach((line) => {
        if (typeof line === 'string') {
          flattened.push({
            scenario_id: scenario?.id,
            scenario_title: scenario?.title || scenario?.id || 'Scenario',
            text: line,
            phase: 'clinical',
            intent: 'generic',
          });
        } else if (line && typeof line === 'object') {
          flattened.push({
            scenario_id: scenario?.id,
            scenario_title: scenario?.title || scenario?.id || 'Scenario',
            ...line,
            text: String(line.text || '').trim(),
          });
        }
      });
    });

    return flattened.filter((line) => line.text);
  }

  function _selectedScriptLine() {
    if (!scriptLineSelect) return null;
    const idx = Number(scriptLineSelect.value || -1);
    if (Number.isNaN(idx) || idx < 0 || idx >= scriptPack.length) return null;
    return scriptPack[idx];
  }

  function _renderSelectedScriptMeta() {
    if (!scriptLineMeta) return;
    const line = _selectedScriptLine();
    if (!line) {
      scriptLineMeta.textContent = '';
      return;
    }
    const scenario = line.scenario_title ? `[${line.scenario_title}]` : '';
    const phase = line.phase ? `phase: ${line.phase}` : '';
    const intent = line.intent ? `intent: ${line.intent}` : '';
    const fields = Array.isArray(line.expected_fields) && line.expected_fields.length
      ? `capture: ${line.expected_fields.join(', ')}`
      : '';
    scriptLineMeta.textContent = [scenario, phase, intent, fields].filter(Boolean).join(' · ');
  }

  function _playScriptClip() {
    const line = _selectedScriptLine();
    if (!line) {
      alert('Select a script line first.');
      return;
    }
    const clipName = String(line.audio_clip || '').trim();
    if (!clipName) {
      alert('No sample clip is mapped for this line yet. Add audio_clip and place the file in avatar/.');
      return;
    }
    const audio = new Audio(`/media/${encodeURIComponent(clipName)}`);
    audio.play().catch(() => {
      alert(`Unable to play ${clipName}. Ensure the file exists in avatar/.`);
    });
  }

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

    startBtn.disabled = true;
    startBtn.textContent = 'Starting…';

    window.AvatarRenderer.setAvatar(avatarSelect.value);
    _setAvatarState('thinking', 'Starting…');

    const result = await rpc('avatar/start_session', {
      patient_case: {
        registration_first_mode: Boolean(registrationFirstToggle?.checked),
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
      llm_config: {
        nondeterministic: Boolean(nondeterministicToggle?.checked),
        temperature: Number(temperatureInput?.value || 0.7),
      },
    });

    sessionId = result.session_id;
    startBtn.textContent = 'Session Active';
    startBtn.classList.add('session-active');
    if (statusPill) statusPill.textContent = `Session: ${sessionId}`;
    if (frameworkEl) frameworkEl.textContent = JSON.stringify(result.framework_progress, null, 2);

    const greeting = result.greeting || 'Session started.';
    addMsg('assistant', greeting);

    // Speak the greeting via streaming TTS
    _speakStreaming(greeting, null);
  }

  async function _loadScriptPack() {
    if (!scriptLineSelect) return;
    try {
      const resp = await fetch('/static/patient_script_pack.json', { cache: 'no-store' });
      if (!resp.ok) return;
      const payload = await resp.json();
      scriptPack = _flattenScriptPack(payload);
      scriptPack.forEach((line, idx) => {
        const opt = document.createElement('option');
        const text = String(line?.text || '');
        const scenarioLabel = line?.scenario_title ? `[${line.scenario_title}] ` : '';
        opt.value = String(idx);
        opt.textContent = `${idx + 1}. ${scenarioLabel}${text.slice(0, 80)}`;
        scriptLineSelect.appendChild(opt);
      });
      _renderSelectedScriptMeta();
    } catch (_) {}
  }

  async function _transcribeUploadedAudio(file) {
    if (!file) return;
    if (!sessionId) {
      alert('Start a session first, then upload patient audio.');
      return;
    }
    if (!await _ensureToken()) return;

    const fd = new FormData();
    fd.append('file', file);
    fd.append('language', 'en');
    if (statusPill) statusPill.textContent = 'Transcribing uploaded audio…';

    let data;
    try {
      const resp = await fetch('/api/stt/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
        body: fd,
      });
      data = await resp.json();
      if (!resp.ok) {
        throw new Error(data?.detail || `Transcription failed (${resp.status})`);
      }
    } catch (err) {
      if (statusPill) statusPill.textContent = `Session: ${sessionId}`;
      alert(err.message || 'Audio transcription failed.');
      return;
    }

    const transcript = String(data?.transcript || '').trim();
    if (!transcript) {
      alert('Transcription returned empty text. Try a clearer recording.');
      if (statusPill) statusPill.textContent = `Session: ${sessionId}`;
      return;
    }

    await sendMessage(transcript, { fromAudio: true, deferTranscript: true });
    if (audioUploadInput) audioUploadInput.value = '';
  }

  // ── Send message (barge-in aware) ────────────────────────────────────────

  async function sendMessage(overrideText = null, options = {}) {
    if (readOnly) return;
    // Same AudioContext unlock — must be before any `await`.
    window.TTSClient.enableAudio().catch(() => {});

    const text = (overrideText == null ? chatInput.value : String(overrideText)).trim();
    if (!text || !sessionId) return;
    if (overrideText == null) chatInput.value = '';

    const fromAudio = Boolean(options.fromAudio);
    const deferTranscript = Boolean(options.deferTranscript);

    // Barge-in: cancel any avatar speech in progress
    window.TTSClient.cancel();
    window.LipSyncEngine.stop();

    if (!deferTranscript) {
      addMsg('user', text);
    }
    _setAvatarState('thinking', 'Thinking…');
    if (statusPill) {
      statusPill.textContent = fromAudio ? 'Transcribing & processing…' : 'Processing…';
    }

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

    if (deferTranscript) {
      setTimeout(() => {
        addMsg('user', `📝 Transcript: ${text}`);
      }, 600);
    }

    _speakStreaming(response, null);
  }

  function _speechApiCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function _setMicUi(active) {
    if (!micBtn) return;
    micBtn.dataset.active = active ? '1' : '0';
    micBtn.textContent = active ? '🛑 Stop' : '🎤 Speak';
  }

  function _stopSpeechCapture() {
    if (!speechRecognition) return;
    try {
      speechRecognition.stop();
    } catch (_) {}
    isSpeechListening = false;
    _setMicUi(false);
    if (sessionId) _setAvatarState('idle', '');
  }

  function _startSpeechCapture() {
    const Ctor = _speechApiCtor();
    if (!Ctor) {
      alert('Speech recognition is not supported in this browser.');
      return;
    }
    if (!sessionId) {
      alert('Start a session first, then use speech input.');
      return;
    }

    if (!speechRecognition) {
      speechRecognition = new Ctor();
      speechRecognition.lang = 'en-US';
      speechRecognition.interimResults = true;
      speechRecognition.continuous = false;

      let finalText = '';

      speechRecognition.onstart = () => {
        isSpeechListening = true;
        _setMicUi(true);
        _setAvatarState('listening', 'Listening…');
      };

      speechRecognition.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const part = event.results[i][0]?.transcript || '';
          if (event.results[i].isFinal) {
            finalText += `${part} `;
          }
        }
      };

      speechRecognition.onerror = () => {
        isSpeechListening = false;
        _setMicUi(false);
        if (sessionId) _setAvatarState('idle', '');
      };

      speechRecognition.onend = () => {
        isSpeechListening = false;
        _setMicUi(false);
        const transcript = finalText.trim();
        finalText = '';
        if (transcript) {
          chatInput.value = '';
          sendMessage(transcript, {
            fromAudio: true,
            deferTranscript: true,
          }).catch((err) => alert(err.message));
        } else if (sessionId) {
          _setAvatarState('idle', '');
        }
      };
    }

    try {
      speechRecognition.start();
    } catch (_) {
      _stopSpeechCapture();
    }
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
    if (micBtn)     micBtn.disabled    = true;
    if (audioUploadInput) audioUploadInput.disabled = true;
    if (useScriptBtn) useScriptBtn.disabled = true;
    if (playScriptClipBtn) playScriptClipBtn.disabled = true;
    if (scriptLineSelect) scriptLineSelect.disabled = true;
    if (chatInput)  {
      chatInput.disabled     = true;
      chatInput.placeholder  = liveMode
        ? 'Live scenario stream mode (read-only)'
        : 'Read-only mode';
    }
  }

  // ── Event wiring ─────────────────────────────────────────────────────────

  startBtn.addEventListener('click', () => startSession().catch((e) => {
    startBtn.disabled = false;
    startBtn.textContent = 'Start Session';
    alert(e.message);
  }));
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
  if (renderModeSelect) {
    renderModeSelect.addEventListener('change', () =>
      window.AvatarRenderer.setRenderMode(renderModeSelect.value)
    );
  }
  if (micBtn) {
    micBtn.addEventListener('click', () => {
      if (isSpeechListening) _stopSpeechCapture();
      else _startSpeechCapture();
    });
  }
  if (audioUploadInput) {
    audioUploadInput.addEventListener('change', (event) => {
      const file = event.target?.files?.[0];
      _transcribeUploadedAudio(file).catch((err) => alert(err.message));
    });
  }
  if (useScriptBtn && scriptLineSelect) {
    useScriptBtn.addEventListener('click', () => {
      const selected = _selectedScriptLine();
      const line = String(selected?.text || '').trim();
      if (!line) return;
      chatInput.value = line;
      chatInput.focus();
    });
  }
  if (scriptLineSelect) {
    scriptLineSelect.addEventListener('change', _renderSelectedScriptMeta);
  }
  if (playScriptClipBtn) {
    playScriptClipBtn.addEventListener('click', _playScriptClip);
  }
  if (temperatureInput && temperatureValue) {
    const updateTemp = () => {
      temperatureValue.textContent = Number(temperatureInput.value || 0.7).toFixed(1);
    };
    updateTemp();
    temperatureInput.addEventListener('input', updateTemp);
  }

  window.addEventListener('nexus_tts_synthetic_fallback', () => {
    if (statusPill) {
      statusPill.textContent = 'Using browser fallback voice (set OPENAI_API_KEY for natural TTS)';
    }
  });

  // ── Boot ─────────────────────────────────────────────────────────────────

  window.AvatarRenderer.init('avatar-canvas');
  window.AvatarRenderer.setAvatar(avatarSelect.value);
  if (renderModeSelect) {
    window.AvatarRenderer.setRenderMode(renderModeSelect.value || 'static');
  }
  _loadScriptPack();
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
