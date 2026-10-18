'use strict';

(() => {
  const input = document.getElementById('chat-file');
  const preview = document.getElementById('attachment-preview');
  const status = document.getElementById('attachment-status');
  function clear() {
    input.value = '';
    preview.hidden = true;
    document.getElementById('attachment-name').textContent = '';
    status.textContent = '';
  }
  const open = document.getElementById('attachment-open');
  // Place the control beside the input without changing the chat submit payload.
  document.querySelector('#chat-form .composer').insertBefore(open, document.getElementById('voice-open'));
  open.addEventListener('click', () => input.click());
  input.addEventListener('change', () => {
    const file = input.files[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      clear();
      status.textContent = 'Choose a file smaller than 10 MB. File analysis is not connected yet.';
      return;
    }
    document.getElementById('attachment-name').textContent = `${file.name} (${Math.max(1, Math.ceil(file.size / 1024))} KB)`;
    preview.hidden = false;
    status.textContent = 'File selected for local preview only. AI file analysis is not connected.';
  });
  document.getElementById('attachment-remove').addEventListener('click', () => { clear(); open.focus(); });
  window.addEventListener('lifeline:new-chat', clear);
  window.addEventListener('pagehide', clear);
})();
