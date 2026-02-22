(() => {
  const chatLog = document.getElementById('chat-log');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const startBtn = document.getElementById('start-btn');
  const avatarSelect = document.getElementById('avatar-select');
  const voiceSelect = document.getElementById('voice-select');
  const statusPill = document.getElementById('status-pill');
  const frameworkState = document.getElementById('framework-state');
  const audioEnableBtn = document.getElementById('audio-enable-btn');

  let authToken = '';
  let sessionId = '';
  const query = new URLSearchParams(window.location.search);
  const liveMode = query.get('live') === '1';
  const readOnlyMode = query.get('readonly') === '1' || liveMode;
  let liveSocket = null;
  let audioEnabled = false;

  function normalizeText(text) {
    const clean = String(text || '').trim();
    if (!clean) return '';
    return clean
      .replace(/\s+\?/g, '?')
      .replace(/\s+!/g, '!')
      .replace(/\s+\./g, '.')
      .replace(/\n{3,}/g, '\n\n');
  }

  function addMsg(role, text) {
    const normalized = normalizeText(text);
    if (!normalized) return;
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.textContent = normalized;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  async function rpc(method, params) {
    const payload = {
      jsonrpc: '2.0',
      id: String(Date.now()),
      method,
      params,
    };
    const resp = await fetch('/rpc', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`RPC ${method} failed: ${resp.status}`);
    const body = await resp.json();
    if (body.error) throw new Error(body.error.message || 'RPC error');
    return body.result;
  }

  async function startSession() {
    if (readOnlyMode) return;
    if (!authToken) {
      authToken = prompt('Paste bearer token (dev JWT)');
      if (!authToken) return;
    }

    window.AvatarRenderer.setAvatar(avatarSelect.value);

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
        name: 'Dr. Maya',
        specialty: 'emergency medicine',
        role: 'physician',
        style: 'calm, empathetic, and precise',
      },
    });

    sessionId = result.session_id;
    statusPill.textContent = `Session: ${sessionId}`;
    frameworkState.textContent = JSON.stringify(result.framework_progress, null, 2);
    addMsg('assistant', result.greeting || 'Session started.');
  }

  async function sendMessage() {
    if (readOnlyMode) return;
    const text = chatInput.value.trim();
    if (!text || !sessionId) return;
    chatInput.value = '';
    addMsg('user', text);

    const result = await rpc('avatar/patient_message', {
      session_id: sessionId,
      message: text,
    });

    addMsg('assistant', result.clinician_response || '(no response)');
    frameworkState.textContent = JSON.stringify(result.framework_progress || {}, null, 2);

    try {
      const tts = await window.TTSClient.synthesize(
        result.clinician_response || '',
        voiceSelect.value,
        authToken
      );
      window.LipSyncEngine.start(tts.visemes || []);
      window.TTSClient.playAudioB64(tts.audio_b64, tts.mime_type);
    } catch (err) {
      console.warn('TTS/lipsync fallback', err);
    }
  }

  async function playSpeech(speech, fallbackText = '') {
    if (!speech || typeof speech !== 'object') return;
    const visemes = Array.isArray(speech.visemes) ? speech.visemes : [];
    if (visemes.length) {
      window.LipSyncEngine.start(visemes);
    }
    await window.TTSClient.playAudioB64(
      speech.audio_b64 || '',
      speech.mime_type || 'audio/wav',
      speech.text || fallbackText || '',
      speech.voice || voiceSelect.value
    );
  }

  function handleLiveEvent(evt) {
    if (!evt || typeof evt !== 'object' || !evt.type) return;

    if (evt.type === 'avatar.session_started') {
      sessionId = evt.session_id || sessionId;
      statusPill.textContent = sessionId ? `Live Session: ${sessionId}` : 'Live Session';
      if (evt.greeting) {
        addMsg('assistant', evt.greeting);
      }
      frameworkState.textContent = JSON.stringify(evt.framework_progress || {}, null, 2);
      playSpeech(evt.speech, evt.greeting || '').catch(() => {});
      return;
    }

    if (evt.type === 'avatar.patient_message') {
      if (evt.patient_message) {
        addMsg('user', evt.patient_message);
      }
      if (evt.clinician_response) {
        addMsg('assistant', evt.clinician_response);
      }
      frameworkState.textContent = JSON.stringify(evt.framework_progress || {}, null, 2);
      playSpeech(evt.speech, evt.clinician_response || '').catch(() => {});
      return;
    }

    if (evt.type === 'avatar.live.connected') {
      statusPill.textContent = 'Live stream connected';
    }
  }

  async function enableAudio() {
    await window.TTSClient.enableAudio();
    audioEnabled = true;
    statusPill.textContent = liveMode
      ? 'Live stream connected (audio enabled)'
      : 'Audio enabled';
    if (audioEnableBtn) {
      audioEnableBtn.disabled = true;
      audioEnableBtn.textContent = 'Audio Enabled';
    }
  }

  function connectLiveStream() {
    if (!liveMode || liveSocket) return;
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${protocol}://${window.location.host}/live/ws`;
    liveSocket = new WebSocket(wsUrl);

    liveSocket.onopen = () => {
      statusPill.textContent = 'Live stream connected';
    };

    liveSocket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleLiveEvent(payload);
      } catch (err) {
        console.warn('Invalid live avatar event', err);
      }
    };

    liveSocket.onclose = () => {
      statusPill.textContent = 'Live stream disconnected';
      liveSocket = null;
      setTimeout(connectLiveStream, 1500);
    };

    liveSocket.onerror = () => {
      statusPill.textContent = 'Live stream error';
    };
  }

  function configureUiMode() {
    if (!readOnlyMode) return;
    startBtn.disabled = true;
    sendBtn.disabled = true;
    chatInput.disabled = true;
    chatInput.placeholder = liveMode
      ? 'Live scenario stream mode (read-only)'
      : 'Read-only mode';
  }

  startBtn.addEventListener('click', () => startSession().catch((e) => alert(e.message)));
  sendBtn.addEventListener('click', () => sendMessage().catch((e) => alert(e.message)));
  if (audioEnableBtn) {
    audioEnableBtn.addEventListener('click', () => {
      enableAudio().catch((e) => alert(`Audio enable failed: ${e.message}`));
    });
  }
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage().catch((err) => alert(err.message));
  });
  avatarSelect.addEventListener('change', () => window.AvatarRenderer.setAvatar(avatarSelect.value));

  window.AvatarRenderer.init('avatar-canvas');
  window.AvatarRenderer.setAvatar(avatarSelect.value);
  configureUiMode();
  connectLiveStream();
  if (!readOnlyMode) {
    enableAudio().catch(() => {
      statusPill.textContent = 'Session ready (click Enable Audio if muted)';
    });
  } else if (!audioEnabled) {
    statusPill.textContent = 'Live mode (click Enable Audio)';
  }
})();
