'use strict';

window.LifeLineVoice = (() => {
  const $ = (id) => document.getElementById(id);
  const dialog = $('voice-dialog');
  const question = $('question');
  let adapter = null;
  let stream = null;
  let recorder = null;
  let timer;
  let revision = 0;
  let phase = 'idle';
  let transcript = '';
  const available = () => adapter?.localOnly === true && adapter.ready === true &&
    typeof adapter.transcribe === 'function' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';
  const busy = () => question.readOnly || question.disabled;

  function update(message) {
    $('voice-status').textContent = message;
    dialog.dataset.listening = String(phase === 'recording');
    $('voice-start').disabled = !available() || busy() || phase !== 'idle';
    $('voice-stop').hidden = phase !== 'recording';
    $('voice-cancel').hidden = phase === 'idle';
    $('voice-review').hidden = !transcript;
    $('voice-transcript').textContent = transcript;
    $('voice-insert').disabled = busy() || !transcript;
    window.dispatchEvent(new CustomEvent('lifeline:voice-state', { detail: {
      active: phase !== 'idle', recording: phase === 'recording', phase
    } }));
  }

  function stopTracks() {
    clearTimeout(timer);
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }

  function cancel() {
    revision++;
    if (recorder) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.onerror = null;
      if (recorder.state !== 'inactive') recorder.stop();
      recorder = null;
    }
    stopTracks();
    transcript = '';
    phase = 'idle';
    update(available() ? 'Ready for local voice input. Start recording when you are ready.' : 'Offline voice input is not ready yet.');
  }

  function stop() {
    if (phase !== 'recording' || !recorder) return;
    phase = 'transcribing';
    recorder.stop();
    stopTracks();
    update('Preparing a transcript locally. Review it before inserting.');
  }

  async function start() {
    if (!available() || busy() || phase !== 'idle' || !dialog.open) return;
    const current = ++revision;
    const localAdapter = adapter;
    phase = 'permission';
    transcript = '';
    update('Waiting for microphone permission.');
    try {
      const granted = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (current !== revision || !dialog.open || busy()) {
        granted.getTracks().forEach((track) => track.stop());
        if (current === revision) cancel();
        return;
      }
      stream = granted;
      $('voice-permission').textContent = 'Microphone permission granted. Recording is limited to 60 seconds.';
      const capture = new MediaRecorder(stream);
      recorder = capture;
      let chunks = [];
      capture.ondataavailable = (event) => { if (current === revision && event.data.size) chunks.push(event.data); };
      capture.onerror = () => { if (current === revision) { cancel(); update('Recording is unavailable. You can still type your question.'); } };
      capture.onstop = async () => {
        if (current !== revision) { chunks = []; return; }
        recorder = null;
        stopTracks();
        let blob = new Blob(chunks, { type: capture.mimeType });
        chunks = [];
        try {
          if (!blob.size) throw new Error('Empty recording');
          const result = await localAdapter.transcribe(blob);
          if (current !== revision || !dialog.open) return;
          if (typeof result?.text !== 'string' || !result.text.trim()) throw new Error('Empty transcript');
          // Never overwrite a draft or insert automatically, including during an AI request.
          transcript = result.text.trim();
          phase = 'idle';
          update(busy() ? 'Transcript ready. Wait for the current answer before inserting.' : 'Review the transcript, then choose Insert into chat.');
        } catch {
          if (current === revision) { phase = 'idle'; update('Local transcription is unavailable. You can still type your question.'); }
        } finally { blob = null; }
      };
      capture.start();
      phase = 'recording';
      update('Listening. Stop recording when you are finished.');
      timer = setTimeout(stop, 60000);
    } catch (error) {
      if (current !== revision) return;
      cancel();
      const message = error.name === 'NotAllowedError' || error.name === 'SecurityError'
        ? 'Microphone access is disabled. You can still type your question'
        : 'Microphone recording is unavailable. You can still type your question.';
      $('voice-permission').textContent = message;
      update(message);
    }
  }

  $('voice-open').addEventListener('click', () => {
    cancel();
    $('voice-permission').textContent = 'Microphone access has not been requested. You can still type your question.';
    dialog.showModal();
  });
  $('voice-close').addEventListener('click', () => { cancel(); dialog.close(); });
  dialog.addEventListener('cancel', cancel);
  dialog.addEventListener('close', cancel);
  $('voice-start').addEventListener('click', start);
  $('voice-stop').addEventListener('click', stop);
  $('voice-cancel').addEventListener('click', cancel);
  $('voice-insert').addEventListener('click', () => {
    if (busy() || !transcript || phase !== 'idle') return;
    const next = [question.value, transcript].filter(Boolean).join('\n');
    if (question.maxLength >= 0 && next.length > question.maxLength) {
      update('The transcript and draft exceed the question length limit. Shorten your draft before inserting.');
      return;
    }
    question.value = next;
    question.dispatchEvent(new Event('input', { bubbles: true }));
    cancel();
    dialog.close();
    question.focus();
  });
  // Guard form submission independently of parent control updates.
  $('chat-form').addEventListener('submit', (event) => {
    if (phase !== 'idle') { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  new MutationObserver(() => {
    if (busy() && ['permission', 'recording'].includes(phase)) cancel();
    $('voice-start').disabled = !available() || busy() || phase !== 'idle';
    $('voice-insert').disabled = busy() || !transcript;
  }).observe(question, { attributes: true, attributeFilter: ['readonly', 'disabled'] });
  window.addEventListener('hashchange', () => { cancel(); if (dialog.open) dialog.close(); });
  window.addEventListener('pagehide', () => { cancel(); if (dialog.open) dialog.close(); });
  cancel();
  return Object.freeze({
    // Configure only after a genuine local engine is confirmed. No default engine or network fallback.
    configure(value) {
      cancel();
      adapter = value?.localOnly === true && value.ready === true && typeof value.transcribe === 'function' ? value : null;
      cancel();
      return available();
    },
    cancel,
    get active() { return phase !== 'idle'; }
  });
})();
