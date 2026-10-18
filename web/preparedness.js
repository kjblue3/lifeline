'use strict';

(() => {
  const library = window.LifeLinePreparednessLibrary;
  const $ = (id) => document.getElementById(id);
  const storageKey = 'lifeline.preparedness.v1';
  const knownIds = new Set(library.items.map((item) => item.id));
  const checked = new Set();
  const storageStatus = $('prepared-storage-status');

  try {
    const raw = localStorage.getItem(storageKey);
    if (raw !== null) {
      const saved = JSON.parse(raw);
      if (!saved || typeof saved !== 'object' || Array.isArray(saved) ||
          Object.keys(saved).length !== 2 || saved.libraryVersion !== library.version ||
          !Array.isArray(saved.checked) || saved.checked.length > knownIds.size ||
          !saved.checked.every((id) => typeof id === 'string' && knownIds.has(id)) ||
          new Set(saved.checked).size !== saved.checked.length) {
        throw new Error('Invalid saved progress');
      }
      saved.checked.forEach((id) => checked.add(id));
      storageStatus.textContent = 'Saved checkmarks restored from this browser. Planning choices were not saved.';
    }
  } catch {
    storageStatus.textContent = 'Saved progress could not be read or validated. Nothing was restored. New changes are not saved until Save progress succeeds.';
  }

  function updateCount() {
    const essentials = library.items.filter((item) => !item.activitySpecific);
    const extras = library.items.filter((item) => item.activitySpecific);
    $('prepared-count').textContent = `${essentials.filter((item) => checked.has(item.id)).length} of ${essentials.length} essentials packed`;
    $('prepared-extra-count').textContent = `${extras.filter((item) => checked.has(item.id)).length} of ${extras.length} optional extras packed`;
  }

  for (const item of library.items) {
    const row = document.createElement('li');
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.id = `prepared-item-${item.id}`;
    input.checked = checked.has(item.id);
    input.setAttribute('aria-describedby', `prepared-reason-${item.id}`);
    const title = document.createElement('span');
    title.textContent = item.title;
    label.append(input, title);
    const rationale = document.createElement('p');
    rationale.id = `prepared-reason-${item.id}`;
    rationale.textContent = item.rationale;
    input.addEventListener('change', () => {
      if (input.checked) checked.add(item.id); else checked.delete(item.id);
      updateCount();
      storageStatus.textContent = 'Checkmarks changed in memory. Choose Save progress to update saved progress.';
    });
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'What to pack';
    const supplies = document.createElement('ul');
    supplies.className = 'prepared-supplies';
    for (const supply of library.supplies[item.id] || []) {
      const entry = document.createElement('li');
      entry.textContent = supply;
      supplies.append(entry);
    }
    details.append(summary, supplies, rationale);
    if (item.id === 'first-aid') {
      const note = document.createElement('p');
      note.textContent = 'Basic supply examples, not a complete kit or treatment instructions. Check expiry dates. Suturing equipment and medication recommendations are not included.';
      const link = document.createElement('a');
      link.textContent = 'Source: American Red Cross';
      link.href = library.firstAidSource.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.referrerPolicy = 'no-referrer';
      details.append(note, link);
    }
    row.append(label, details);
    $(item.activitySpecific ? 'prepared-extra-items' : 'prepared-items').append(row);
  }
  updateCount();

  const source = library.source;
  $('prepared-source').tabIndex = -1;
  $('prepared-source-detail').textContent = `${source.publisher}: ${source.title}. Last updated ${source.updated}. Accessed ${source.accessed}.`;
  $('prepared-source-url').textContent = source.url;
  const sourceLink = document.createElement('a');
  sourceLink.href = source.url;
  sourceLink.target = '_blank';
  sourceLink.rel = 'noopener noreferrer';
  sourceLink.referrerPolicy = 'no-referrer';
  sourceLink.textContent = 'Source: National Park Service';
  $('prepared-source-link').append(sourceLink);

  $('prepared-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const message = $('prepared-message').value.trim();
    if (!message) { $('prepared-message').focus(); return; }
    const article = document.createElement('article');
    article.className = 'message user';
    const label = document.createElement('div');
    label.className = 'message-label';
    label.textContent = 'YOUR TRIP NOTE';
    const text = document.createElement('p');
    text.textContent = message;
    article.append(label, text);
    $('prepared-messages').append(article);
    $('prepared-message').value = '';
    $('prepared-ai-note').textContent = 'Trip details kept for this session. AI checklist personalization is not connected yet; these details have not changed your supplies.';
    $('prepared-summary').textContent = 'General outdoor essentials. Trip-specific AI recommendations are not available yet.';
    article.scrollIntoView({ block: 'nearest' });
    $('prepared-message').focus({ preventScroll: true });
  });
  $('prepared-message').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $('prepared-form').requestSubmit();
    }
  });

  $('prepared-save').addEventListener('click', () => {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ libraryVersion: library.version, checked: [...checked] }));
      storageStatus.textContent = 'Progress saved on this browser. Only checked item IDs and library version were saved; checkmarks will restore on reload.';
    } catch {
      storageStatus.textContent = 'Progress not saved. Browser storage is unavailable or full. Your current checkmarks remain in memory; any earlier saved progress may remain.';
    }
  });

  $('prepared-clear').addEventListener('click', () => {
    if (!window.confirm('Remove saved preparedness progress from this browser? Current on-screen checkmarks will remain until you change them or reload.')) return;
    try {
      localStorage.removeItem(storageKey);
      storageStatus.textContent = 'Saved preparedness progress removed. Current checkmarks remain in memory and are not saved.';
    } catch {
      storageStatus.textContent = 'Could not remove saved progress. Browser storage is unavailable; saved progress may still remain.';
    }
  });
})();
