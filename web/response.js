'use strict';

window.LifeLineResponse = Object.freeze({
  // Future structured guidance must explicitly link each instruction to verified,
  // locally available references. Never derive treatment steps from answer text.
  renderGuidance(parent, data) {
    const sources = new Map((Array.isArray(data.sources) ? data.sources : [])
      .filter((source) => source && typeof source.id === 'string' &&
        source.verified === true && source.locally_available === true)
      .map((source) => [source.id, source]));
    const supported = (item) => item?.verified === true &&
      Array.isArray(item.source_ids) && item.source_ids.length > 0 &&
      item.source_ids.every((id) => sources.has(id));
    const warnings = (Array.isArray(data.warnings) ? data.warnings : [])
      .filter((item) => supported(item) && typeof item.text === 'string' && item.text.trim());
    if (warnings.length) {
      const section = document.createElement('section');
      section.className = 'response-warnings';
      const title = document.createElement('h3');
      title.textContent = 'When to get emergency help';
      section.append(title);
      for (const warning of warnings) {
        const paragraph = document.createElement('p');
        paragraph.textContent = warning.text;
        section.append(paragraph);
      }
      parent.append(section);
    }
    const steps = (Array.isArray(data.steps) ? data.steps : [])
      .filter((item) => supported(item) && Number.isInteger(item.number) && item.number > 0 &&
        typeof item.instruction === 'string' && item.instruction.trim());
    if (!steps.length) return;
    const section = document.createElement('section');
    section.className = 'response-steps';
    const title = document.createElement('h3');
    title.textContent = 'What to do now';
    section.append(title);
    steps.forEach((step, index) => {
      const detail = document.createElement('details');
      detail.open = index === 0;
      const summary = document.createElement('summary');
      summary.textContent = `Step ${step.number}`;
      const instruction = document.createElement('p');
      instruction.textContent = step.instruction;
      detail.append(summary, instruction);
      section.append(detail);
    });
    parent.append(section);
  }
});
