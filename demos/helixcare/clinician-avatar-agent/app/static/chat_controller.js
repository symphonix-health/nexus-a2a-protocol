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
  const chatLog        = document.getElementById('chat-log');
  const chatInput      = document.getElementById('chat-input');
  const sendBtn        = document.getElementById('send-btn');
  const startBtn       = document.getElementById('start-btn');
  const avatarSelect   = document.getElementById('avatar-select');
  const renderModeSelect = document.getElementById('render-mode-select');
  const voiceSelect    = document.getElementById('voice-select');
  const micBtn         = document.getElementById('mic-btn');
  const audioUploadInput = document.getElementById('audio-upload-input');
  // Patient mode controls
  const scenarioSelect     = document.getElementById('scenario-select');
  const patientContextBar  = document.getElementById('patient-context-bar');
  const aiPatientRespondBtn = document.getElementById('ai-patient-respond-btn');
  const autoRoleplayToggle = document.getElementById('auto-roleplay-toggle');
  const patientTtsToggle   = document.getElementById('patient-tts-toggle');   // optional: speak typed patient text
  const patientModeHuman   = document.getElementById('patient-mode-human');
  const patientModeAi      = document.getElementById('patient-mode-ai');
  const registrationFirstToggle = document.getElementById('registration-first-toggle');
  const nondeterministicToggle  = document.getElementById('nondeterministic-toggle');
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

  // ── Patient mode state ───────────────────────────────────────────────────
  let patientMode        = 'human';   // 'human' | 'ai'
  let patientContext     = null;      // loaded from patient_script_pack.json scenario
  let patientConversation = [];        // [{role, content}] for /api/patient/respond
  let lastClinicianText  = '';        // last clinician response, used by AI respond
  let scenarioPack       = [];        // array of scenario objects from pack

  // ── Patient mode ─────────────────────────────────────────────────────────

  function _applyPatientMode(mode) {
    patientMode = mode || 'human';
    const isAi = patientMode === 'ai';

    // AI-specific controls
    if (aiPatientRespondBtn) aiPatientRespondBtn.disabled = !isAi;
    if (autoRoleplayToggle)  autoRoleplayToggle.disabled  = !isAi;
    if (scenarioSelect)      scenarioSelect.disabled      = !isAi;
    if (patientContextBar)   patientContextBar.style.display = isAi ? '' : 'none';

    // Update input placeholder
    if (chatInput) {
      chatInput.placeholder = isAi
        ? 'Override AI patient text (or leave blank to use AI)…'
        : 'Type patient response…';
    }
  }

  // Load scenario pack and populate the scenario dropdown
  async function _loadScenarioPack() {
    if (!scenarioSelect) return;
    try {
      const resp = await fetch('/static/patient_script_pack.json', { cache: 'no-store' });
      if (!resp.ok) return;
      const payload = await resp.json();
      scenarioPack = Array.isArray(payload?.scenarios) ? payload.scenarios : [];
      scenarioPack.forEach((scenario, idx) => {
        const opt = document.createElement('option');
        opt.value = String(idx);
        opt.textContent = scenario.title || scenario.id || `Scenario ${idx + 1}`;
        scenarioSelect.appendChild(opt);
      });
    } catch (_) {}
  }

  // Called when the user picks a scenario — loads its patient_context
  function _loadPatientPersona() {
    if (!scenarioSelect) return;
    const idx = Number(scenarioSelect.value);
    const scenario = (!Number.isNaN(idx) && idx >= 0) ? scenarioPack[idx] : null;
    patientContext      = scenario?.patient_context || null;
    patientConversation = [];
    lastClinicianText   = '';
    if (patientContextBar) {
      if (patientContext) {
        const name = patientContext.name || 'Patient';
        const cc   = patientContext.chief_complaint || scenario?.title || '';
        patientContextBar.textContent = `🟢 ${name} · ${cc}`;
      } else {
        patientContextBar.textContent = '';
      }
    }
  }

  // Generate an AI patient response using the /api/patient/respond endpoint
  async function _generateAiPatientResponse() {
    if (!patientContext) {
      if (statusPill) statusPill.textContent = '⚠ Select a patient scenario first';
      return;
    }
    if (!lastClinicianText) {
      if (statusPill) statusPill.textContent = '⚠ No clinician message yet — start the consultation first';
      return;
    }
    if (!await _ensureToken()) return;

    if (statusPill) statusPill.textContent = 'AI patient thinking…';
    if (aiPatientRespondBtn) aiPatientRespondBtn.disabled = true;

    let patientText;
    try {
      const resp = await fetch('/api/patient/respond', {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clinician_message: lastClinicianText,
          patient_context: patientContext,
          conversation_history: patientConversation,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data?.detail || `Patient AI failed (${resp.status})`);
      patientText = String(data?.patient_response || '').trim();
    } catch (err) {
      if (statusPill) statusPill.textContent = `⚠ AI Patient: ${err.message}`;
      if (aiPatientRespondBtn) aiPatientRespondBtn.disabled = (patientMode !== 'ai');
      return;
    }

    if (!patientText) {
      if (statusPill) statusPill.textContent = '⚠ AI patient returned empty response';
      if (aiPatientRespondBtn) aiPatientRespondBtn.disabled = (patientMode !== 'ai');
      return;
    }

    // Record in local conversation history
    patientConversation.push({ role: 'user', content: patientText });

    // Display in chat
    addMsg('user', patientText);

    // Restore button
    if (aiPatientRespondBtn) aiPatientRespondBtn.disabled = (patientMode !== 'ai');
    if (statusPill) statusPill.textContent = sessionId ? `Session: ${sessionId}` : 'Session ready';

    // Speak the AI patient response in shimmer voice via streaming TTS
    window.TTSClient.cancel();
    window.LipSyncEngine.start([]);
    _setAvatarState('speaking', 'Patient speaking…');
    window.TTSClient.streamSpeak(patientText, 'shimmer', authToken, {
      onVisemes(visemes) { window.LipSyncEngine.start(visemes); },
      onSpeechStart()    { window.LipSyncEngine.stop(); _setAvatarState('speaking', 'Patient speaking…'); },
      onSpeechEnd()      {
        window.LipSyncEngine.stop();
        _setAvatarState('idle', '');
        if (statusPill) statusPill.textContent = sessionId ? `Session: ${sessionId}` : 'Session ready';
      },
      onError(msg)       {
        window.LipSyncEngine.stop();
        _setAvatarState('idle', '');
        if (statusPill) statusPill.textContent = `⚠ Patient TTS: ${msg}`;
      },
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
    // Unlock AudioContext before streaming — must be called before any await.
    window.TTSClient.enableAudio().catch(() => {});

    _setAvatarState('speaking', 'Speaking…');
    window.TTSClient.streamSpeak(text, voiceSelect.value, authToken, {
      onVisemes(visemes) {
        // Pre-computed timeline warm-up while waiting for first PCM chunk.
        window.LipSyncEngine.start(visemes);
      },
      onSpeechStart() {
        // Real PCM is flowing — amplitude polling takes over lipsync.
        window.LipSyncEngine.stop();
        _setAvatarState('speaking', 'Speaking…');
      },
      onSpeechEnd() {
        window.LipSyncEngine.stop();
        _setAvatarState('idle', '');
        if (statusPill) statusPill.textContent = sessionId ? `Session: ${sessionId}` : 'Session ready';
        if (onDone) onDone();
      },
      onError(msg) {
        // Hard TTS failure — surface visibly; no silent fallback.
        window.LipSyncEngine.stop();
        _setAvatarState('idle', '');
        if (statusPill) statusPill.textContent = `⚠ TTS Error: ${msg}`;
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

  // _loadScenarioPack and patient-mode functions are defined above

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

    // In human mode, optionally speak typed patient text via TTS (shimmer voice).
    // Only fires when the user explicitly enables the 'patient-tts-toggle' checkbox.
    if (text && patientMode === 'human' && patientTtsToggle?.checked && !options.fromAudio) {
      window.TTSClient.cancel();
      window.TTSClient.streamSpeak(text, 'shimmer', authToken, {
        onError() {/* silent — best-effort patient-side TTS */},
      });
    }
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

    // Track clinician message for AI patient; record both sides in conversation history
    lastClinicianText = response;
    patientConversation.push({ role: 'user',      content: text     });
    patientConversation.push({ role: 'assistant', content: response });
    // Cap conversation history at 30 entries so it doesn’t grow unboundedly
    if (patientConversation.length > 30) patientConversation = patientConversation.slice(-30);

    _speakStreaming(response, () => {
      // After clinician speaks, auto-respond as AI patient if toggled
      if (patientMode === 'ai' && autoRoleplayToggle?.checked) {
        _generateAiPatientResponse().catch(() => {});
      }
    });
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
      if (statusPill) statusPill.textContent = '⚠ Speech recognition is not supported in this browser';
      return;
    }
    if (!sessionId) {
      if (statusPill) statusPill.textContent = '⚠ Start a session first, then use speech input';
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
        if (micBtn) micBtn.disabled = true; // prevent double-tap during recognition
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
        if (micBtn) micBtn.disabled = false;
        if (sessionId) _setAvatarState('idle', '');
      };

      speechRecognition.onend = () => {
        isSpeechListening = false;
        _setMicUi(false);
        if (micBtn) micBtn.disabled = false;
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
    if (aiPatientRespondBtn) aiPatientRespondBtn.disabled = true;
    if (autoRoleplayToggle)  autoRoleplayToggle.disabled  = true;
    if (scenarioSelect)      scenarioSelect.disabled      = true;
    if (patientModeHuman)    patientModeHuman.disabled    = true;
    if (patientModeAi)       patientModeAi.disabled       = true;
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
  // Patient mode radio toggle
  if (patientModeHuman) {
    patientModeHuman.addEventListener('change', () => {
      if (patientModeHuman.checked) _applyPatientMode('human');
    });
  }
  if (patientModeAi) {
    patientModeAi.addEventListener('change', () => {
      if (patientModeAi.checked) _applyPatientMode('ai');
    });
  }
  if (scenarioSelect) {
    scenarioSelect.addEventListener('change', _loadPatientPersona);
  }
  if (aiPatientRespondBtn) {
    aiPatientRespondBtn.addEventListener('click', () =>
      _generateAiPatientResponse().catch((e) => {
        if (statusPill) statusPill.textContent = `⚠ AI Patient: ${e.message}`;
      })
    );
  }
  if (temperatureInput && temperatureValue) {
    const updateTemp = () => {
      temperatureValue.textContent = Number(temperatureInput.value || 0.7).toFixed(1);
    };
    updateTemp();
    temperatureInput.addEventListener('input', updateTemp);
  }

  // ── Boot ─────────────────────────────────────────────────────────────────

  window.AvatarRenderer.init('avatar-canvas');
  window.AvatarRenderer.setAvatar(avatarSelect.value);
  if (renderModeSelect) {
    window.AvatarRenderer.setRenderMode(renderModeSelect.value || 'static');
  }
  _applyPatientMode('human');  // default: human patient mode
  _loadScenarioPack();
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
