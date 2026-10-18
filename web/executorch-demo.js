'use strict';

(() => {
  const screen = document.getElementById('screen-chat');
  if (!screen || document.getElementById('et-demo')) return;

  const panel = document.createElement('section');
  panel.id = 'et-demo';
  panel.className = 'content-card et-demo';

  panel.innerHTML = `
    <p class="et-eyebrow">ON-DEVICE AI DEMONSTRATION</p>
    <h2>ExecuTorch Emergency Classification</h2>
    <p>Classify an emergency report using a real ExecuTorch model running locally on this device.</p>

    <form id="et-form">
      <label for="et-text">Emergency report</label>
      <textarea id="et-text" rows="3" minlength="3" maxlength="2000" required>Our campsite caught fire and we need help</textarea>
      <button id="et-run" class="primary-button" type="submit">Analyze with ExecuTorch</button>
    </form>

    <p id="et-status" role="status" aria-live="polite"></p>

    <div id="et-results" class="et-results" hidden>
      <h3>Local analysis result</h3>
      <dl class="et-grid">
        <div><dt>Report category (rules)</dt><dd id="et-category"></dd></div>
        <div><dt>Urgency (safety rules)</dt><dd id="et-urgency"></dd></div>
        <div><dt>AI category prediction</dt><dd id="et-prediction"></dd></div>
        <div><dt>Inference engine</dt><dd id="et-engine"></dd></div>
      </dl>
    </div>

    <p class="et-disclaimer">Experimental category classifier, not medical triage.
    Reports are stored locally for this demo. No emergency responders are contacted.
    ExecuTorch runs on CPU; NPU acceleration has not been verified.</p>
  `;

  screen.appendChild(panel);

  const $ = (id) => document.getElementById(id);
  const form = $('et-form');
  const button = $('et-run');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const text = $('et-text').value.trim();
    if (text.length < 3) return;

    button.disabled = true;
    $('et-results').hidden = true;
    $('et-status').textContent = 'Running local classification...';

    try {
      const response = await fetch('/reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
        cache: 'no-store'
      });

      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }

      const report = await response.json();

      $('et-category').textContent = report.category ?? 'Unknown';
      $('et-urgency').textContent = report.urgency ?? 'Unknown';
      $('et-prediction').textContent =
        report.model_category ?? 'Unavailable (rules fallback)';
      $('et-engine').textContent = report.engine ?? 'Unknown';

      $('et-results').hidden = false;
      $('et-status').textContent =
        report.model_category && String(report.engine).includes('executorch')
          ? 'ExecuTorch inference completed. Report saved locally.'
          : 'Rules fallback used. ExecuTorch inference not confirmed.';
    } catch (error) {
      $('et-status').textContent =
        'Classification failed: ' + error.message;
    } finally {
      button.disabled = false;
    }
  });
})();
