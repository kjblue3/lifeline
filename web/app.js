'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const api = window.LifeLineAPI;
  const question = $('question');
  let canAsk = false;
  let sending = false;
  let checking = false;
  let requestRevision = 0;
  let lastQuestion = '';
  let profile = null;
  const profileFields = ['name', 'age', 'allergies', 'medications', 'conditions', 'contact'];

  function updateControls() {
    $('send-button').disabled = sending || window.LifeLineVoice.active || !canAsk || !question.value.trim();
    $('retry-question').disabled = sending || !canAsk;
    $('clear-chat').disabled = sending;
    question.readOnly = sending;
    document.querySelectorAll('[data-question]').forEach((button) => { button.disabled = sending; });
    $('chat-form').setAttribute('aria-busy', String(sending));
    $('send-button').setAttribute('aria-label', sending ? 'Waiting for a response' : 'Send question');
  }

  function setAIStatus(allowed, label, detail) {
    canAsk = allowed;
    $('connection-label').textContent = label;
    $('availability-detail').textContent = detail;
    updateControls();
  }

  function applyStatus(data) {
    if (!['local', 'unavailable'].includes(data.mode) ||
        typeof data.local?.configured !== 'boolean' || typeof data.local?.ready !== 'boolean' ||
        typeof data.references?.installed !== 'boolean' || !Number.isInteger(data.references?.count) ||
        data.references.count < 0 || typeof data.offline_ready !== 'boolean') {
      throw new Error('Invalid status response');
    }
    $('local-state').textContent = data.local.ready ? 'Ready' : 'Not ready';
    const library = data.references.installed ? `Available · ${data.references.count} Reference Topics` : 'Not Installed';
    $('references-state').textContent = library;
    $('library-summary').textContent = `Medical Library: ${library}`;
    $('offline-label').textContent = data.offline_ready ? 'Complete offline system ready' : 'Complete offline system not ready';
    const detail = data.local.configured && !data.local.ready
      ? 'Local model files found. Your first question loads the model on CPU and may take a few minutes.'
      : typeof data.local.message === 'string' ? data.local.message : 'No local AI status message provided.';
    // A configured model loads lazily, so readiness must not block the first ask.
    setAIStatus(true, data.local.ready ? 'Local AI Active' : 'Local AI Not Ready', detail);
    $('connection-state').dataset.ready = String(data.local.ready);
    $('model-name').textContent = typeof data.local.model === 'string' ? data.local.model : 'Not connected';
    $('status-explanation').textContent = $('availability-detail').textContent;
    window.LifeLineLibrary.updateStatus(data);
  }

  function unavailable() {
    setAIStatus(false, 'Unable to Check AI Status', 'Cannot verify backend status. Your messages and draft remain here; we will check again.');
    $('connection-state').dataset.ready = 'false';
    $('status-explanation').textContent = 'Backend status could not be verified. Internet connectivity is separate from local AI readiness.';
    for (const id of ['model-name', 'local-state', 'references-state']) $(id).textContent = 'Not verified';
    $('library-summary').textContent = 'Medical Library: Not verified';
    $('offline-label').textContent = 'Offline readiness unverified';
    window.LifeLineLibrary.updateStatus(null);
  }

  async function checkStatus() {
    if (checking) return;
    checking = true;
    $('refresh-status').disabled = true;
    try {
      const data = await window.LifeLineStatus.read();
      applyStatus(data);
    } catch {
      unavailable();
    } finally {
      checking = false;
      $('refresh-status').disabled = false;
    }
  }

  function addMessage(kind, text, data = {}) {
    const article = document.createElement('article');
    article.className = `message ${kind}`;
    const label = document.createElement('div');
    label.className = 'message-label';
    label.textContent = kind === 'user' ? 'YOU' : 'LIFELINE';
    if (kind === 'assistant') {
      const badge = document.createElement('span');
      badge.className = 'demo-badge';
      badge.textContent = 'LOCAL AI';
      label.append(badge);
    }
    const body = document.createElement('p');
    body.textContent = text;
    article.append(label);
    if (kind === 'assistant') {
      if (typeof data.heading === 'string' && data.heading.trim()) {
        const heading = document.createElement('h2');
        heading.textContent = data.heading;
        article.append(heading);
      }
      window.LifeLineResponse.renderGuidance(article, data);
    }
    article.append(body);
    // Optional structured sections remain plain text, never HTML or markdown.
    if (Array.isArray(data.sections)) {
      for (const section of data.sections) {
        if (!section || typeof section !== 'object') continue;
        if (typeof section.title === 'string') {
          const heading = document.createElement('h3');
          heading.textContent = section.title;
          article.append(heading);
        }
        const content = typeof section.content === 'string' ? section.content : section.text;
        if (typeof content === 'string') {
          const paragraph = document.createElement('p');
          paragraph.textContent = content;
          article.append(paragraph);
        }
      }
    }
    if (kind === 'assistant') {
      const note = document.createElement('p');
      note.className = 'message-notice';
      note.textContent = data.notice || 'AI-generated information. Not a doctor or an emergency service.';
      article.append(note);
      if (!Array.isArray(data.sources) || !data.sources.length) {
        const limitation = document.createElement('p');
        limitation.className = 'message-notice';
        limitation.textContent = 'No verified medical references were returned with this answer.';
        article.append(limitation);
      }
    }
    const sources = Array.isArray(data.sources) ? data.sources : [];
    const list = document.createElement('ul');
    list.className = 'source-list';
    for (const source of sources) {
      const raw = typeof source === 'string' ? source : source?.url;
      if (typeof raw !== 'string') {
        const title = source?.title || source?.name;
        if (typeof title === 'string' && title.trim()) {
          const item = document.createElement('li');
          item.textContent = title;
          list.append(item);
        }
        continue;
      }
      let url;
      try { url = new URL(raw); } catch { continue; }
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) continue;
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = url.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.referrerPolicy = 'no-referrer';
      link.textContent = typeof source.title === 'string' ? source.title : typeof source.name === 'string' ? source.name : url.href;
      item.append(link);
      list.append(item);
    }
    if (list.childElementCount) {
      const heading = document.createElement('h3');
      heading.className = 'source-heading';
      heading.textContent = 'Sources returned by the backend (not independently verified)';
      article.append(heading, list);
    }
    $('messages').append(article);
    $('conversation').hidden = false;
    $('welcome').hidden = true;
    $('starters').hidden = true;
    return article;
  }

  async function send(text, retry = false) {
    if (sending || window.LifeLineVoice.active || !canAsk || !text) return;
    sending = true;
    lastQuestion = text;
    const revision = ++requestRevision;
    const loading = $('ai-loading');
    const progress = $('ai-progress');
    const started = performance.now();
    loading.dataset.complete = 'false';
    $('ai-loading-title').textContent = 'LifeLine AI is preparing your answer...';
    $('ai-elapsed').textContent = '0 seconds elapsed';
    $('ai-progress-fill').style.width = '0%';
    progress.setAttribute('aria-valuenow', '0');
    progress.setAttribute('aria-valuetext', 'Time-based estimate, not model completion');
    loading.hidden = false;
    // Elapsed time is only a waiting estimate; reserve completion for a valid answer.
    const progressTimer = setInterval(() => {
      const seconds = Math.floor((performance.now() - started) / 1000);
      const estimate = Math.min(95, 95 * (1 - Math.exp(-seconds / 45)));
      $('ai-elapsed').textContent = `${seconds} ${seconds === 1 ? 'second' : 'seconds'} elapsed`;
      $('ai-progress-fill').style.width = `${estimate}%`;
      progress.setAttribute('aria-valuenow', String(Math.floor(estimate)));
    }, 1000);
    $('request-error').hidden = true;
    if (!retry) addMessage('user', text);
    $('request-status').textContent = 'Waiting for local AI on CPU. The first question also loads the model and may take a few minutes. For immediate danger, contact emergency services now.';
    updateControls();
    if (!$('screen-chat').hidden) loading.scrollIntoView({ block: 'nearest', behavior: 'instant' });
    try {
      const data = await api.ask(text);
        if (typeof data.answer !== 'string' || !data.answer.trim() || data.mode !== 'local' ||
            data.simulated === true || !Array.isArray(data.sources) ||
            (data.notice != null && typeof data.notice !== 'string')) throw new Error('The backend did not return a valid answer.');
      if (revision !== requestRevision) return;
      const reply = addMessage('assistant', data.answer, data);
      clearInterval(progressTimer);
      loading.dataset.complete = 'true';
      $('ai-loading-title').textContent = 'Your answer is ready.';
      $('ai-progress-fill').style.width = '100%';
      progress.setAttribute('aria-valuenow', '100');
      progress.setAttribute('aria-valuetext', 'Response received');
      question.value = '';
      $('request-status').textContent = 'Response received. Earlier questions are not sent with follow-up requests.';
      if (!$('screen-chat').hidden) reply.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      await new Promise((resolve) => setTimeout(resolve, 450));
    } catch (error) {
      if (revision !== requestRevision) return;
      $('request-status').textContent = '';
      $('error-detail').textContent = error.name === 'AbortError'
        ? 'The local AI request timed out after 3 minutes. The model may still be loading or generating. Your question is still here; wait before retrying. For immediate danger, contact emergency services now.'
        : `${error.message || 'Could not get a response.'} Your question is still here. You can retry when the service is available.`;
      $('request-error').hidden = false;
      if (error.status === 503) {
        setAIStatus(true, 'Local AI Not Ready', error.message);
        $('connection-state').dataset.ready = 'false';
      }
    } finally {
      clearInterval(progressTimer);
      if (revision === requestRevision) {
        loading.hidden = true;
        sending = false;
        updateControls();
        if (!$('screen-chat').hidden) question.focus({ preventScroll: true });
        void checkStatus();
      }
    }
  }

  $('chat-form').addEventListener('submit', (event) => {
    event.preventDefault();
    void send(question.value.trim());
  });
  question.addEventListener('input', updateControls);
  question.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $('chat-form').requestSubmit();
    }
  });
  $('retry-question').addEventListener('click', () => {
    question.value = lastQuestion;
    void send(lastQuestion, true);
  });
  document.querySelectorAll('[data-question]').forEach((button) => {
    button.addEventListener('click', () => {
      question.value = button.dataset.question;
      updateControls();
      question.focus();
    });
  });
  $('clear-chat').addEventListener('click', () => {
    if (sending) return;
    if (($('messages').childElementCount || question.value.trim()) && !window.confirm('Start a new chat? This clears the visible conversation and your draft.')) return;
    $('messages').replaceChildren();
    $('conversation').hidden = true;
    $('welcome').hidden = false;
    $('starters').hidden = false;
    $('request-error').hidden = true;
    $('request-status').textContent = '';
    question.value = '';
    lastQuestion = '';
    updateControls();
    question.focus();
  });

  function showScreen() {
    const name = ['chat', 'library', 'prepared', 'profile'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'chat';
    for (const screen of ['chat', 'library', 'prepared', 'profile']) $(`screen-${screen}`).hidden = screen !== name;
    document.querySelectorAll('[data-screen]').forEach((link) => {
      const active = link.dataset.screen === name;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    });
    $('page-label').hidden = name === 'chat';
    $('page-label').textContent = name === 'chat' ? '' : name === 'prepared' ? 'MAKE ROOM FOR PREPARATION' : name === 'library' ? 'FIRST-AID LIBRARY' : 'YOUR OPTIONAL DEMO PROFILE';
    document.title = `LifeLine | ${name === 'chat' ? 'Chat' : name === 'prepared' ? 'Get Prepared' : name === 'library' ? 'First-Aid Library' : 'Medical Profile'}`;
  }
  window.addEventListener('hashchange', () => { showScreen(); $('main').focus({ preventScroll: true }); });
  $('prepared-shortcut').addEventListener('click', () => { location.hash = 'prepared'; });
  $('sidebar-toggle').addEventListener('click', () => {
    const collapsed = $('app-shell').classList.toggle('collapsed');
    $('sidebar-toggle').setAttribute('aria-expanded', String(!collapsed));
    $('sidebar-toggle').setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
    document.querySelectorAll('[data-screen]').forEach((link) => {
      if (collapsed) link.setAttribute('aria-label', link.textContent.trim()); else link.removeAttribute('aria-label');
    });
  });

  function setProfileEditing(editing) {
    for (const field of profileFields) $(`profile-${field}`).readOnly = !editing;
    $('profile-save').hidden = !editing;
    $('profile-edit').hidden = editing;
  }
  $('profile-form').addEventListener('submit', (event) => {
    event.preventDefault();
    profile = Object.fromEntries(profileFields.map((field) => [field, $(`profile-${field}`).value.trim()]));
    if (!Object.values(profile).some(Boolean)) {
      profile = null;
      $('profile-summary').textContent = 'No profile kept. Add fictional details if you want to try the demo.';
      return;
    }
    setProfileEditing(false);
    $('profile-summary').textContent = 'Fictional profile kept in this page\'s memory only. Never uploaded or used in answers. Reloading clears it.';
  });
  $('profile-edit').addEventListener('click', () => { setProfileEditing(true); $('profile-name').focus(); });
  $('profile-clear').addEventListener('click', () => {
    profile = null;
    $('profile-form').reset();
    setProfileEditing(true);
    $('profile-summary').textContent = 'Profile removed. No profile is stored or uploaded.';
  });

  for (const name of ['emergency', 'status']) {
    $(`${name}-open`).addEventListener('click', () => $(`${name}-dialog`).showModal());
    $(`${name}-close`).addEventListener('click', () => $(`${name}-dialog`).close());
  }
  $('refresh-status').addEventListener('click', checkStatus);
  $('emergency-library').addEventListener('click', () => {
    $('emergency-dialog').close();
    location.hash = 'library';
  });
  window.addEventListener('lifeline:voice-state', updateControls);

  const accountDialog = $('account-dialog');
  let signingUp = false;
  function setAccountMode(signUp) {
    signingUp = signUp;
    $('account-form').reset();
    $('account-feedback').textContent = '';
    $('account-title').textContent = signUp ? 'Sign Up' : 'Sign In';
    $('account-name-field').hidden = !signUp;
    $('account-submit').textContent = signUp ? 'Preview Sign Up' : 'Preview Sign In';
    $('account-switch').textContent = signUp ? 'Try Sign In instead' : 'Try Sign Up instead';
  }
  for (const [id, signUp] of [['sign-in-open', false], ['sign-up-open', true]]) {
    $(id).addEventListener('click', () => {
      setAccountMode(signUp);
      accountDialog.showModal();
    });
  }
  $('account-switch').addEventListener('click', () => {
    setAccountMode(!signingUp);
    $('account-email').focus();
  });
  $('account-close').addEventListener('click', () => accountDialog.close());
  accountDialog.addEventListener('close', () => {
    $('account-form').reset();
    $('account-feedback').textContent = '';
  });
  $('account-form').addEventListener('submit', (event) => {
    event.preventDefault();
    $('account-form').reset();
    $('account-feedback').textContent = 'Demo preview complete. You are not signed in and no account was created. All entered details have been cleared. Continue using LifeLine without an account.';
  });

  window.LifeLineStatus.subscribe(applyStatus, unavailable);
  showScreen();
  updateControls();
})();
