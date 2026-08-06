/**
 * SecondSelf — Ask / Chat Interface (Step 4.3)
 *
 * Public API (used by graph.js and the DOM):
 *   setupAskBar()            → wire ask form + keyboard shortcuts
 *   askBrain(question)       → POST /api/ask, render answer + source chips
 *   highlightSourceNodes(ids)→ glow source nodes in vis-network + focus view
 *   setupCaptureModal()      → wire the Capture Note button → modal
 */

'use strict';

// ── Module state ───────────────────────────────────────────────────────────
let _isAsking    = false;  // debounce guard for ask requests
let _isCapturing = false;  // debounce guard for capture requests

// Snapshot of original node colours — restored when highlight is cleared.
// shape: { [nodeId]: { color, shadow } }
let _originalNodeColors = {};

// ═══════════════════════════════════════════════════════════════════════════
//  1. SETUP
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Wire the ask form (submit + Enter key) and keyboard shortcuts.
 * Called once on DOMContentLoaded.
 */
function setupAskBar() {
  const form    = document.getElementById('ask-form');
  const input   = document.getElementById('ask-input');
  const display = document.getElementById('answer-display');

  if (!form || !input) return;

  // Submit on Enter / button click
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question || _isAsking) return;

    await askBrain(question);
    input.value = '';
  });

  // Global keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // "/" — focus ask input from anywhere on the page
    if (e.key === '/' && document.activeElement !== input) {
      e.preventDefault();
      input.focus();
      input.select();
    }

    // Escape — close answer panel
    if (e.key === 'Escape') {
      if (display && !display.classList.contains('hidden')) {
        hideAnswer();
      }
      // Also close capture modal if open
      const modal = document.getElementById('capture-modal');
      if (modal && !modal.classList.contains('hidden')) {
        closeCaptureModal();
      }
    }
  });

  // Click outside ask-bar → close answer panel
  document.addEventListener('click', (e) => {
    const bar = document.getElementById('ask-bar');
    if (bar && !bar.contains(e.target) && display && !display.classList.contains('hidden')) {
      hideAnswer();
    }
  });
}

// ═══════════════════════════════════════════════════════════════════════════
//  2. ASK BRAIN  (core function per spec)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Ask the RAG pipeline a question and render the answer.
 *
 * Steps (per implementation plan):
 *   1. Show loading state (pulsing dots animation)
 *   2. POST /api/ask with { question }
 *   3. Parse response
 *   4. Render answer with markdown formatting
 *   5. Render source citations as clickable links
 *      (clicking a source highlights that node in the graph)
 *   6. Show confidence badge and timing info
 *   7. Hide loading state
 *
 * @param {string} question
 */
async function askBrain(question) {
  if (_isAsking) return;
  _isAsking = true;

  const display = document.getElementById('answer-display');
  const btn     = document.getElementById('btn-ask');

  // Step 1: Show loading state
  _showLoadingState(display, btn, question);
  adjustLayout();

  try {
    // Step 2: POST /api/ask
    const res = await fetch('/api/ask', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ question }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    // Step 3: Parse response
    const data = await res.json();

    // Steps 4–6: Render answer, sources, confidence badge, timings
    _renderAnswer(display, data, question);

    // Step 5: Highlight source nodes in the graph (clicking chips also does this)
    if (data.sources && data.sources.length > 0) {
      highlightSourceNodes(data.sources.map(s => s.id));
    }

  } catch (err) {
    _renderError(display, err.message);
  } finally {
    // Step 7: Restore button state
    _isAsking = false;
    if (btn) {
      btn.textContent = 'Ask';
      btn.disabled    = false;
    }
    adjustLayout();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  3. HIGHLIGHT SOURCE NODES IN GRAPH  (core function per spec)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Highlight source nodes with a glow effect and focus the graph view.
 *
 * Steps (per implementation plan):
 *   1. Reset all node colors (restore originals)
 *   2. Highlight source nodes with glow effect
 *   3. Focus the graph view on those nodes
 *
 * @param {string[]} sourceIds  - capture IDs to highlight; empty → reset
 */
function highlightSourceNodes(sourceIds) {
  // _network is the vis.Network instance declared in graph.js
  if (typeof _network === 'undefined' || !_network) return;

  const nodesDataset = _network.body.data.nodes;
  if (!nodesDataset) return;

  // Step 1: Reset all node colors to their originals
  if (Object.keys(_originalNodeColors).length > 0) {
    const resets = Object.entries(_originalNodeColors).map(([id, saved]) => ({
      id,
      color:  saved.color,
      shadow: saved.shadow,
      size:   saved.size,
    }));
    nodesDataset.update(resets);
    _originalNodeColors = {};
  }

  if (!sourceIds || sourceIds.length === 0) {
    _network.unselectAll();
    return;
  }

  // Step 2: Apply glow highlight to source nodes
  const allNodeIds = nodesDataset.getIds();
  const sourceSet  = new Set(sourceIds);

  // Dim all non-source nodes slightly
  const dimUpdates = allNodeIds
    .filter(id => !sourceSet.has(id))
    .map(id => ({ id, color: { opacity: 0.25 } }));

  if (dimUpdates.length > 0) {
    nodesDataset.update(dimUpdates);
  }

  // Glow highlight for source nodes
  const glowUpdates = sourceIds.map(id => {
    // Save original before modifying
    const node = nodesDataset.get(id);
    if (node) {
      _originalNodeColors[id] = {
        color:  node.color,
        shadow: node.shadow,
        size:   node.size,
      };
    }

    return {
      id,
      color: {
        background: '#a78bfa',           // bright violet
        border:     '#c4b5fd',
        highlight:  { background: '#c4b5fd', border: '#ddd6fe' },
      },
      shadow: {
        enabled: true,
        color:   'rgba(167, 139, 250, 0.8)',  // violet glow
        size:    25,
        x: 0,
        y: 0,
      },
      size: (node && node.size ? node.size * 1.3 : 25),
    };
  });

  nodesDataset.update(glowUpdates);
  _network.selectNodes(sourceIds, false);

  // Step 3: Focus the graph view on the source nodes
  if (sourceIds.length === 1) {
    _network.focus(sourceIds[0], {
      scale:     1.3,
      animation: { duration: 600, easingFunction: 'easeInOutQuad' },
    });
  } else if (sourceIds.length > 1) {
    _network.fit({
      nodes:     sourceIds,
      animation: { duration: 600, easingFunction: 'easeInOutQuad' },
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  4. CAPTURE MODAL
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Wire the #btn-capture button to open the capture modal.
 * Called once on DOMContentLoaded.
 */
function setupCaptureModal() {
  const btn = document.getElementById('btn-capture');
  if (!btn) return;

  btn.addEventListener('click', openCaptureModal);

  // Wire the close button inside the modal (injected dynamically)
  document.addEventListener('click', (e) => {
    const target = e.target;
    if (target.id === 'capture-modal-overlay' ||
        target.classList.contains('capture-close')) {
      closeCaptureModal();
    }
  });
}

function openCaptureModal() {
  // Inject modal if not already in DOM
  let modal = document.getElementById('capture-modal');
  if (!modal) {
    modal = _buildCaptureModal();
    document.body.appendChild(modal);
    _wireCaptureModalTabs(modal);
    _wireCaptureModalSubmit(modal);
  }

  modal.classList.remove('hidden');
  modal.querySelector('#capture-modal-overlay').style.opacity = '1';
  modal.querySelector('.capture-modal-box').style.transform   = 'scale(1)';

  // Focus the text area on the default (Note) tab
  setTimeout(() => {
    const ta = modal.querySelector('#capture-note-text');
    if (ta) ta.focus();
  }, 120);
}

function closeCaptureModal() {
  const modal = document.getElementById('capture-modal');
  if (!modal) return;

  modal.classList.add('hidden');
  // Reset form state
  const status = modal.querySelector('#capture-status');
  if (status) status.textContent = '';
  const btn = modal.querySelector('#capture-submit-btn');
  if (btn) { btn.textContent = 'Capture'; btn.disabled = false; }
  // Clear inputs
  modal.querySelectorAll('textarea, input[type="text"]').forEach(el => {
    el.value = '';
  });
}

/** Build the capture modal HTML and inject it into the body */
function _buildCaptureModal() {
  const wrapper = document.createElement('div');
  wrapper.id = 'capture-modal';
  wrapper.innerHTML = `
    <div id="capture-modal-overlay">
      <div class="capture-modal-box" role="dialog" aria-modal="true" aria-label="Capture Note">
        <div class="capture-modal-header">
          <h2>✦ Capture</h2>
          <button class="capture-close" aria-label="Close">&times;</button>
        </div>

        <!-- Tabs -->
        <div class="capture-tabs" role="tablist">
          <button class="capture-tab active" data-tab="note" role="tab" aria-selected="true">📝 Note</button>
          <button class="capture-tab"         data-tab="url"  role="tab">🔗 URL</button>
          <button class="capture-tab"         data-tab="file" role="tab">📄 File</button>
          <button class="capture-tab"         data-tab="video" role="tab">🎥 Video</button>
        </div>

        <!-- Note tab -->
        <div class="capture-tab-panel" id="capture-panel-note">
          <textarea
            id="capture-note-text"
            placeholder="Type or paste your note here…"
            rows="6"
            aria-label="Note text"
          ></textarea>
        </div>

        <!-- URL tab -->
        <div class="capture-tab-panel hidden" id="capture-panel-url">
          <input
            type="text"
            id="capture-url-input"
            placeholder="https://…"
            aria-label="URL to capture"
          />
        </div>

        <!-- File tab -->
        <div class="capture-tab-panel hidden" id="capture-panel-file">
          <input
            type="file"
            id="capture-file-input"
            aria-label="File to upload"
            accept=".txt,.md,.pdf,.csv,.json,.py,.js,.png,.jpg,.jpeg,.mp3,.wav,.m4a"
          />
        </div>

        <!-- Video tab -->
        <div class="capture-tab-panel hidden" id="capture-panel-video">
          <input
            type="file"
            id="capture-video-input"
            aria-label="Video to upload"
            accept=".mp4,.mov,.avi,.mkv,.webm"
          />
          <div id="video-quality-container" style="margin-top: 10px;">
            <label for="capture-video-quality" style="font-size: 13px; color: var(--text-secondary);">Video Quality:</label>
            <select id="capture-video-quality" style="background: var(--bg-glass); color: var(--text-primary); border: 1px solid var(--border-glass); padding: 4px; border-radius: 4px; width: 100%; margin-top: 5px;">
              <option value="original">Original</option>
              <option value="720p">720p (Compress)</option>
              <option value="480p">480p (Compress)</option>
            </select>
          </div>
        </div>

        <div class="capture-modal-footer">
          <span id="capture-status" class="capture-status" role="status" aria-live="polite"></span>
          <button class="btn primary" id="capture-submit-btn">Capture</button>
        </div>
      </div>
    </div>`;
  return wrapper;
}

/** Wire tab switching inside the capture modal */
function _wireCaptureModalTabs(modal) {
  const tabs   = modal.querySelectorAll('.capture-tab');
  const panels = modal.querySelectorAll('.capture-tab-panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      // Active tab
      tabs.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');

      // Show matching panel
      const target = tab.dataset.tab;
      panels.forEach(panel => {
        panel.classList.toggle('hidden', !panel.id.endsWith(target));
      });

      // Focus the active field
      const activeField = modal.querySelector(`#capture-panel-${target} textarea, #capture-panel-${target} input[type="text"]`);
      if (activeField) activeField.focus();
    });
  });

  // Video Quality dropdown is now static in the Video tab, so no toggle logic needed.
}

/** Wire the submit button — POSTs to /api/capture */
function _wireCaptureModalSubmit(modal) {
  const submitBtn = modal.querySelector('#capture-submit-btn');
  const status    = modal.querySelector('#capture-status');

  submitBtn.addEventListener('click', async () => {
    if (_isCapturing) return;

    // Determine active tab
    const activeTab = modal.querySelector('.capture-tab.active');
    const tabName   = activeTab ? activeTab.dataset.tab : 'note';

    let type, content;

    if (tabName === 'note') {
      content = modal.querySelector('#capture-note-text').value.trim();
      type    = 'note';
    } else if (tabName === 'url') {
      content = modal.querySelector('#capture-url-input').value.trim();
      type    = 'url';
    }

    let fileInput = modal.querySelector('#capture-file-input');
    let videoInput = modal.querySelector('#capture-video-input');

    if (tabName !== 'file' && tabName !== 'video' && !content) {
      _setStatus(status, '⚠ Please enter some content first.', 'warn');
      return;
    } else if (tabName === 'file' && (!fileInput.files || fileInput.files.length === 0)) {
      _setStatus(status, '⚠ Please select a file first.', 'warn');
      return;
    } else if (tabName === 'video' && (!videoInput.files || videoInput.files.length === 0)) {
      _setStatus(status, '⚠ Please select a video first.', 'warn');
      return;
    }

    // Submit
    _isCapturing  = true;
    submitBtn.textContent = '…';
    submitBtn.disabled    = true;
    _setStatus(status, 'Capturing…', 'info');

    try {
      let res;
      if (tabName === 'file' || tabName === 'video') {
        const formData = new FormData();
        const inputToUse = tabName === 'video' ? videoInput : fileInput;
        formData.append('file', inputToUse.files[0]);
        if (tabName === 'video') {
          const qual = modal.querySelector('#capture-video-quality');
          if (qual) formData.append('quality', qual.value);
        }
        
        res = await fetch('/api/upload', {
          method: 'POST',
          body: formData,
        });
      } else {
        res = await fetch('/api/capture', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ type, content }),
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      _setStatus(
        status,
        `✓ Captured as "${data.title}" (${data.category})`,
        'success',
      );

      // Close after a brief success pause
      setTimeout(() => {
        closeCaptureModal();
        // Refresh the graph so the new node appears
        if (typeof loadGraph === 'function') loadGraph();
      }, 1800);

    } catch (err) {
      _setStatus(status, `✕ ${err.message}`, 'error');
      submitBtn.textContent = 'Capture';
      submitBtn.disabled    = false;
    } finally {
      _isCapturing = false;
    }
  });
}

function _setStatus(el, msg, kind) {
  if (!el) return;
  el.textContent  = msg;
  el.dataset.kind = kind;  // used by CSS for colour
}

// ═══════════════════════════════════════════════════════════════════════════
//  5. RENDER HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function _showLoadingState(display, btn, question) {
  display.classList.remove('hidden');
  display.innerHTML = `
    <div class="answer-loading">
      <span class="loading-dots">
        <span></span><span></span><span></span>
      </span>
      <span style="color:var(--text-muted);font-size:13px;">
        Searching your notes for <em>"${_escHtml(question)}"</em>…
      </span>
    </div>`;

  if (btn) {
    btn.textContent = '…';
    btn.disabled    = true;
  }
}

function _renderAnswer(display, data, question) {
  const answer     = data.answer     || '(no answer)';
  const sources    = data.sources    || [];
  const confidence = data.confidence || 'low';
  const embMs      = Math.round(data.query_embedding_time_ms || 0);
  const retMs      = Math.round(data.retrieval_time_ms       || 0);
  const llmMs      = Math.round(data.llm_time_ms             || 0);

  // Confidence badge
  const confColor = { high: '#34d399', medium: '#fbbf24', low: '#f87171' }[confidence] || '#94a3b8';
  const confLabel = { high: '● High',  medium: '◐ Medium', low: '○ Low' }[confidence]  || confidence;

  // Format answer with lightweight Markdown → HTML conversion
  const formattedAnswer = _formatAnswer(answer);

  // Source citation chips
  const sourcesHtml = sources.length
    ? `<div class="answer-sources">
        <span class="sources-label">Sources:</span>
        ${sources.map(s => `
          <button
            class="source-chip"
            data-id="${_escHtml(s.id)}"
            title="Similarity: ${(s.similarity * 100).toFixed(0)}%  ·  click to highlight in graph"
          >${_escHtml(s.title || s.id.slice(0, 8))}</button>`
        ).join('')}
       </div>`
    : '';

  display.innerHTML = `
    <div class="answer-header">
      <span class="answer-question">"${_escHtml(question)}"</span>
      <div class="answer-meta">
        <span class="conf-badge" style="color:${confColor}">${confLabel} confidence</span>
        <span class="timing-info">⏱ ${embMs + retMs}ms retrieve · ${llmMs}ms LLM</span>
        <button class="close-answer" title="Close (Esc)">✕</button>
      </div>
    </div>
    <div class="answer-body">${formattedAnswer}</div>
    ${sourcesHtml}`;

  // Source chip clicks → highlight corresponding graph nodes
  display.querySelectorAll('.source-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const id = chip.dataset.id;
      if (id) highlightSourceNodes([id]);
    });
  });

  // Close button
  const closeBtn = display.querySelector('.close-answer');
  if (closeBtn) closeBtn.addEventListener('click', hideAnswer);
}

function _renderError(display, message) {
  display.classList.remove('hidden');
  display.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;color:#f87171;">
      <span>⚠</span>
      <span style="font-size:13px;">${_escHtml(message)}</span>
      <button class="close-answer" style="margin-left:auto">✕</button>
    </div>`;
  display.querySelector('.close-answer')?.addEventListener('click', hideAnswer);
}

function hideAnswer() {
  const display = document.getElementById('answer-display');
  if (display) display.classList.add('hidden');
  // Reset node highlight when answer is dismissed
  highlightSourceNodes([]);
  adjustLayout();
}

// ═══════════════════════════════════════════════════════════════════════════
//  6. LAYOUT ADJUSTMENT
//  Dynamically set #main-content bottom so it is never hidden behind ask-bar
// ═══════════════════════════════════════════════════════════════════════════

function adjustLayout() {
  const askBar      = document.getElementById('ask-bar');
  const mainContent = document.getElementById('main-content');
  if (!askBar || !mainContent) return;

  const barHeight = askBar.getBoundingClientRect().height;
  mainContent.style.bottom = `${barHeight}px`;
}

// ═══════════════════════════════════════════════════════════════════════════
//  7. UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

/** Escape special HTML characters to prevent XSS */
function _escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#039;');
}

/**
 * Convert a subset of Markdown to HTML suitable for the answer panel.
 *
 * Handled patterns:
 *   **bold**       → <strong>
 *   *italic*       → <em>
 *   [Source: ...]  → <span class="inline-citation">
 *   - list item    → <ul><li>
 *   1. list item   → <ol><li>
 *   `code`         → <code>
 *   blank line     → paragraph break
 *   single \n      → <br>
 */
function _formatAnswer(text) {
  if (!text) return '';

  const lines   = text.split('\n');
  const output  = [];
  let inUL      = false;
  let inOL      = false;

  const closeList = () => {
    if (inUL) { output.push('</ul>'); inUL = false; }
    if (inOL) { output.push('</ol>'); inOL = false; }
  };

  for (let line of lines) {
    // Bullet list item
    const ulMatch = line.match(/^[\s]*[-*]\s+(.+)$/);
    if (ulMatch) {
      if (inOL) { output.push('</ol>'); inOL = false; }
      if (!inUL) { output.push('<ul>'); inUL = true; }
      output.push(`<li>${_inlineMarkdown(ulMatch[1])}</li>`);
      continue;
    }

    // Ordered list item
    const olMatch = line.match(/^[\s]*\d+\.\s+(.+)$/);
    if (olMatch) {
      if (inUL) { output.push('</ul>'); inUL = false; }
      if (!inOL) { output.push('<ol>'); inOL = true; }
      output.push(`<li>${_inlineMarkdown(olMatch[1])}</li>`);
      continue;
    }

    // Close any open list on non-list line
    closeList();

    // Blank line → paragraph break
    if (line.trim() === '') {
      output.push('<br>');
      continue;
    }

    // Regular line
    output.push(_inlineMarkdown(line) + '<br>');
  }

  closeList();

  // Wrap in a paragraph and clean up extra <br> at start/end
  let html = output.join('\n').replace(/^(<br>\s*)+/, '').replace(/(<br>\s*)+$/, '');
  return `<p>${html}</p>`;
}

/** Apply inline Markdown transformations to a single line */
function _inlineMarkdown(line) {
  return line
    // `code`
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // **bold**
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // *italic*
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // [Source: Title]  → styled citation span
    .replace(/\[Source:\s*(.+?)\]/g,
      '<span class="inline-citation">[Source: $1]</span>');
}

// ═══════════════════════════════════════════════════════════════════════════
//  8. CALCULATOR WIDGET
// ═══════════════════════════════════════════════════════════════════════════
function setupCalculator() {
  const widget = document.getElementById('calculator-widget');
  const toggleBtn = document.getElementById('btn-calc-toggle');
  const closeBtn = document.querySelector('.calc-close');
  
  if (!widget || !toggleBtn) return;
  
  toggleBtn.addEventListener('click', () => widget.classList.toggle('hidden'));
  closeBtn.addEventListener('click', () => widget.classList.add('hidden'));
  
  let currentInput = '0';
  let history = '';
  let lastOperator = null;
  let previousValue = null;
  let shouldResetScreen = false;
  
  const currentEl = document.getElementById('calc-current');
  const historyEl = document.getElementById('calc-history');
  
  const updateDisplay = () => {
    if (currentEl) currentEl.textContent = currentInput;
    if (historyEl) historyEl.textContent = history;
  };
  
  const calculate = (a, b, op) => {
    a = parseFloat(a); b = parseFloat(b);
    if (isNaN(a) || isNaN(b)) return b;
    switch (op) {
      case '+': return a + b;
      case '-': return a - b;
      case '*': return a * b;
      case '/': return b === 0 ? 'Error' : a / b;
      default: return b;
    }
  };
  
  widget.querySelectorAll('.calc-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const val = btn.dataset.val;
      
      if (val === 'C') {
        currentInput = '0'; history = ''; previousValue = null; lastOperator = null;
      } else if (val === 'DEL') {
        if (!shouldResetScreen) {
          currentInput = currentInput.slice(0, -1) || '0';
        }
      } else if (['+', '-', '*', '/'].includes(val)) {
        if (lastOperator && !shouldResetScreen) {
          currentInput = String(calculate(previousValue, currentInput, lastOperator));
        }
        previousValue = currentInput;
        lastOperator = val;
        history = `${previousValue} ${val}`;
        shouldResetScreen = true;
      } else if (val === '=') {
        if (lastOperator) {
          history = `${previousValue} ${lastOperator} ${currentInput} =`;
          currentInput = String(calculate(previousValue, currentInput, lastOperator));
          lastOperator = null;
          shouldResetScreen = true;
        }
      } else if (val) {
        if (shouldResetScreen) {
          currentInput = val;
          shouldResetScreen = false;
        } else {
          if (val === '.' && currentInput.includes('.')) return;
          currentInput = currentInput === '0' && val !== '.' ? val : currentInput + val;
        }
      }
      updateDisplay();
    });
  });
  
  // Capture Result
  const captureBtn = document.getElementById('btn-calc-capture');
  if (captureBtn) {
    captureBtn.addEventListener('click', async () => {
      const text = `Calculation: ${history}\nResult: ${currentInput}`;
      try {
        captureBtn.disabled = true;
        captureBtn.textContent = '...';
        const res = await fetch('/api/capture', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'note', content: text }),
        });
        if (res.ok) {
          if (typeof loadGraph === 'function') loadGraph();
          widget.classList.add('hidden');
        }
      } finally {
        captureBtn.disabled = false;
        captureBtn.textContent = '✦ Capture Result';
      }
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  setupAskBar();
  setupCaptureModal();
  setupCalculator();
  adjustLayout();

  // Re-measure layout whenever the window is resized
  window.addEventListener('resize', adjustLayout);
});
