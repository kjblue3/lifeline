'use strict';

window.LifeLineLibrary = (() => {
  const $ = (id) => document.getElementById(id);
  let records = [];
  let category = '';
  let status = null;
  let lastCard = null;
  const text = (value) => typeof value === 'string' && value.trim().length > 0;

  function node(tag, value, className) {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    return element;
  }

  function renderStatus() {
    const refs = status?.references;
    $('library-status').textContent = refs?.installed === false
      ? 'First-aid library is not installed yet'
      : refs?.installed === true && Number.isInteger(refs.count) && refs.count >= 0
        ? `${refs.count} indexed topics reported. ${records.length ? 'Completed articles are supplied separately below.' : 'Library browsing is not connected yet.'} Indexed topics are not completed articles.`
        : 'First-aid library status is unknown.';
  }

  function metadata(parent, record) {
    parent.append(node('p', `Source: ${record.source.title} | ${record.source.organisation}`, 'muted'));
    const link = node('a', 'Open original source (requires a connection)');
    link.href = record.source.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.referrerPolicy = 'no-referrer';
    parent.append(link);
    for (const key of ['published', 'updated', 'reviewed']) {
      if (record[key]) parent.append(node('p', `${key[0].toUpperCase() + key.slice(1)}: ${record[key]}`, 'muted'));
    }
    for (const warning of record.warnings) parent.append(node('p', warning, 'feature-notice'));
  }

  function render() {
    const query = $('library-search').value.trim().toLowerCase();
    const matches = records.filter((record) => (!category || record.category === category) &&
      [record.title, record.content, record.category, record.source.title, record.source.organisation].join(' ').toLowerCase().includes(query));
    $('library-cards').replaceChildren();
    $('library-empty').hidden = matches.length > 0;
    $('library-empty').textContent = records.length ? 'No matching medical information found' : 'No completed first-aid articles are available on this device.';
    for (const record of matches) {
      const card = node('article', '', 'content-card library-card');
      card.append(node('h2', record.title));
      if (record.category) card.append(node('p', record.category, 'muted'));
      metadata(card, record);
      const open = node('button', 'Read article', 'primary-button');
      open.type = 'button';
      open.setAttribute('aria-label', `Read article: ${record.title}`);
      open.addEventListener('click', () => {
        lastCard = open;
        const article = $('library-article');
        article.replaceChildren(node('h2', record.title), node('p', record.content, 'library-body'));
        metadata(article, record);
        article.append(node('p', 'For immediate danger, contact emergency services. This library does not replace professional medical care.', 'feature-notice'));
        $('library-browse').hidden = true;
        $('library-detail').hidden = false;
        article.focus();
      });
      card.append(open);
      $('library-cards').append(card);
    }
  }

  // Only completed, verified, locally readable articles cross this integration boundary.
  // Schema: title/content/category, source:{title,organisation,url}, warnings:string[],
  // optional published/updated/reviewed strings; all three availability flags must be true.
  function setRecords(input) {
    records = [];
    for (const value of Array.isArray(input) ? input : []) {
      if (value?.completed !== true || value.verified !== true || value.locally_available !== true ||
          !text(value.title) || !text(value.content) || !text(value.source?.title) ||
          !text(value.source?.organisation) || !text(value.source?.url)) continue;
      let url;
      try { url = new URL(value.source.url); } catch { continue; }
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) continue;
      const record = {
        title: value.title.trim(), content: value.content.trim(), category: text(value.category) ? value.category.trim() : '',
        source: { title: value.source.title.trim(), organisation: value.source.organisation.trim(), url: url.href },
        warnings: Array.isArray(value.warnings) ? value.warnings.filter(text) : []
      };
      for (const key of ['published', 'updated', 'reviewed']) if (text(value[key])) record[key] = value[key].trim();
      records.push(record);
    }
    category = '';
    $('library-search').value = '';
    $('library-search').disabled = !records.length;
    $('library-browse').hidden = false;
    $('library-detail').hidden = true;
    $('library-article').replaceChildren();
    $('library-categories').replaceChildren();
    if (records.length) {
      for (const name of ['', ...new Set(records.map((record) => record.category).filter(Boolean))]) {
        const button = node('button', name || 'All articles', 'library-category');
        button.type = 'button';
        button.setAttribute('aria-pressed', String(name === category));
        button.addEventListener('click', () => {
          category = name;
          for (const sibling of $('library-categories').children) sibling.setAttribute('aria-pressed', String(sibling === button));
          render();
        });
        $('library-categories').append(button);
      }
    }
    renderStatus();
    render();
    return records.length;
  }

  $('library-search').addEventListener('input', render);
  $('library-back').addEventListener('click', () => {
    $('library-detail').hidden = true;
    $('library-browse').hidden = false;
    if (lastCard?.isConnected) lastCard.focus();
    else $('library-search').focus();
  });
  setRecords([]);
  return Object.freeze({ setRecords, updateStatus(data) { status = data; renderStatus(); } });
})();
