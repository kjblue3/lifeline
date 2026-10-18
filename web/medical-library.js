'use strict';

window.LifeLineLibrary = (() => {
  const $ = (id) => document.getElementById(id);
  let records = [];
  let dataset = {};
  let category = '';
  let letter = '';
  let lastCard = null;
  const categories = {
    Injuries: ['Bleeding', 'Burns', 'Sprains and Strains', 'Wounds and Injuries'],
    Outdoor: ['Heat Illness', 'Hypothermia', 'Frostbite'],
    Illnesses: ['Dehydration'],
    'Medical Emergencies': ['Poisoning', 'Choking']
  };

  function node(tag, value, className) {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    return element;
  }

  function render() {
    const query = $('library-search').value.trim().toLowerCase();
    const matches = records.filter((record) => (!category || record.category === category) &&
      (!letter || record.title.toUpperCase().startsWith(letter)) &&
      [record.title, record.summary, record.category].join(' ').toLowerCase().includes(query));
    $('library-cards').replaceChildren();
    $('library-results').textContent = `${matches.length} of ${records.length} summaries`;
    $('library-empty').hidden = matches.length > 0;
    $('library-empty').textContent = 'No matching medical information found.';
    for (const record of matches) {
      const card = node('article', '', 'content-card library-card');
      const heading = node('h2', '');
      const open = node('button', record.title, 'library-title-button');
      open.type = 'button';
      open.addEventListener('click', () => {
        lastCard = open;
        const article = $('library-article');
        article.replaceChildren(node('h2', record.title),
          node('p', 'Official medical information summary, not a complete first-aid protocol.', 'muted'),
          node('p', record.summary, 'library-body'),
          node('p', 'Source: MedlinePlus / U.S. National Library of Medicine', 'muted'));
        const link = node('a', 'Open original MedlinePlus source (requires a connection)');
        link.href = record.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.referrerPolicy = 'no-referrer';
        article.append(link);
        const provenance = node('details', '', 'library-provenance');
        provenance.append(node('summary', 'Source and import provenance'));
        for (const [label, value] of [
          ['MedlinePlus topic ID', record.medlineplus_id],
          ['Source topic creation date (not a clinical review date)', record.date_created],
          ['Source feed date', dataset.feed_date],
          ['Import timestamp', dataset.imported_at],
          ['Snapshot SHA-256', dataset.snapshot_sha256]
        ]) {
          if (value) provenance.append(node('p', `${label}: ${value}`, 'muted'));
        }
        provenance.append(node('p', 'Source-extracted summary. Feed and import dates do not indicate clinical review. Contributor credits in the source summary are retained.', 'muted'));
        article.append(provenance);
        $('library-browse').hidden = true;
        $('library-detail').hidden = false;
        article.focus();
      });
      heading.append(open);
      card.append(heading, node('p', record.category, 'muted'));
      $('library-cards').append(card);
    }
  }

  function filters(id, names, select) {
    $(id).replaceChildren();
    for (const name of ['', ...names]) {
      const button = node('button', name || 'All', 'library-category');
      button.type = 'button';
      button.setAttribute('aria-pressed', String(!name));
      button.addEventListener('click', () => {
        select(name);
        for (const sibling of $(id).children) sibling.setAttribute('aria-pressed', String(sibling === button));
        render();
      });
      $(id).append(button);
    }
  }

  async function reload() {
    $('library-status').textContent = 'Loading local medical information summaries...';
    $('library-search').disabled = true;
    $('library-categories').replaceChildren();
    $('library-alphabet').replaceChildren();
    $('library-cards').replaceChildren();
    $('library-results').textContent = '';
    $('library-empty').hidden = true;
    $('library-browse').hidden = false;
    $('library-detail').hidden = true;
    try {
      const response = await fetch('/assets/official_first_aid.json', { mode: 'same-origin', credentials: 'same-origin', redirect: 'error' });
      if (!response.ok) throw new Error('Unable to load bundled summaries');
      const data = await response.json();
      if (!Array.isArray(data.topics) || !data.topics.length || data.topics.some((record) => {
        if (!record || typeof record.title !== 'string' || !record.title.trim() ||
            typeof record.summary !== 'string' || !record.summary.trim() || record.content_status !== 'official_summary') return true;
        try {
          const url = new URL(record.url);
          return url.protocol !== 'https:' || url.hostname !== 'medlineplus.gov' || !!url.username || !!url.password;
        } catch { return true; }
      })) throw new Error('Invalid bundled summary JSON');
      dataset = data;
      records = data.topics.map((record) => ({ ...record,
        category: Object.keys(categories).find((name) => categories[name].includes(record.title)) || ''
      })).sort((a, b) => a.title.localeCompare(b.title, 'en'));
      category = '';
      letter = '';
      filters('library-categories', Object.keys(categories).filter((name) => records.some((record) => record.category === name)), (name) => { category = name; });
      filters('library-alphabet', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split(''), (name) => { letter = name; });
      $('library-search').disabled = false;
      $('library-status').textContent = `${records.length} medical information summaries loaded locally.`;
      render();
    } catch {
      records = [];
      $('library-status').textContent = 'Library loading failed: the bundled summary JSON is unavailable or invalid. Reload the page to try again.';
      $('library-empty').hidden = false;
      $('library-empty').textContent = 'Medical information summaries could not be loaded.';
    }
  }

  $('library-search').addEventListener('input', render);
  $('library-back').addEventListener('click', () => {
    $('library-detail').hidden = true;
    $('library-browse').hidden = false;
    if (lastCard?.isConnected) lastCard.focus();
    else $('library-search').focus();
  });
  reload();
  return Object.freeze({ reload });
})();
