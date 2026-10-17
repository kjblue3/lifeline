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
    $('prepared-count').textContent = `${checked.size} of ${library.items.length} packed`;
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
    title.textContent = item.title + (item.activitySpecific ? ' (activity-specific)' : '');
    label.append(input, title);
    const rationale = document.createElement('p');
    rationale.id = `prepared-reason-${item.id}`;
    rationale.textContent = item.rationale;
    const source = document.createElement('button');
    source.type = 'button';
    source.className = 'text-button';
    source.textContent = 'Source: NPS Ten Essentials';
    source.setAttribute('aria-label', `Source for ${item.title}: NPS Ten Essentials`);
    // Avoid changing the screen hash when opening local source notes.
    source.addEventListener('click', () => {
      $('prepared-source').scrollIntoView({ block: 'start' });
      $('prepared-source').focus({ preventScroll: true });
    });
    input.addEventListener('change', () => {
      if (input.checked) checked.add(item.id); else checked.delete(item.id);
      updateCount();
      storageStatus.textContent = 'Checkmarks changed in memory. Choose Save progress to update saved progress.';
    });
    row.append(label, rationale, source);
    $('prepared-items').append(row);
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
  sourceLink.textContent = 'Read the original NPS article (requires internet)';
  $('prepared-source-link').append(sourceLink);

  $('prepared-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const days = Number($('prepared-days').value);
    if (!Number.isInteger(days) || days < 1 || days > 365) return;
    const environment = document.querySelector('#prepared-form input[name="environment"]:checked')?.value || 'Not selected';
    const description = $('prepared-description').value.trim();
    const activity = $('prepared-activity').value.trim() || 'Not specified';
    $('prepared-summary').textContent = `Environment: ${environment}${description ? ` (${description})` : ''}. Activity: ${activity}. Duration: ${days} ${days === 1 ? 'day' : 'days'}. Context only; the complete baseline checklist is unchanged. Choices are not saved.`;
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
