// ── Theme ────────────────────────────────────────────
let theme = localStorage.getItem('ae-theme') || 'dark';
applyTheme(theme);
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('themeIcon').textContent = t === 'dark' ? '🌙' : '☀';
  const dt = document.getElementById('darkToggle');
  if (dt) { dt.classList.toggle('on', t === 'dark'); }
  localStorage.setItem('ae-theme', t);
  theme = t;
}
function toggleTheme() { applyTheme(theme === 'dark' ? 'light' : 'dark'); }

// ── Page switching ───────────────────────────────────
function showPage(name) {
  document.querySelectorAll('[id^="page-"]').forEach(p => p.style.display = 'none');
  const pg = document.getElementById('page-' + name);
  if (pg) { pg.style.display = 'flex'; pg.classList.add('active'); }
  document.querySelectorAll('.sidebar-icon[id^="sb-"]').forEach(el => el.classList.remove('active'));
  const sb = document.getElementById('sb-' + name);
  if (sb) sb.classList.add('active');
}

// ── Mode switching (Review ↔ Assistant) ─────────────
function switchMode(mode) {
  // Tab buttons
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  const tab = document.querySelector(`.mode-tab[data-mode="${mode}"]`);
  if (tab) tab.classList.add('active');

  // Pages
  document.getElementById('page-analyse').style.display = 'none';
  document.getElementById('page-analyse').classList.remove('active');
  document.getElementById('page-assistant').style.display = 'none';
  document.getElementById('page-assistant').classList.remove('active');

  // Sidebar icons
  document.querySelectorAll('.sidebar-icon[id^="sb-"]').forEach(el => el.classList.remove('active'));

  const reviewOnly = ['reviewLangGroup','reviewOnlySep','reviewConvertSep','reviewConvertBtn'];

  if (mode === 'review') {
    document.getElementById('page-analyse').style.display = 'flex';
    document.getElementById('page-analyse').classList.add('active');
    const sb = document.getElementById('sb-analyse');
    if (sb) sb.classList.add('active');
    reviewOnly.forEach(id => { const el = document.getElementById(id); if(el) el.style.display=''; });
  } else {
    document.getElementById('page-assistant').style.display = 'flex';
    document.getElementById('page-assistant').classList.add('active');
    const sb = document.getElementById('sb-assistant');
    if (sb) sb.classList.add('active');
    reviewOnly.forEach(id => { const el = document.getElementById(id); if(el) el.style.display='none'; });
  }
}

// ── AI Assistant ─────────────────────────────────────
let asstHistory = [];
let asstOutputText = '';

function updateAsstMode() {
  const hasCode = document.getElementById('asstCode').value.trim().length > 0;
  const p1 = document.getElementById('asstModePill1');
  const p2 = document.getElementById('asstModePill2');
  const btn = document.getElementById('asstBtnText');
  if (hasCode) {
    p1.className = 'asst-mode-pill'; p2.className = 'asst-mode-pill active-mod';
    btn.textContent = 'Modify Code';
  } else {
    p1.className = 'asst-mode-pill active-gen'; p2.className = 'asst-mode-pill';
    btn.textContent = 'Generate Code';
  }
}

function updateCharCount(el) {
  const c = el.value.length;
  document.getElementById('asstCharCount').textContent = c + ' / 2000';
  if (c > 1800) document.getElementById('asstCharCount').style.color = 'var(--rose)';
  else if (c > 1400) document.getElementById('asstCharCount').style.color = 'var(--amber)';
  else document.getElementById('asstCharCount').style.color = '';
}

function syncAsstLines(ta) {
  const lines = ta.value.split('\n').length;
  const nums = Array.from({length: lines}, (_, i) => i + 1).join('\n');
  document.getElementById('asstLineNums').textContent = nums + '\n';
}

function fillPrompt(text) {
  document.getElementById('asstPrompt').value = text;
  updateCharCount(document.getElementById('asstPrompt'));
  document.getElementById('asstPrompt').focus();
}

function setAsstOutputDot(color) {
  const dot = document.getElementById('asstOutputDot');
  dot.style.background = color;
  if (color === 'var(--sky)') dot.style.boxShadow = '0 0 6px rgba(56,189,248,.6)';
  else dot.style.boxShadow = '';
}

async function runAssistant() {
  const prompt = document.getElementById('asstPrompt').value.trim();
  const code   = document.getElementById('asstCode').value.trim();

  if (!prompt) {
    showAsstError('⚠ Please enter a prompt before submitting.');
    return;
  }

  // Reset UI
  hideAsstError();
  document.getElementById('asstEmptyState').style.display = 'none';
  document.getElementById('asstOutput').style.display = 'none';
  document.getElementById('asstOutputFooter').style.display = 'none';
  document.getElementById('asstMetaBar').style.display = 'none';
  document.getElementById('asstCopyBtn').style.display = 'none';
  document.getElementById('asstDownloadBtn').style.display = 'none';
  document.getElementById('asstClearBtn').style.display = 'none';
  document.getElementById('asstLoading').classList.add('show');
  document.getElementById('asstSubmitBtn').disabled = true;
  setAsstOutputDot('var(--sky)');
  document.getElementById('asstOutputLabel').textContent = 'Generating...';

  const steps = ['Connecting to model','Analyzing prompt','Processing context','Generating output','Finalizing response'];
  let stepIdx = 0;
  const stepInterval = setInterval(() => {
    document.getElementById('asstLoadingStep').textContent = steps[Math.min(stepIdx++, steps.length-1)];
  }, 900);

  const startTime = Date.now();

  try {
    await runAssistantStreaming(prompt, code, startTime, stepInterval);
  } catch(err) {
    console.warn('Streaming failed, falling back to non-streaming /assistant:', err);
    try {
      await runAssistantNonStreaming(prompt, code, startTime, stepInterval);
    } catch(err2) {
      clearInterval(stepInterval);
      showAsstError('❌ Network error — is the server running?');
    }
  } finally {
    document.getElementById('asstLoading').classList.remove('show');
    document.getElementById('asstSubmitBtn').disabled = false;
  }
}

function finalizeAsstOutput(output, modelName, promptTok, outputTok, totalTok, limitPct, limit, startTime) {
  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1) + 's';
  const lineCount = output.split('\n').length;

  if (limitPct >= 80) {
    showAsstError(`⚠ Used ${limitPct}% of ${modelName}'s context window (${totalTok.toLocaleString()} / ${limit.toLocaleString()} tokens). Try shorter code or a model with a larger context window.`);
  }

  // History is saved server-side (in app.py, both /assistant and
  // /assistant/stream) — refresh the strip from there instead of keeping a
  // separate client-side copy. This also means assistant history now
  // survives a page reload, which it never did before (it was a plain JS
  // array with no persistence at all — not even localStorage).
  loadAsstHistoryFromServer();

  document.getElementById('asstOutputFooter').style.display = 'flex';
  document.getElementById('asstMetaBar').style.display = 'flex';
  document.getElementById('asstCopyBtn').style.display = '';
  document.getElementById('asstDownloadBtn').style.display = '';
  document.getElementById('asstClearBtn').style.display = '';
  document.getElementById('metaMode').textContent       = document.getElementById('asstCode').value.trim() ? 'Modify' : 'Generate';
  document.getElementById('metaModel').textContent      = modelName || '—';
  document.getElementById('metaPromptTok').textContent  = promptTok.toLocaleString();
  document.getElementById('metaOutputTok').textContent  = outputTok.toLocaleString();
  document.getElementById('metaTokens').textContent     = totalTok.toLocaleString();
  document.getElementById('metaLimitPct').textContent   = limitPct + '%';
  document.getElementById('metaTime').textContent       = elapsed;
  document.getElementById('metaLines').textContent      = lineCount;
  const fill = document.getElementById('metaLimitFill');
  fill.style.width = Math.min(limitPct, 100) + '%';
  fill.style.background = limitPct >= 80 ? 'var(--rose)' : limitPct >= 60 ? 'var(--amber)' : 'var(--lime)';
  setAsstOutputDot('var(--lime)');
  document.getElementById('asstOutputLabel').textContent = document.getElementById('asstCode').value.trim() ? 'Modified Code' : 'Generated Code';
}

// Real streaming: reads Server-Sent Events from /assistant/stream as Groq
// actually generates them, appending text live — no fake character-by-character
// reveal of an already-complete response.
async function runAssistantStreaming(prompt, code, startTime, stepInterval) {
  const resp = await fetch('/assistant/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, code })
  });
  if (!resp.ok || !resp.body) throw new Error('stream endpoint unavailable');

  clearInterval(stepInterval);
  document.getElementById('asstLoading').classList.remove('show');
  const outEl = document.getElementById('asstOutput');
  outEl.style.display = 'block';
  outEl.textContent = '';
  const cursor = document.createElement('span');
  cursor.className = 'stream-cursor';
  outEl.appendChild(cursor);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';
  let doneData = null;
  let sawError = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop(); // last part may be incomplete, keep it for next read
    for (const part of parts) {
      const line = part.split('\n').find(l => l.startsWith('data: '));
      if (!line) continue;
      let evt;
      try { evt = JSON.parse(line.slice(6)); } catch { continue; }
      if (evt.type === 'chunk') {
        fullText += evt.text;
        outEl.insertBefore(document.createTextNode(evt.text), cursor);
        outEl.scrollTop = outEl.scrollHeight;
      } else if (evt.type === 'done') {
        doneData = evt;
      } else if (evt.type === 'error') {
        sawError = evt.message;
      }
    }
  }
  cursor.remove();

  if (sawError || !fullText.trim()) {
    showAsstError('❌ ' + (sawError || 'Request failed. Check server.'));
    return;
  }

  // Safety net: strip a stray leading/trailing code fence if the model
  // added one despite being told not to (rare, but streamed text can't be
  // cleaned mid-flight the way a full response can).
  let cleaned = fullText.trim();
  cleaned = cleaned.replace(/^```[a-zA-Z]*\n?/, '').replace(/```$/, '').trim();
  if (cleaned !== fullText.trim()) {
    outEl.textContent = cleaned;
  }
  asstOutputText = cleaned;

  const d = doneData || {};
  finalizeAsstOutput(cleaned, d.model || '', d.prompt_tokens || 0, d.output_tokens || 0,
                      d.total_tokens || 0, d.limit_pct || 0, d.limit || 0, startTime);
}

// Fallback for browsers/networks where streaming fails outright — same
// non-streaming endpoint as before, just without the fake typewriter.
async function runAssistantNonStreaming(prompt, code, startTime, stepInterval) {
  try {
    const resp = await fetch('/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, code })
    });
    const data = await resp.json();
    clearInterval(stepInterval);

    if (!resp.ok || data.error) {
      showAsstError('❌ ' + (data.error || 'Request failed. Check server.'));
      return;
    }

    const output = data.result || '';
    asstOutputText = output;
    const modelName = data.model || '';

    document.getElementById('asstLoading').classList.remove('show');
    const outEl = document.getElementById('asstOutput');
    outEl.style.display = 'block';
    outEl.textContent = output;

    finalizeAsstOutput(output, modelName, data.prompt_tokens || 0, data.output_tokens || 0,
                        data.total_tokens || 0, data.limit_pct || 0, data.limit || 0, startTime);
  } catch(err) {
    clearInterval(stepInterval);
    throw err; // let the outer runAssistant() catch handle the error message
  }
}

function showAsstError(msg) {
  const el = document.getElementById('asstError');
  el.textContent = msg; el.classList.add('show');
  document.getElementById('asstLoading').classList.remove('show');
  document.getElementById('asstEmptyState').style.display = 'flex';
  document.getElementById('asstSubmitBtn').disabled = false;
  setAsstOutputDot('var(--rose)');
  document.getElementById('asstOutputLabel').textContent = 'Output';
}
function hideAsstError() {
  document.getElementById('asstError').classList.remove('show');
}

function copyAsstOutput() {
  navigator.clipboard.writeText(asstOutputText).then(() => {
    const btn = document.getElementById('asstCopyBtn');
    btn.textContent = '✓ Copied'; btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '⎘ Copy'; btn.classList.remove('copied'); }, 1600);
  });
}
function downloadAsstOutput() {
  const blob = new Blob([asstOutputText], { type: 'text/plain' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'ai_output.py'; a.click();
}
function clearAsstOutput() {
  asstOutputText = '';
  document.getElementById('asstOutput').style.display = 'none';
  document.getElementById('asstOutputFooter').style.display = 'none';
  document.getElementById('asstMetaBar').style.display = 'none';
  document.getElementById('asstCopyBtn').style.display = 'none';
  document.getElementById('asstDownloadBtn').style.display = 'none';
  document.getElementById('asstClearBtn').style.display = 'none';
  document.getElementById('asstEmptyState').style.display = 'flex';
  setAsstOutputDot('var(--muted2)');
  document.getElementById('asstOutputLabel').textContent = 'Output';
}
function sendToReview() {
  if (!asstOutputText) return;
  document.getElementById('codeInput').value = asstOutputText;
  syncLines(document.getElementById('codeInput'));
  updateStats(document.getElementById('codeInput'));
  switchMode('review');
}
async function loadAsstHistoryFromServer() {
  try {
    const resp = await fetch('/api/history/assistant?limit=6');
    const data = await resp.json();
    asstHistory = data.entries || [];
  } catch (err) {
    console.warn('Failed to load assistant history from server:', err);
    asstHistory = [];
  }
  renderAsstHistory();
}
function renderAsstHistory() {
  const strip = document.getElementById('asstHistoryStrip');
  strip.style.display = asstHistory.length ? 'flex' : 'none';
  strip.innerHTML = asstHistory.map(h => {
    const label = (h.prompt || '').slice(0, 40) + ((h.prompt || '').length > 40 ? '…' : '');
    return `<div class="asst-history-chip" onclick="restoreAsstHistory(${h.id})" title="${h.created_at || ''}">${label.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>`;
  }).join('');
}
function restoreAsstHistory(id) {
  const h = asstHistory.find(e => e.id === id);
  if (!h) return;
  asstOutputText = h.result;
  const outEl = document.getElementById('asstOutput');
  outEl.textContent = h.result;
  outEl.style.display = 'block';
  document.getElementById('asstOutputFooter').style.display = 'flex';
  document.getElementById('asstMetaBar').style.display = 'flex';
  document.getElementById('asstCopyBtn').style.display = '';
  document.getElementById('asstDownloadBtn').style.display = '';
  document.getElementById('asstClearBtn').style.display = '';
  document.getElementById('asstEmptyState').style.display = 'none';
  document.getElementById('asstOutputLabel').textContent = 'Restored Output';
  setAsstOutputDot('var(--purple)');
}
loadAsstHistoryFromServer();

// Ctrl+Enter to submit in assistant mode
document.addEventListener('keydown', e => {
  if (e.ctrlKey && e.key === 'Enter') {
    const asst = document.getElementById('page-assistant');
    if (asst && (asst.style.display === 'flex' || asst.classList.contains('active'))) {
      runAssistant();
    }
  }
});

// ── Side modals ──────────────────────────────────────
function openSideModal(id) {
  closeAllSideModals();
  document.getElementById(id).classList.add('open');
  document.getElementById('sideBackdrop').classList.add('open');
  // Mark sidebar icon active if applicable
  const iconMap = { sideHistory: 'sb-history' };
  if (iconMap[id]) {
    document.querySelectorAll('.sidebar-icon[id^="sb-"]').forEach(el => el.classList.remove('active'));
    document.getElementById(iconMap[id]).classList.add('active');
  }
}
function closeSideModal(id) {
  document.getElementById(id).classList.remove('open');
  document.getElementById('sideBackdrop').classList.remove('open');
  // Restore analyse as active
  document.querySelectorAll('.sidebar-icon[id^="sb-"]').forEach(el => el.classList.remove('active'));
  document.getElementById('sb-analyse').classList.add('active');
}
function closeAllSideModals() {
  document.querySelectorAll('.side-modal').forEach(m => m.classList.remove('open'));
  document.getElementById('sideBackdrop').classList.remove('open');
}

// ── Language switching ───────────────────────────────
const langExt = { python:'py', java:'java', javascript:'js', c:'c' };
function setLang(lang) {
  document.getElementById('langHidden').value = lang;
  ['python','java','js','c'].forEach(l => {
    const id = 'lang-' + l;
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', (l === 'js' ? 'javascript' : l) === lang);
  });
  const ext = langExt[lang] || 'txt';
  document.getElementById('fileTagLabel').textContent = 'main.' + ext;
}

// ── Gauge chart ──────────────────────────────────────
const score = window.__ANCHOR_SCORE__ ?? 0;
const gColor = score >= 85 ? '#84cc16' : score >= 50 ? '#f59e0b' : score > 0 ? '#f43f5e' : '#334155';
const gBg    = document.documentElement.getAttribute('data-theme') === 'light' ? '#e2e8f0' : '#1e293b';
const gaugeCtx = document.getElementById('gaugeChart');
if (gaugeCtx) {
  new Chart(gaugeCtx, {
    type: 'doughnut',
    data: { datasets:[{
      data: [score || 1, 100 - (score || 1)],
      backgroundColor: [score > 0 ? gColor : '#334155', gBg],
      borderWidth: 0,
      borderRadius: 4
    }] },
    options: {
      cutout: '76%',
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      animation: { duration: 1000, easing: 'easeInOutQuart' }
    }
  });
}

// ── Line numbers ─────────────────────────────────────
function syncLines(ta) {
  const n = ta.value.split('\n').length;
  let s = '';
  for (let i = 1; i <= n + 1; i++) s += i + '\n';
  document.getElementById('lineNums').textContent = s;
}
function updateStats(ta) {
  const lines = ta.value.split('\n').length;
  const chars = ta.value.length;
  document.getElementById('codeStats').textContent = lines + ' ln · ' + chars + ' ch';
}
const ta = document.getElementById('codeInput');
if (ta) { syncLines(ta); updateStats(ta); }

// ── Ctrl+Enter to analyze, Ctrl+K to clear ──────────
if (ta) {
  ta.addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      document.getElementById('mainForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }
    if (e.ctrlKey && e.key === 'k') {
      e.preventDefault();
      clearCode();
    }
  });
}

// ── ANALYZING OVERLAY ────────────────────────────────
const overlaySteps = [
  'Parsing syntax tree...',
  'Running pattern detection...',
  'Checking security vulnerabilities...',
  'Calling neural engine...',
  'Generating corrected code...',
  'Calculating health score...',
];
let overlayInterval;
function showAnalyzeOverlay(e) {
  const code = document.getElementById('codeInput').value.trim();
  if (!code) return;
  const overlay = document.getElementById('analyzeOverlay');
  overlay.classList.add('show');
  document.getElementById('analyzeBtn').disabled = true;
  let step = 0, pct = 0;
  document.getElementById('overlayBar').style.width = '0%';
  document.getElementById('overlayStep').textContent = overlaySteps[0];
  overlayInterval = setInterval(() => {
    step = Math.min(step + 1, overlaySteps.length - 1);
    pct  = Math.min(pct + (100 / overlaySteps.length), 92);
    document.getElementById('overlayStep').textContent = overlaySteps[step];
    document.getElementById('overlayBar').style.width = pct + '%';
  }, 600);
  // History is now saved server-side, AFTER the result exists (so it
  // actually records a score) — see app.py's index() route. Nothing to do
  // here anymore; the history panel refreshes itself from the server on
  // the next page load, which happens right after this form submits.
}

// ── History (server-side, via /api/history/analyze) ────
// Replaces the old localStorage-only version, which saved BEFORE the
// result existed (so it never actually recorded a score) and truncated
// code to 120 chars even for the "restore" action, so loading old history
// gave you back broken/incomplete code.
let analysisHistory = [];
async function loadAnalyzeHistoryFromServer() {
  try {
    const resp = await fetch('/api/history/analyze?limit=20');
    const data = await resp.json();
    analysisHistory = data.entries || [];
  } catch (err) {
    console.warn('Failed to load analyze history from server:', err);
    analysisHistory = [];
  }
  renderHistory();
}
function renderHistory() {
  const body = document.getElementById('historyBody');
  if (!analysisHistory.length) {
    body.innerHTML = '<div class="modal-empty"><div class="me-icon">⏱</div>No analyses yet.</div>';
    return;
  }
  body.innerHTML = analysisHistory.map(h => {
    const preview = (h.code || '').slice(0, 120).replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const score = (h.score !== null && h.score !== undefined) ? `${h.score}/100` : '—';
    return `
    <div class="history-item" onclick="loadHistory(${h.id})">
      <div class="hi-lang">${(h.lang || '').toUpperCase()} · ${score}</div>
      <div class="hi-code">${preview}</div>
      <div class="hi-meta"><span>${h.created_at || ''}</span>
        <span onclick="event.stopPropagation(); deleteHistoryEntry(${h.id})" style="cursor:pointer" title="Delete">🗑</span>
      </div>
    </div>`;
  }).join('');
}
function loadHistory(id) {
  const h = analysisHistory.find(e => e.id === id);
  if (!h) return;
  document.getElementById('codeInput').value = h.code;  // full code, not a truncated preview
  syncLines(document.getElementById('codeInput'));
  updateStats(document.getElementById('codeInput'));
  setLang(h.lang);
  closeAllSideModals();
}
async function deleteHistoryEntry(id) {
  try {
    await fetch(`/api/history/analyze/${id}`, { method: 'DELETE' });
  } catch (err) { console.warn('Failed to delete history entry:', err); }
  loadAnalyzeHistoryFromServer();
}
async function clearAnalyzeHistory() {
  try {
    await fetch('/api/history/analyze', { method: 'DELETE' });
  } catch (err) { console.warn('Failed to clear history:', err); }
  loadAnalyzeHistoryFromServer();
}
loadAnalyzeHistoryFromServer();

// ── Copy & Download ───────────────────────────────────
function toggleDiffView() {
  const codeEl = document.getElementById('correctedCode');
  const diffEl = document.getElementById('diffView');
  const btn = document.getElementById('diffToggleBtn');
  if (!codeEl || !diffEl) return;
  const showingDiff = diffEl.style.display !== 'none';
  diffEl.style.display = showingDiff ? 'none' : 'block';
  codeEl.style.display = showingDiff ? 'block' : 'none';
  btn.textContent = showingDiff ? '⇄ Diff View' : '⇄ Code View';
  btn.classList.toggle('active', !showingDiff);
}
function copyCode() {
  const diffEl = document.getElementById('diffView');
  const showingDiff = diffEl && diffEl.style.display !== 'none';
  const el = document.getElementById(showingDiff ? 'diffView' : 'correctedCode');
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✓ Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '⎘ Copy'; btn.classList.remove('copied'); }, 2000);
  });
}
function downloadCode() {
  const el = document.getElementById('correctedCode');
  if (!el) return;
  const lang = document.getElementById('langHidden').value;
  const ext  = { python:'py', java:'java', javascript:'js' }[lang] || 'txt';
  const blob = new Blob([el.innerText], { type:'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `corrected_code.${ext}`;
  a.click();
}
function clearCode() {
  const ta = document.getElementById('codeInput');
  ta.value = '';
  syncLines(ta);
  updateStats(ta);
}

// ── Refactor card actions ────────────────────────────
const refactorTips = {
  decouple: {
    title: '🔗 Decouple API Logic',
    what: 'Separates route definitions from business logic so each can change independently without breaking the other.',
    why: 'Tightly coupled code is hard to test, reuse, and maintain. When routes and logic are mixed, a small change can break everything.',
    steps: [
      'Move all URL/route strings into a constants dict at the top of the file.',
      'Create pure service functions that handle logic — routes just call them.',
      'Pass dependencies (DB, config) as arguments instead of importing globals.',
      'Each function should do one thing: validate, process, or respond.',
    ],
    example: '# BEFORE — logic mixed with routing\n@app.route("/users")\ndef get_users():\n    db = connect_db()\n    return jsonify(db.query("SELECT * FROM users"))\n\n# AFTER — decoupled\nROUTES = {"users": "/users"}\n\ndef fetch_users(db):\n    return db.query("SELECT * FROM users")\n\n@app.route(ROUTES["users"])\ndef get_users():\n    return jsonify(fetch_users(get_db()))',
  },
  lazy: {
    title: '✦ Lazy Load Modules',
    what: 'Delays importing heavy libraries until they are actually needed at runtime, not at startup.',
    why: 'Top-level imports of large libraries (torch, sklearn, numpy) run every cold start, slowing down every request — even ones that never use ML.',
    steps: [
      'Move heavy imports inside the function that uses them.',
      'Cache the module in a module-level variable after first load.',
      'Use importlib.import_module() for fully dynamic loading.',
      'Apply to any import that adds >50ms to startup time.',
    ],
    example: '# BEFORE — slow startup, always loads torch\nimport torch\n\ndef predict(data):\n    return torch.tensor(data)\n\n# AFTER — fast startup, loads only when called\n_torch = None\n\ndef predict(data):\n    global _torch\n    if _torch is None:\n        import torch\n        _torch = torch\n    return _torch.tensor(data)',
  },
  sanitize: {
    title: '🛡 Sanitize Inputs',
    what: 'Validates and cleans all user-supplied data before it touches your database, shell commands, or HTML output.',
    why: 'SQL injection, XSS, and command injection are the #1 cause of data breaches. All exploit unsanitized user input.',
    steps: [
      'Never concatenate user input into SQL — use parameterized queries.',
      'Use allowlists (accept known-good) not denylists (block known-bad).',
      'Escape HTML characters before rendering any user content.',
      'Use subprocess.run(list, shell=False) instead of shell=True.',
    ],
    example: '# BEFORE — SQL injection risk\nquery = "SELECT * FROM users WHERE name=\'" + name + "\'"\ncursor.execute(query)\n\n# BEFORE — XSS risk\nreturn f"<h1>Hello {username}</h1>"\n\n# AFTER — safe parameterized query\ncursor.execute("SELECT * FROM users WHERE name=%s", (name,))\n\n# AFTER — escaped HTML output\nfrom html import escape\nreturn f"<h1>Hello {escape(username)}</h1>"',
  },
};

function applyRefactor(type) {
  if (type === 'convert') { openConvert(); return; }
  const tip = refactorTips[type];
  if (!tip) return;

  document.getElementById('tipPanelTitle').textContent = tip.title;

  const stepsHtml = tip.steps.map(s =>
    `<div class="tip-step"><span class="tip-step-bullet">›</span><span style="font-size:13px;color:var(--text2);line-height:1.5">${s}</span></div>`
  ).join('');

  document.getElementById('tipPanelBody').innerHTML = `
    <div class="tip-section-label">What it does</div>
    <div class="tip-what">${tip.what}</div>
    <div class="tip-section-label">Why it matters</div>
    <div class="tip-why">${tip.why}</div>
    <div class="tip-section-label">How to apply</div>
    ${stepsHtml}
    <div class="tip-section-label">Example</div>
    <div class="tip-code-block">${tip.example}</div>
    <button class="tip-analyze-btn" onclick="runAndClose()">⚡ Analyze My Code Now</button>
  `;
  openSideModal('sideRefactorTip');
}

function runAndClose() {
  const code = document.getElementById('codeInput').value.trim();
  if (!code) { alert('Paste some code in the editor first.'); return; }
  closeSideModal('sideRefactorTip');
  document.getElementById('mainForm').submit();
}

// ── Mobile nav ────────────────────────────────────────
function mobileNav(section) {
  // Update active state
  document.querySelectorAll('.mobile-nav-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById('mnav-' + section);
  if (btn) btn.classList.add('active');

  // Close any open side modals first
  closeAllSideModals();

  if (section === 'analyse') {
    // Nothing to open — just close panels
  } else if (section === 'history') {
    openSideModal('sideHistory');
  } else if (section === 'reports') {
    openSideModal('sideReports');
  } else if (section === 'docs') {
    openSideModal('sideDocs');
  } else if (section === 'settings') {
    openSideModal('sideSettings');
  }
}

// ── Convert modal ─────────────────────────────────────
function openConvert() {
  const lang = document.getElementById('langHidden').value;
  document.getElementById('convertFrom').value = lang;
  document.getElementById('convertStatus').classList.remove('show');
  document.getElementById('convertModal').classList.add('open');
}
function closeConvert() {
  document.getElementById('convertModal').classList.remove('open');
}
async function doConvert() {
  const from = document.getElementById('convertFrom').value;
  const to   = document.getElementById('convertTo').value;
  const code = document.getElementById('codeInput').value.trim();
  const status = document.getElementById('convertStatus');
  const btn = document.getElementById('convertBtn');

  if (!code) {
    status.style.color = 'var(--rose)';
    status.textContent = '⚠ Please paste some code in the editor first.';
    status.classList.add('show');
    return;
  }
  if (from === to) {
    status.style.color = 'var(--amber)';
    status.textContent = '⚠ Source and target language are the same.';
    status.classList.add('show');
    return;
  }

  btn.disabled = true;
  btn.textContent = '⟳ Converting...';
  status.style.color = 'var(--sky)';
  status.textContent = `Converting ${from} → ${to}...`;
  status.classList.add('show');

  try {
    const resp = await fetch('/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, from_lang: from, to_lang: to })
    });
    const data = await resp.json();
    if (data.converted) {
      document.getElementById('codeInput').value = data.converted;
      syncLines(document.getElementById('codeInput'));
      updateStats(document.getElementById('codeInput'));
      setLang(to === 'typescript' ? 'javascript' : (to === 'cpp' || to === 'go' ? 'python' : to));
      document.getElementById('langHidden').value = to;
      status.style.color = 'var(--lime)';
      status.textContent = `✅ Converted successfully from ${from} to ${to}!`;
      setTimeout(() => closeConvert(), 1400);
    } else {
      status.style.color = 'var(--rose)';
      status.textContent = '❌ Conversion failed: ' + (data.error || 'Unknown error');
    }
  } catch(err) {
    status.style.color = 'var(--rose)';
    status.textContent = '❌ Request failed — check server connection.';
  }
  btn.disabled = false;
  btn.textContent = '⚡ Convert Code';
}

// Close convert modal on backdrop click
document.getElementById('convertModal').addEventListener('click', function(e) {
  if (e.target === this) closeConvert();
});