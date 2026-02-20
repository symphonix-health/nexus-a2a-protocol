window.TTSClient = (() => {
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

  function playAudioB64(audioB64, mimeType = 'audio/wav') {
    if (!audioB64) return null;
    const audio = new Audio(`data:${mimeType};base64,${audioB64}`);
    audio.play().catch(() => {});
    return audio;
  }

  return { synthesize, playAudioB64 };
})();
