/**
 * RealtimeClient v10 — OpenAI Realtime API via WebRTC with spectral lip sync.
 *
 * Uses a direct WebRTC peer connection to the OpenAI Realtime API.  Produces
 * dramatically more natural voice than standard TTS because the Realtime model
 * generates speech natively (speech-to-speech, not text-to-speech conversion).
 *
 * Architecture:
 *   1. Backend mints an ephemeral client secret (POST /api/realtime/token).
 *   2. Browser creates an RTCPeerConnection with a silent local audio track.
 *   3. SDP offer is sent to OpenAI with the ephemeral key → answer SDP back.
 *   4. Remote audio stream → <audio> element (playback) + AnalyserNode (lip sync).
 *   5. Data channel ("oai-events") sends text and receives lifecycle events.
 *
 * Lip sync: Remote audio routed through AnalyserNode for frequency-band
 * analysis every 40 ms → AvatarRenderer.applyVisemeParams({ jawOpen, mouthWidth, lipPucker }).
 *
 * Clinician voice only — patient voice continues to use TTSClient (shimmer).
 * Voice is locked after first audio in a Realtime session.
 */
window.RealtimeClient = (() => {
  // ── State ─────────────────────────────────────────────────────────────────
  let _pc       = null;   // RTCPeerConnection
  let _dc       = null;   // WebRTC data channel ("oai-events")
  let _audioEl  = null;   // <audio> element for remote stream playback
  let _active   = false;  // True when session is connected and usable
  let _speaking = false;  // True while a speak request is in flight

  // AnalyserNode for lip sync
  let _audioCtx         = null;
  let _mediaStreamSrc   = null;
  let _analyser         = null;
  let _analyserBuf      = null;
  let _ampTimer         = null;

  // Current speak request state
  let _callbacks        = {};  // { onSpeechStart, onSpeechEnd, onError }
  let _speechStarted    = false;
  let _responseDone     = false;
  let _silenceMs        = 0;   // ms of consecutive silence after response.done

  const AMP_POLL_MS     = 40;
  const SPEECH_THRESHOLD = 0.015;  // RMS above this = speech detected
  const SILENCE_END_MS  = 400;    // ms of silence after response.done → speechEnd
  const MAX_WAIT_AFTER_DONE = 4000; // hard timeout after response.done

  // ── Audio context helper ──────────────────────────────────────────────────
  function _getAudioContext() {
    if (!_audioCtx) {
      _audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 24000,
      });
    }
    if (_audioCtx.state === 'suspended') {
      _audioCtx.resume().catch(() => {});
    }
    return _audioCtx;
  }

  // ── Spectral lip-sync analysis ────────────────────────────────────────────
  function _startAmpPoller() {
    if (_ampTimer) return;
    _silenceMs = 0;
    const sampleRate = _audioCtx ? _audioCtx.sampleRate : 24000;
    const fftSize = _analyser ? _analyser.fftSize : 512;
    const binHz = sampleRate / fftSize;

    _ampTimer = setInterval(() => {
      if (!_analyser || !_analyserBuf) return;

      // Frequency-domain analysis → multi-parameter visemes
      _analyser.getByteFrequencyData(_analyserBuf);
      const binCount = _analyser.frequencyBinCount;

      // Energy in three speech-relevant frequency bands
      let lowE = 0, midE = 0, highE = 0;
      let lowN = 0, midN = 0, highN = 0;

      for (let i = 0; i < binCount; i++) {
        const freq = i * binHz;
        const val = _analyserBuf[i] / 255;
        if (freq >= 80 && freq < 400)        { lowE += val; lowN++; }
        else if (freq >= 400 && freq < 2200)  { midE += val; midN++; }
        else if (freq >= 2200 && freq < 6500) { highE += val; highN++; }
      }

      lowE  = lowN  > 0 ? lowE  / lowN  : 0;
      midE  = midN  > 0 ? midE  / midN  : 0;
      highE = highN > 0 ? highE / highN : 0;

      const totalE = (lowE + midE + highE) / 3;

      // --- Map spectral features to mouth-shape parameters ---
      // Jaw openness: overall energy (louder → more open)
      const jawOpen = Math.min(1, totalE * 3.2);

      // Mouth width: high-freq emphasis → spread (ee, ss); low → narrow
      const freqSum = midE + highE + 0.001;
      const hiRatio = highE / freqSum;
      const mouthWidth = 0.45 + hiRatio * 0.55;

      // Lip pucker: low-freq dominant with weak highs → rounded (oo, oh)
      const loRatio = lowE / (totalE + 0.001);
      const lipPucker = (loRatio > 0.55 && highE < lowE * 0.4)
        ? Math.min(1, (loRatio - 0.4) * 2.5) : 0;

      // Drive lip sync with spectral parameters
      if (window.AvatarRenderer) {
        if (window.AvatarRenderer.applyVisemeParams) {
          window.AvatarRenderer.applyVisemeParams({
            jawOpen,
            mouthWidth,
            lipPucker,
            rms: totalE,
          });
        } else {
          window.AvatarRenderer.applyViseme(Math.min(1, totalE * 10));
        }
      }

      // Detect speech start via energy threshold
      if (!_speechStarted && totalE > SPEECH_THRESHOLD) {
        _speechStarted = true;
        if (_callbacks.onSpeechStart) _callbacks.onSpeechStart();
      }

      // After response.done, detect sustained silence → speech ended
      if (_responseDone) {
        if (totalE < SPEECH_THRESHOLD) {
          _silenceMs += AMP_POLL_MS;
        } else {
          _silenceMs = 0;
        }
        if (_silenceMs >= SILENCE_END_MS) {
          _finishSpeak();
        }
      }
    }, AMP_POLL_MS);
  }

  function _stopAmpPoller() {
    if (_ampTimer) { clearInterval(_ampTimer); _ampTimer = null; }
    if (window.AvatarRenderer) {
      if (window.AvatarRenderer.applyVisemeParams) {
        window.AvatarRenderer.applyVisemeParams({ jawOpen: 0, mouthWidth: 0.5, lipPucker: 0, rms: 0 });
      } else {
        window.AvatarRenderer.applyViseme(0);
      }
    }
  }

  function _finishSpeak() {
    _stopAmpPoller();
    _speaking = false;
    const cb = _callbacks;
    _callbacks = {};
    if (cb.onSpeechEnd) cb.onSpeechEnd();
  }

  // ── Handle server events from data channel ────────────────────────────────
  function _handleServerEvent(e) {
    let event;
    try { event = JSON.parse(e.data); } catch (_) { return; }

    // Session lifecycle
    if (event.type === 'session.created' || event.type === 'session.updated') {
      console.log('[RealtimeClient]', event.type);
      return;
    }

    // Response lifecycle — detect when model finished generating
    if (event.type === 'response.created') {
      console.log('[RealtimeClient] response.created');
      return;
    }

    if (event.type === 'response.done') {
      console.log('[RealtimeClient] response.done — status:', event.response?.status);
      _responseDone = true;
      // Hard timeout: if silence detection doesn't trigger, force-end after MAX_WAIT
      setTimeout(() => {
        if (_speaking) _finishSpeak();
      }, MAX_WAIT_AFTER_DONE);

      // Check for errors in the response
      if (event.response?.status === 'failed') {
        const errMsg = event.response?.status_details?.error?.message || 'Realtime response failed';
        _stopAmpPoller();
        _speaking = false;
        if (_callbacks.onError) _callbacks.onError(errMsg);
        _callbacks = {};
      }
      return;
    }

    if (event.type === 'error') {
      console.error('[RealtimeClient] error:', event.error);
      _stopAmpPoller();
      _speaking = false;
      if (_callbacks.onError) _callbacks.onError(event.error?.message || 'Realtime API error');
      _callbacks = {};
      return;
    }

    if (event.type === 'rate_limits.updated') {
      // Informational — ignore
      return;
    }

    // Log any unhandled events in debug mode
    if (event.type) {
      console.log('[RealtimeClient] event:', event.type);
    }
  }

  // ── Public: initialize WebRTC session ─────────────────────────────────────
  /**
   * Initialize a WebRTC session with OpenAI Realtime API.
   *
   * Must be called within a user-gesture handler (click/keydown) because it
   * creates an AudioContext which browsers block outside gestures.
   *
   * @param {string} authToken  JWT for our backend
   * @param {object} [options]  { voice: 'coral' }
   * @returns {Promise<boolean>} true if connected successfully
   */
  async function init(authToken, options = {}) {
    if (_active && _dc && _dc.readyState === 'open') return true;

    // Clean up any previous session
    close();

    const voice = options.voice || 'coral';

    // 1. Get ephemeral key from our backend
    let ephemeralKey;
    try {
      const resp = await fetch('/api/realtime/token', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ voice }),
      });
      if (!resp.ok) {
        console.warn('[RealtimeClient] Token endpoint returned', resp.status);
        return false;
      }
      const data = await resp.json();
      ephemeralKey = data?.client_secret?.value;
      if (!ephemeralKey) {
        console.warn('[RealtimeClient] No ephemeral key in response');
        return false;
      }
    } catch (err) {
      console.warn('[RealtimeClient] Failed to get token:', err.message);
      return false;
    }

    // 2. Create peer connection
    _pc = new RTCPeerConnection();

    // 3. Set up remote audio playback + AnalyserNode for lip sync
    _audioEl = document.createElement('audio');
    _audioEl.autoplay = true;

    _pc.ontrack = (e) => {
      // Play audio via <audio> element
      _audioEl.srcObject = e.streams[0];
      _audioEl.muted = false;
      _audioEl.volume = 1.0;
      _audioEl.playsInline = true;
      _audioEl.play().catch((err) => {
        console.warn('[RealtimeClient] Remote audio play() blocked:', err?.message || err);
      });

      // Also route through AnalyserNode for lip sync amplitude measurement
      try {
        const ctx = _getAudioContext();
        _mediaStreamSrc = ctx.createMediaStreamSource(e.streams[0]);
        _analyser = ctx.createAnalyser();
        _analyser.fftSize = 512;
        _analyser.smoothingTimeConstant = 0.3;
        _analyserBuf = new Uint8Array(_analyser.frequencyBinCount);
        _mediaStreamSrc.connect(_analyser);
        // Analyser is read-only — audio playback comes from <audio> element
      } catch (err) {
        console.warn('[RealtimeClient] AnalyserNode setup failed:', err.message);
      }
    };

    // 4. Add a silent local audio track (required for WebRTC negotiation)
    try {
      const ctx = _getAudioContext();
      const dest = ctx.createMediaStreamDestination();
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value = 0; // completely silent
      osc.connect(gain);
      gain.connect(dest);
      osc.start();
      const silentTrack = dest.stream.getTracks()[0];
      _pc.addTrack(silentTrack);
    } catch (err) {
      console.warn('[RealtimeClient] Silent track creation failed:', err.message);
      _pc.close(); _pc = null;
      return false;
    }

    // 5. Create data channel for events
    _dc = _pc.createDataChannel('oai-events');
    _dc.addEventListener('message', _handleServerEvent);

    // 6. Create SDP offer and connect to OpenAI
    try {
      const offer = await _pc.createOffer();
      await _pc.setLocalDescription(offer);

      const sdpResp = await fetch('https://api.openai.com/v1/realtime/calls', {
        method: 'POST',
        body: offer.sdp,
        headers: {
          'Authorization': `Bearer ${ephemeralKey}`,
          'Content-Type': 'application/sdp',
        },
      });

      if (!sdpResp.ok) {
        const errText = await sdpResp.text().catch(() => 'unknown');
        console.warn('[RealtimeClient] SDP exchange failed:', sdpResp.status, errText);
        _pc.close(); _pc = null; _dc = null;
        return false;
      }

      const answerSdp = await sdpResp.text();
      await _pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
    } catch (err) {
      console.warn('[RealtimeClient] WebRTC setup failed:', err.message);
      _pc.close(); _pc = null; _dc = null;
      return false;
    }

    // 7. Wait for data channel to open
    try {
      await new Promise((resolve, reject) => {
        if (_dc.readyState === 'open') { resolve(); return; }
        const onOpen = () => { _dc.removeEventListener('error', onErr); resolve(); };
        const onErr  = () => { _dc.removeEventListener('open', onOpen); reject(new Error('DC error')); };
        _dc.addEventListener('open', onOpen, { once: true });
        _dc.addEventListener('error', onErr, { once: true });
        setTimeout(() => reject(new Error('Data channel open timeout')), 15000);
      });
    } catch (err) {
      console.warn('[RealtimeClient] Data channel failed:', err.message);
      _pc.close(); _pc = null; _dc = null;
      return false;
    }

    _active = true;
    console.log('[RealtimeClient] Connected — voice:', voice);

    // 8. Configure session: disable VAD (we send text, not audio), set instructions
    _dc.send(JSON.stringify({
      type: 'session.update',
      session: {
        instructions: 'You are a voice reader. When you receive text, read it aloud exactly as written with natural, warm clinician pacing. Do not add, paraphrase, or interpret the text. Just read it naturally and expressively.',
        input_audio_transcription: null,
        turn_detection: null,  // disable VAD — we control input via text
      },
    }));

    return true;
  }

  // ── Public: speak text ────────────────────────────────────────────────────
  /**
   * Speak text using the Realtime API.
   *
   * The model reads the text aloud with natural expressive speech.
   * Uses out-of-band responses to avoid polluting the conversation state.
   *
   * @param {string}  text       The text to read aloud.
   * @param {object}  callbacks  { onSpeechStart, onSpeechEnd, onError }
   * @param {object}  [options]  { instructions } — override read instructions
   */
  function speak(text, callbacks = {}, options = {}) {
    if (!_dc || _dc.readyState !== 'open') {
      if (callbacks.onError) callbacks.onError('Realtime session not connected');
      return;
    }

    // Cancel any ongoing speech
    if (_speaking) {
      _stopAmpPoller();
      try { _dc.send(JSON.stringify({ type: 'response.cancel' })); } catch (_) {}
    }

    _callbacks      = callbacks;
    _speechStarted  = false;
    _responseDone   = false;
    _silenceMs      = 0;
    _speaking       = true;

    // Start lip sync poller immediately (will detect audio when it arrives)
    _startAmpPoller();

    const readInstructions = options.instructions ||
      `Read this text aloud exactly as written, with natural warm clinician expression and pacing:\n\n${text}`;

    // Out-of-band generation — does not pollute conversation history
    _dc.send(JSON.stringify({
      type: 'response.create',
      response: {
        conversation: 'none',
        input: [],
        instructions: readInstructions,
        modalities: ['audio'],
      },
    }));
  }

  // ── Public: cancel current speech ─────────────────────────────────────────
  function cancel() {
    if (_speaking) {
      _stopAmpPoller();
      _speaking = false;
      if (_dc && _dc.readyState === 'open') {
        try { _dc.send(JSON.stringify({ type: 'response.cancel' })); } catch (_) {}
      }
      const cb = _callbacks;
      _callbacks = {};
      if (cb.onSpeechEnd) cb.onSpeechEnd();
    }
  }

  // ── Public: status check ──────────────────────────────────────────────────
  function isActive() {
    return _active && _dc && _dc.readyState === 'open';
  }

  // ── Public: tear down session ─────────────────────────────────────────────
  function close() {
    cancel();
    _active = false;
    if (_mediaStreamSrc) {
      try { _mediaStreamSrc.disconnect(); } catch (_) {}
      _mediaStreamSrc = null;
    }
    if (_analyser) {
      try { _analyser.disconnect(); } catch (_) {}
      _analyser = null;
    }
    _analyserBuf = null;
    if (_dc) {
      try { _dc.close(); } catch (_) {}
      _dc = null;
    }
    if (_pc) {
      _pc.close();
      _pc = null;
    }
    if (_audioEl) {
      _audioEl.srcObject = null;
      _audioEl = null;
    }
    // Don't close AudioContext — it's shared and can be reused
  }

  return { init, speak, cancel, isActive, close };
})();
