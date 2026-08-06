/**
 * SecondSelf — Graph Renderer (Steps 3.4 + 4.4)
 *
 * Loads /api/graph, renders a vis-network force-directed graph, and
 * wires up all interactions:
 *   - Hover   → floating tooltip card
 *   - Click   → note detail panel slide-in + connected EDGE highlight  ← 4.4
 *   - Dbl-clk → zoom to node
 *   - Empty   → empty-state design shown when no notes exist           ← 4.4
 *   - Stats   → stats bar + header pill populated from /api/stats       ← 4.4
 */

'use strict';

// ── PARA colour map (matches style.css CSS variables) ───────────────────────
const CATEGORY_COLORS = {
  projects:  { background: '#6C5CE7', border: '#9b89ff', highlight: { background: '#8b7cf7', border: '#b8a9ff' } },
  areas:     { background: '#00B894', border: '#00d4aa', highlight: { background: '#00cfa6', border: '#33e8c4' } },
  resources: { background: '#0984E3', border: '#2fa8ff', highlight: { background: '#1a9af5', border: '#5cbfff' } },
  archives:  { background: '#636E72', border: '#8a979b', highlight: { background: '#7a878b', border: '#a4b0b4' } },
};

const DEFAULT_COLOR = CATEGORY_COLORS.resources;

// Edge colors
const EDGE_DEFAULT   = { color: 'rgba(148, 163, 184, 0.2)',  opacity: 1 };
const EDGE_HIGHLIGHT = { color: 'rgba(108,  92, 231, 0.85)', opacity: 1 };
const EDGE_DIM       = { color: 'rgba(148, 163, 184, 0.06)', opacity: 1 };

// ── Module-level state ──────────────────────────────────────────────────────
let _network      = null;   // vis.Network instance  (used by chat.js too)
let _nodesMap     = {};     // id → raw node data (from graph.json)
let _tooltip      = null;   // floating tooltip DOM element
let _selectedNode = null;   // currently selected node id

// ═══════════════════════════════════════════════════════════════════════════
//  1. LOAD GRAPH
// ═══════════════════════════════════════════════════════════════════════════

async function loadGraph() {
  const container = document.getElementById('graph-container');
  const emptyState = document.getElementById('graph-empty-state');

  try {
    const response = await fetch('/api/graph');

    if (!response.ok) {
      _showError(container, `Server returned ${response.status}: ${response.statusText}`);
      return;
    }

    const graphData = await response.json();
    const nodes = graphData.nodes || [];
    const edges = graphData.edges || [];

    // ── Empty state ── ────────────────────────────────────────────────────
    if (nodes.length === 0) {
      if (emptyState) emptyState.classList.remove('hidden');
      _showEmptyStats();
      return;
    }

    if (emptyState) emptyState.classList.add('hidden');

    // Build the node lookup map
    _nodesMap = {};
    for (const node of nodes) {
      _nodesMap[node.id] = node;
    }

    // Transform for vis-network
    const visNodes = _transformNodes(nodes);
    const visEdges = _transformEdges(edges);

    const data = {
      nodes: new vis.DataSet(visNodes),
      edges: new vis.DataSet(visEdges),
    };

    const options = _buildNetworkOptions();
    _network = new vis.Network(container, data, options);

    // Disable physics after stabilisation
    _network.once('stabilizationIterationsDone', () => {
      _network.setOptions({ physics: { enabled: false } });
      _network.fit({ animation: { duration: 800, easingFunction: 'easeOutQuart' } });
    });

    _setupInteractions(_network, data);
    _setupFilters(data);
    _showGraphStats(graphData.metadata || {});

    // Load and render dashboard stats
    _loadStats();

  } catch (err) {
    _showError(container, `Failed to load graph: ${err.message}`);
    console.error('[SecondSelf] Graph load error:', err);
  }
}

// ── Node transformation ───────────────────────────────────────────────────

function _transformNodes(rawNodes) {
  const now = Date.now();
  const total = rawNodes.length;

  return rawNodes.map((node, index) => {
    const linkCount = node.link_count || 0;

    // Size proportional to link_count (min: 14, max: 42)
    const size = Math.min(42, Math.max(14, 14 + linkCount * 6));

    // "Recent" node = captured within last 7 days
    let createdMs = 0;
    try { createdMs = node.created ? new Date(node.created).getTime() : 0; } catch (_) {}
    const isRecent = (now - createdMs) < 7 * 24 * 60 * 60 * 1000;

    // Unique color per node using golden-angle hue distribution
    const hue = (index * 137.508) % 360;  // golden angle for max spread
    const bg        = `hsl(${hue}, 70%, 55%)`;
    const border    = `hsl(${hue}, 75%, 65%)`;
    const hlBg      = `hsl(${hue}, 80%, 65%)`;
    const hlBorder  = `hsl(${hue}, 85%, 75%)`;

    const colors = {
      background: bg,
      border: border,
      highlight: { background: hlBg, border: hlBorder },
    };

    return {
      id:    node.id,
      label: _truncate(node.label, 22),
      title: _buildTooltipHTML(node),
      size,
      color: colors,
      shape: 'dot',
      font: {
        color: '#e2e8f0',
        size:  12,
        face:  'Inter, sans-serif',
        bold:  { color: '#ffffff', size: 13 },
      },
      shadow: {
        enabled: true,
        color:   'rgba(0,0,0,0.45)',
        size:    8,
        x: 2,
        y: 2,
      },
      _raw:    node,
      _recent: isRecent,
    };
  });
}

function _transformEdges(rawEdges) {
  return rawEdges.map((edge, i) => ({
    id:     `e-${i}`,
    from:   edge.from,
    to:     edge.to,
    width:  1.5,
    color:  EDGE_DEFAULT,
    smooth: { type: 'dynamic' },
    arrows: { to: { enabled: false } },
  }));
}

// ── vis-network configuration ─────────────────────────────────────────────

function _buildNetworkOptions() {
  return {
    nodes: {
      shape: 'dot',
      font:  { color: '#e2e8f0', size: 12, face: 'Inter, sans-serif' },
      borderWidth: 2,
      borderWidthSelected: 3,
    },
    edges: {
      smooth:  { type: 'dynamic' },
      color:   { inherit: false },
      selectionWidth: 0,   // we handle edge selection manually
    },
    physics: {
      enabled: true,
      solver: 'barnesHut',
      barnesHut: {
        gravitationalConstant: -3000,
        centralGravity: 0.3,
        springLength: 120,
        springConstant: 0.04,
        damping: 0.3,
        avoidOverlap: 0.1,
      },
      stabilization: { iterations: 250, updateInterval: 25 },
    },
    interaction: {
      hover:           true,
      tooltipDelay:    100,
      hideEdgesOnDrag: false,
      dragNodes:       true,
      zoomView:        true,
      navigationButtons: false,
      keyboard:        { enabled: true },
    },
    layout: {
      improvedLayout: true,
    },
  };
}

// ═══════════════════════════════════════════════════════════════════════════
//  2. SETUP INTERACTIONS
// ═══════════════════════════════════════════════════════════════════════════

function _setupInteractions(network, data) {
  const edgesDataset = data.edges;

  // ── Hover: floating tooltip ──────────────────────────────────────────
  network.on('hoverNode', (params) => {
    const node = _nodesMap[params.node];
    if (!node) return;

    _removeTooltip();
    _tooltip = document.createElement('div');
    _tooltip.className = 'node-tooltip';
    _tooltip.innerHTML = _buildTooltipHTML(node);
    document.body.appendChild(_tooltip);
    _positionTooltip(params.event);
  });

  network.on('blurNode', () => _removeTooltip());

  network.on('mouseMoved', (params) => {
    if (_tooltip) _positionTooltip(params.event);
  });

  // ── Click: note panel + EDGE HIGHLIGHT ──────────────────────────────
  network.on('click', (params) => {
    _removeTooltip();

    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      _selectedNode = nodeId;

      showNoteDetail(nodeId);
      _highlightConnectedEdges(nodeId, edgesDataset);

      // Select the node itself (gives it the highlight border in vis)
      network.selectNodes([nodeId], false);

    } else {
      // Click on empty canvas — reset everything
      _selectedNode = null;
      resetNotePanel();
      _resetAllEdges(edgesDataset);
      network.unselectAll();
    }
  });

  // ── Double click: zoom to node ───────────────────────────────────────
  network.on('doubleClick', (params) => {
    if (params.nodes.length > 0) {
      network.focus(params.nodes[0], {
        scale:     1.5,
        animation: { duration: 600, easingFunction: 'easeInOutQuad' },
      });
    }
  });

  // ── Drag: keep tooltip hidden while dragging ─────────────────────────
  network.on('dragStart', () => _removeTooltip());
}

// ── Graph Filtering ───────────────────────────────────────────────────────

let _activeCategories = new Set(['projects', 'areas', 'resources', 'archives']);

function _setupFilters(data) {
  const nodesDataset = data.nodes;
  
  document.querySelectorAll('.filter-btn').forEach(btn => {
    // Reset state in case graph reloads
    btn.classList.add('active');
    
    // Remove old listeners by cloning (simple way)
    const newBtn = btn.cloneNode(true);
    btn.parentNode.replaceChild(newBtn, btn);
    
    newBtn.addEventListener('click', (e) => {
      const cat = e.target.dataset.category;
      if (_activeCategories.has(cat)) {
        _activeCategories.delete(cat);
        e.target.classList.remove('active');
      } else {
        _activeCategories.add(cat);
        e.target.classList.add('active');
      }
      _applyFilters(nodesDataset);
    });
  });
  
  // Apply immediately in case _activeCategories was modified before reload
  _applyFilters(nodesDataset);
}

function _applyFilters(nodesDataset) {
  const allNodeIds = nodesDataset.getIds();
  const updates = allNodeIds.map(id => {
    const node = _nodesMap[id];
    const cat = (node && node.category) ? node.category : 'resources';
    return {
      id: id,
      hidden: !_activeCategories.has(cat)
    };
  });
  nodesDataset.update(updates);
}

// ── Edge highlight helpers ────────────────────────────────────────────────

/**
 * Highlight edges connected to nodeId and dim all others.
 * This is the Step 4.4 "Node click highlights connected edges" feature.
 */
function _highlightConnectedEdges(nodeId, edgesDataset) {
  const connectedEdgeIds = new Set(_network.getConnectedEdges(nodeId));
  const allEdgeIds       = edgesDataset.getIds();

  const updates = allEdgeIds.map(eid => ({
    id:    eid,
    color: connectedEdgeIds.has(eid) ? EDGE_HIGHLIGHT : EDGE_DIM,
    width: connectedEdgeIds.has(eid) ? 2.5 : 1,
  }));

  edgesDataset.update(updates);
}

/** Restore all edges to their default (unselected) appearance. */
function _resetAllEdges(edgesDataset) {
  const updates = edgesDataset.getIds().map(eid => ({
    id:    eid,
    color: EDGE_DEFAULT,
    width: 1.5,
  }));
  edgesDataset.update(updates);
}

// ═══════════════════════════════════════════════════════════════════════════
//  3. NOTE DETAIL PANEL  (with slide-in animation)
// ═══════════════════════════════════════════════════════════════════════════

function showNoteDetail(nodeId) {
  const node = _nodesMap[nodeId];
  if (!node) return;

  const emptyEl  = document.getElementById('note-panel-empty');
  const detailEl = document.getElementById('note-detail');

  // ── Slide-in transition ──────────────────────────────────────────────
  if (emptyEl && !emptyEl.classList.contains('hidden')) {
    emptyEl.classList.add('panel-exit');
    setTimeout(() => {
      emptyEl.classList.add('hidden');
      emptyEl.classList.remove('panel-exit');
      if (detailEl) {
        detailEl.classList.remove('hidden');
        detailEl.classList.add('panel-enter');
        requestAnimationFrame(() => detailEl.classList.remove('panel-enter'));
      }
    }, 180);
  } else if (detailEl && detailEl.classList.contains('hidden')) {
    detailEl.classList.remove('hidden');
    detailEl.classList.add('panel-enter');
    requestAnimationFrame(() => detailEl.classList.remove('panel-enter'));
  }

  // ── Populate content ─────────────────────────────────────────────────

  // Title
  const titleEl = document.getElementById('note-title');
  if (titleEl) titleEl.textContent = node.label || 'Untitled';

  // Category badge
  const badge = document.getElementById('note-category');
  if (badge) {
    badge.textContent = node.category || '';
    badge.className   = `badge ${node.category || ''}`;
    badge.classList.remove('hidden');
  }

  // Tags
  const tagsContainer = document.getElementById('note-tags');
  if (tagsContainer) {
    tagsContainer.innerHTML = '';
    const tags = Array.isArray(node.tags) ? node.tags : [];
    tags.forEach(tag => {
      const chip       = document.createElement('span');
      chip.className   = 'tag';
      chip.textContent = `#${tag}`;
      tagsContainer.appendChild(chip);
    });
  }

  // Content preview
  const preview = document.getElementById('note-content-preview');
  if (preview) {
    preview.innerHTML = '';
    // Store original text so we can translate it or reset
    const originalText = node.content_preview || node.summary || '';
    
    const textEl = document.createElement('div');
    textEl.style.whiteSpace = 'pre-wrap';
    textEl.textContent = originalText;
    preview.appendChild(textEl);
    
    // Word count
    const wc     = document.createElement('small');
    wc.className = 'word-count-hint';
    wc.textContent = node.word_count ? `${node.word_count} words` : '';
    wc.style.display = 'block';
    wc.style.marginTop = '10px';
    preview.appendChild(wc);

    // Wire up Translate button
    const translateBtn = document.getElementById('btn-translate');
    const translateSelect = document.getElementById('translate-lang');
    if (translateBtn && translateSelect) {
      // Remove old event listeners by cloning
      const newBtn = translateBtn.cloneNode(true);
      translateBtn.parentNode.replaceChild(newBtn, translateBtn);
      
      newBtn.addEventListener('click', async () => {
        const lang = translateSelect.value;
        const oldText = newBtn.textContent;
        newBtn.textContent = 'Translating...';
        newBtn.disabled = true;

        try {
          const res = await fetch('/api/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note_id: nodeId, target_language: lang })
          });
          
          if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Translation failed');
          }
          
          const data = await res.json();
          textEl.textContent = data.translated_text;
          
        } catch (e) {
          alert('Error: ' + e.message);
        } finally {
          newBtn.textContent = oldText;
          newBtn.disabled = false;
        }
      });
    }
  }

  // Video player
  const videoContainer = document.getElementById('note-video-container');
  if (videoContainer) {
    if (node._raw && node._raw.metadata && node._raw.metadata.video_filename) {
      const filename = node._raw.metadata.video_filename;
      videoContainer.innerHTML = `
        <video controls style="width:100%; border-radius:8px; margin-bottom:10px;" src="/memory/${filename}"></video>
        <a href="/memory/${filename}" download class="btn" style="display:block; text-align:center; margin-bottom:15px; border-color:var(--border-glass);">Download Video</a>
      `;
      videoContainer.classList.remove('hidden');
    } else {
      videoContainer.innerHTML = '';
      videoContainer.classList.add('hidden');
    }
  }

  // Related notes
  const relContainer = document.getElementById('note-related-container');
  const relList      = document.getElementById('note-related-list');
  if (relList) relList.innerHTML = '';

  const relatedIds = _getRelatedNodeIds(nodeId);
  if (relatedIds.length > 0 && relContainer) {
    relatedIds.forEach(relId => {
      const rel = _nodesMap[relId];
      if (!rel) return;
      const li = document.createElement('li');
      const a  = document.createElement('a');
      a.href        = '#';
      a.textContent = rel.label || relId;
      a.addEventListener('click', (e) => {
        e.preventDefault();
        showNoteDetail(relId);
        if (_network) {
          _network.selectNodes([relId], false);
          if (_network.body.data.edges) {
            _highlightConnectedEdges(relId, _network.body.data.edges);
          }
        }
      });
      li.appendChild(a);
      relList.appendChild(li);
    });
    relContainer.classList.remove('hidden');
  } else if (relContainer) {
    relContainer.classList.add('hidden');
  }

  // Scroll panel to top
  const panelContent = document.getElementById('note-panel-content');
  if (panelContent) panelContent.scrollTop = 0;
}

function resetNotePanel() {
  const emptyEl  = document.getElementById('note-panel-empty');
  const detailEl = document.getElementById('note-detail');

  if (detailEl && !detailEl.classList.contains('hidden')) {
    detailEl.classList.add('panel-exit');
    setTimeout(() => {
      detailEl.classList.add('hidden');
      detailEl.classList.remove('panel-exit');
      if (emptyEl) {
        emptyEl.classList.remove('hidden');
        emptyEl.classList.add('panel-enter');
        requestAnimationFrame(() => emptyEl.classList.remove('panel-enter'));
      }
    }, 180);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  4. STATS DASHBOARD  (Step 4.4)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Fetch /api/stats and populate the stats bar + header pill.
 * Called after the graph is loaded.
 */
async function _loadStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    const stats = await res.json();

    _renderStatsDashboard(stats);
    _renderHeaderPill(stats);

  } catch (_) {
    // Non-fatal — stats are decorative
  }
}

function _renderStatsDashboard(stats) {
  const by   = stats.by_category || {};
  const cats = ['projects', 'areas', 'resources', 'archives'];

  cats.forEach(cat => {
    const el = document.querySelector(`#sc-${cat} .stat-card-count`);
    if (el) el.textContent = by[cat] ?? 0;
  });

  const totalEl = document.querySelector('#sc-total .stat-card-count');
  if (totalEl) totalEl.textContent = stats.total_notes ?? 0;
}

function _renderHeaderPill(stats) {
  const notesEl    = document.getElementById('stat-notes-count');
  const embeddedEl = document.getElementById('stat-embedded-count');

  if (notesEl)    notesEl.textContent    = stats.total_notes    ?? 0;
  if (embeddedEl) embeddedEl.textContent = stats.total_embedded ?? 0;
}

function _showEmptyStats() {
  // Set all counts to 0 rather than "—"
  document.querySelectorAll('.stat-card-count').forEach(el => { el.textContent = 0; });
  const notesEl    = document.getElementById('stat-notes-count');
  const embeddedEl = document.getElementById('stat-embedded-count');
  if (notesEl)    notesEl.textContent    = 0;
  if (embeddedEl) embeddedEl.textContent = 0;
}

// ═══════════════════════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════════════════════

/** Build rich HTML for the hover tooltip */
function _buildTooltipHTML(node) {
  const tags = Array.isArray(node.tags) && node.tags.length
    ? node.tags.map(t => `<span style="opacity:.7">#${t}</span>`).join(' ')
    : '';
  const summary = node.summary
    ? `<div style="margin-top:5px;opacity:.8;">${_truncate(node.summary, 120)}</div>`
    : '';
  const badge = node.category
    ? `<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:rgba(255,255,255,.08);color:#94a3b8">${node.category}</span>`
    : '';
  const links = node.link_count
    ? `<div style="margin-top:4px;font-size:10px;color:#64748b">${node.link_count} link${node.link_count !== 1 ? 's' : ''}</div>`
    : '';

  return `<div class="tooltip-title">${node.label || node.id}</div>` +
         badge + summary + links +
         (tags ? `<div style="margin-top:5px;font-size:11px">${tags}</div>` : '');
}

/** Position the floating tooltip near the mouse, keeping it on screen */
function _positionTooltip(event) {
  if (!_tooltip) return;
  const padding = 16;
  const rect    = _tooltip.getBoundingClientRect();
  let x = (event.clientX || event.pageX || 0) + padding;
  let y = (event.clientY || event.pageY || 0) + padding;

  if (x + rect.width  > window.innerWidth)  x -= rect.width  + padding * 2;
  if (y + rect.height > window.innerHeight) y -= rect.height + padding * 2;

  _tooltip.style.left = `${x}px`;
  _tooltip.style.top  = `${y}px`;
}

function _removeTooltip() {
  if (_tooltip) { _tooltip.remove(); _tooltip = null; }
}

/** Return IDs of nodes connected to nodeId via any edge */
function _getRelatedNodeIds(nodeId) {
  if (!_network) return [];
  return [...new Set(_network.getConnectedNodes(nodeId))].filter(id => id !== nodeId);
}

function _truncate(str, max) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max).trimEnd() + '…' : str;
}

/** Show an error overlay inside the graph container */
function _showError(container, msg) {
  container.innerHTML = `
    <div class="graph-error-state">
      <span class="graph-error-icon">⚠️</span>
      <strong>Graph unavailable</strong>
      <p>${msg}</p>
      <p style="font-size:12px;opacity:.6;margin-top:4px;">
        Make sure the SecondSelf server is running:<br>
        <code>uv run secondself serve</code>
      </p>
    </div>`;
}

/** Overlay graph metadata stats badge in the top-left corner */
function _showGraphStats(meta) {
  const container = document.getElementById('graph-container');
  if (!container) return;

  // Remove any existing badge
  container.querySelector('.graph-meta-badge')?.remove();

  const badge = document.createElement('div');
  badge.className = 'graph-meta-badge';

  const pill = (label, val, color) => `
    <span class="graph-meta-pill" style="--pill-color:${color || '#94a3b8'}">
      ${label} <strong>${val}</strong>
    </span>`;

  badge.innerHTML =
    pill('Nodes', meta.total_nodes || 0, '#a78bfa') +
    pill('Edges', meta.total_edges || 0, '#60a5fa');

  if (meta.category_counts) {
    for (const [cat, count] of Object.entries(meta.category_counts)) {
      const c = (CATEGORY_COLORS[cat] || DEFAULT_COLOR).background;
      badge.innerHTML += pill(cat, count, c);
    }
  }

  container.appendChild(badge);
}

// ── Wire the empty-state CTA button ────────────────────────────────────────
function _wireEmptyStateCTA() {
  const btn = document.getElementById('btn-empty-capture');
  if (btn) {
    btn.addEventListener('click', () => {
      if (typeof openCaptureModal === 'function') openCaptureModal();
    });
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  VIDEO GALLERY
// ═══════════════════════════════════════════════════════════════════════════
let _galleryActive = false;

function setupVideoGallery() {
  const toggleBtn = document.getElementById('btn-gallery-toggle');
  const graphSection = document.getElementById('graph-section');
  const notePanel = document.getElementById('note-panel');
  const gallerySection = document.getElementById('gallery-section');
  
  if (!toggleBtn || !gallerySection) return;
  
  // --- Upload button: simple file picker → POST /api/upload-video ---
  const uploadBtn = document.getElementById('btn-gallery-upload');
  if (uploadBtn) {
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = '.mp4,.mov,.avi,.mkv,.webm';
    fileInput.style.display = 'none';
    document.body.appendChild(fileInput);

    uploadBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', async () => {
      if (!fileInput.files || fileInput.files.length === 0) return;

      const file = fileInput.files[0];
      uploadBtn.disabled = true;
      uploadBtn.textContent = '⏳ Uploading…';

      try {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('/api/upload-video', {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert('Upload failed: ' + (err.detail || res.statusText));
        } else {
          _renderGallery();
        }
      } catch (e) {
        alert('Upload error: ' + e.message);
      } finally {
        uploadBtn.disabled = false;
        uploadBtn.innerHTML = '<span aria-hidden="true">✦</span> Upload Video';
        fileInput.value = '';
      }
    });
  }
  
  // --- Toggle gallery view (sidebar, graph stays visible) ---
  toggleBtn.addEventListener('click', () => {
    _galleryActive = !_galleryActive;
    
    if (_galleryActive) {
      // Show gallery sidebar, hide note panel, keep graph visible
      notePanel.classList.add('hidden');
      gallerySection.classList.remove('hidden');
      toggleBtn.classList.add('active');
      toggleBtn.style.borderColor = 'var(--border-glow)';
      _renderGallery();
    } else {
      // Hide gallery, restore note panel
      gallerySection.classList.add('hidden');
      notePanel.classList.remove('hidden');
      toggleBtn.classList.remove('active');
      toggleBtn.style.borderColor = 'var(--border-glass)';
    }
  });
}

async function _renderGallery() {
  const grid = document.getElementById('gallery-grid');
  if (!grid) return;
  
  grid.innerHTML = '<div style="color:var(--text-muted); padding:16px; font-size:13px;">Loading…</div>';
  
  try {
    const res = await fetch('/api/videos');
    const data = await res.json();
    const videos = data.videos || [];

    grid.innerHTML = '';

    if (videos.length === 0) {
      grid.innerHTML = `<div style="color:var(--text-muted); font-size: 13px; padding: 16px;">
        No videos yet. Click <strong>✦ Upload Video</strong> above to add one.
      </div>`;
      return;
    }

    videos.forEach(video => {
      const card = document.createElement('div');
      card.className = 'video-card';
      card.innerHTML = `
        <div class="video-card-thumbnail">
          <div class="play-overlay">
            <span style="font-size:16px; color:#a78bfa;">▶</span>
          </div>
        </div>
        <div class="video-card-title" title="${video.display_name}">${video.display_name}</div>
        <div class="video-card-meta">
          <span>${video.size_mb} MB</span>
          <span>${new Date(video.modified * 1000).toLocaleDateString()}</span>
        </div>
      `;
      
      // Clicking anywhere on the row opens the modal
      card.addEventListener('click', () => {
        const modal = document.getElementById('video-player-modal');
        const videoEl = document.getElementById('video-player-element');
        if (modal && videoEl) {
          videoEl.src = `/memory/${video.filename}`;
          modal.classList.remove('hidden');
          videoEl.play();
        }
      });
      
      grid.appendChild(card);
    });

  } catch (e) {
    grid.innerHTML = `<div style="color:#f87171; padding:16px;">Failed to load videos: ${e.message}</div>`;
  }
}


function _setupVideoModal() {
  const modal = document.getElementById('video-player-modal');
  const closeBtn = document.querySelector('.video-player-close');
  const overlay = document.querySelector('.video-player-overlay');
  const videoEl = document.getElementById('video-player-element');

  if (!modal || !videoEl) return;

  const closeModal = () => {
    modal.classList.add('hidden');
    videoEl.pause();
    videoEl.src = '';
  };

  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (overlay) overlay.addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
      closeModal();
    }
  });
}

// ── Initialise on DOM load ─────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadGraph();
  _wireEmptyStateCTA();
  setupVideoGallery();
  _setupVideoModal();
});
