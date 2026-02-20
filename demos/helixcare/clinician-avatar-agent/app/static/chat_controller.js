(() => {
  const chatLog = document.getElementById('chat-log');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  const startBtn = document.getElementById('start-btn');
  const avatarSelect = document.getElementById('avatar-select');
  const voiceSelect = document.getElementById('voice-select');
  const statusPill = document.getElementById('status-pill');
  const frameworkState = document.getElementById('framework-state');

  let authToken = '';
  let sessionId = '';

  function addMsg(role, text) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.textContent = text;
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

  startBtn.addEventListener('click', () => startSession().catch((e) => alert(e.message)));
  sendBtn.addEventListener('click', () => sendMessage().catch((e) => alert(e.message)));
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage().catch((err) => alert(err.message));
  });
  avatarSelect.addEventListener('change', () => window.AvatarRenderer.setAvatar(avatarSelect.value));

  window.AvatarRenderer.init('avatar-canvas');
  window.AvatarRenderer.setAvatar(avatarSelect.value);
})();
