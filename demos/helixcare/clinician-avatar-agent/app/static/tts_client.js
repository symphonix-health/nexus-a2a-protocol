window.TTSClient = (() => {
  let audioUnlocked = false;

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

  async function enableAudio() {
    // Attempt to unlock audio playback policy with a user gesture.
    const probe = new Audio();
    probe.muted = true;
    try {
      await probe.play();
      probe.pause();
    } catch (_) {
      // Ignore: some browsers still unlock from user-initiated speech synthesis.
    }
    audioUnlocked = true;
    return true;
  }

  function _pickVoice(voiceHint = '') {
    const voices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
    if (!voices.length) return null;
    const hint = String(voiceHint || '').toLowerCase();
    if (hint) {
      const matched = voices.find((v) => v.name.toLowerCase().includes(hint));
      if (matched) return matched;
    }
    const english = voices.find((v) => String(v.lang || '').toLowerCase().startsWith('en'));
    return english || voices[0] || null;
  }

  function speakTextFallback(text, voiceHint = '') {
    const clean = String(text || '').trim();
    if (!clean || !window.speechSynthesis) return null;
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;
    const voice = _pickVoice(voiceHint);
    if (voice) utterance.voice = voice;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
    return utterance;
  }

  async function playAudioB64(audioB64, mimeType = 'audio/wav', fallbackText = '', voiceHint = '') {
    if (!audioB64) {
      return speakTextFallback(fallbackText, voiceHint);
    }

    const audio = new Audio(`data:${mimeType};base64,${audioB64}`);
    audio.volume = 1.0;
    try {
      await audio.play();
    } catch (_) {
      if (!audioUnlocked) {
        // Most common cause in embedded iframe/live mode: autoplay policy.
        return speakTextFallback(fallbackText, voiceHint);
      }
      return speakTextFallback(fallbackText, voiceHint);
    }
    return audio;
  }

  return { synthesize, enableAudio, playAudioB64, speakTextFallback };
})();
