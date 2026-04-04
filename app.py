from flask import Flask, render_template_string, request
from code_analyzer import analyze_logic

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ANCHOR ELITE | Neural Code Review</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --navy: #020617; --sky: #0ea5e9; --rose: #f43f5e;
    --lime: #84cc16; --amber: #f59e0b; --slate: #1e293b;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--navy);
    color: #f8fafc;
    font-family: 'Syne', sans-serif;
    min-height: 100vh;
    overflow-x: hidden;
  }
  .mono { font-family: 'JetBrains Mono', monospace; }
  .glass {
    background: rgba(15,23,42,0.75);
    backdrop-filter: blur(24px);
    border: 1px solid rgba(255,255,255,0.08);
  }
  .critical { border-color: var(--rose) !important; box-shadow: 0 0 40px rgba(244,63,94,0.15); }
  .good     { border-color: var(--lime) !important; box-shadow: 0 0 40px rgba(132,204,22,0.1); }
  .scrollbox {
    overflow-y: auto;
    max-height: 280px;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .scrollbox::-webkit-scrollbar { width: 4px; }
  .scrollbox::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
  textarea:focus { outline: none; }
  .copy-btn {
    position: absolute; top: 12px; right: 12px;
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    color: #94a3b8; font-size: 11px;
    padding: 4px 10px; border-radius: 6px; cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    transition: all .2s;
  }
  .copy-btn:hover { background: rgba(255,255,255,0.15); color: #f8fafc; }
  .copy-btn.copied { background: rgba(132,204,22,0.2); border-color: #84cc16; color: #84cc16; }
  .severity-badge {
    display: inline-block; padding: 1px 8px;
    border-radius: 9999px; font-size: 10px; font-weight: 700;
    letter-spacing: .05em; text-transform: uppercase;
  }
  .sev-high   { background: rgba(244,63,94,.2);  color: #f43f5e; }
  .sev-med    { background: rgba(245,158,11,.2); color: #f59e0b; }
  .sev-low    { background: rgba(132,204,22,.2); color: #84cc16; }
  select { appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2394a3b8'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 12px center; background-size: 16px; padding-right: 36px !important; }
  @media (max-width: 1200px) { .layout { flex-direction: column; } }
</style>
</head>
<body class="p-4 md:p-6">

<!-- ─── Header ─────────────────────────────────────────── -->
<header class="mb-6 flex items-center justify-between">
  <div>
    <h1 class="text-2xl font-extrabold tracking-tight">
      ANCHOR<span class="text-sky-400">.ELITE</span>
    </h1>
    <p class="text-slate-500 text-xs mono mt-1">Neural Code Review System v2</p>
  </div>
  <div class="flex gap-2 items-center">
    <span class="severity-badge sev-high">🔴 Critical</span>
    <span class="severity-badge sev-med">🟡 Moderate</span>
    <span class="severity-badge sev-low">🔵 Minor</span>
  </div>
</header>

<!-- ─── Main layout ─────────────────────────────────────── -->
<div class="layout flex gap-4">

  <!-- LEFT: Input + controls -->
  <div class="flex flex-col gap-4" style="flex:1.2;min-width:0">

    <!-- Language + score summary -->
    <div class="glass rounded-2xl p-5 flex items-center gap-4 {% if result.score > 0 %}{% if result.score < 50 %}critical{% else %}good{% endif %}{% endif %}">
      <form method="POST" class="flex-1 flex gap-3 items-center">
        <div class="flex flex-col gap-1 flex-1">
          <label class="text-[10px] text-slate-500 mono uppercase tracking-widest">Language</label>
          <select name="lang" onchange="this.form.submit()"
            class="bg-slate-900 border border-white/10 p-3 rounded-xl text-sm mono text-sky-300 cursor-pointer">
            <option value="python"     {% if lang=='python' %}selected{% endif %}>🐍 Python</option>
            <option value="java"       {% if lang=='java' %}selected{% endif %}>☕ Java</option>
            <option value="javascript" {% if lang=='javascript' %}selected{% endif %}>🟨 JavaScript</option>
          </select>
        </div>
        <input type="hidden" name="code" value="{{ code | e }}">
      </form>
      <div class="text-right">
        <div class="text-4xl font-extrabold {% if result.score < 50 and result.score > 0 %}text-rose-400{% elif result.score >= 85 %}text-lime-400{% else %}text-amber-400{% endif %}">
          {{ result.score }}
        </div>
        <div class="text-[10px] text-slate-500 mono uppercase tracking-widest">Score</div>
      </div>
      <canvas id="scoreChart" width="80" height="80"></canvas>
    </div>

    <!-- Code input -->
    <div class="glass rounded-2xl flex-1 flex flex-col overflow-hidden">
      <div class="px-5 pt-4 pb-2 flex items-center justify-between border-b border-white/5">
        <span class="text-[10px] mono text-slate-500 uppercase tracking-widest">Input Code</span>
        <span class="mono text-[10px] text-slate-600">{{ result.lines }} lines · {{ result.chars }} chars</span>
      </div>
      <form method="POST" class="flex-1 flex flex-col">
        <input type="hidden" name="lang" value="{{ lang }}">
        <textarea name="code" id="codeInput"
          class="flex-1 bg-transparent px-5 py-4 text-sm mono text-sky-100 resize-none placeholder-slate-700 min-h-[300px]"
          placeholder="// Paste your code here and click Analyse...&#10;// Supports Python, Java, and JavaScript">{{ code }}</textarea>
        <div class="p-4 flex gap-3">
          <button type="submit"
            class="flex-1 bg-sky-600 hover:bg-sky-500 text-white font-bold text-xs mono uppercase tracking-widest py-4 rounded-xl transition-all">
            ⚡ Analyse Code
          </button>
          <button type="button" onclick="clearCode()"
            class="bg-slate-800 hover:bg-slate-700 text-slate-400 font-bold text-xs mono uppercase px-6 rounded-xl transition-all">
            Clear
          </button>
        </div>
      </form>
    </div>

    <!-- Metadata row -->
    <div class="grid grid-cols-3 gap-3">
      <div class="glass rounded-xl p-4 text-center">
        <div class="text-xl font-extrabold text-sky-400 mono">{{ result.lines }}</div>
        <div class="text-[10px] text-slate-500 uppercase tracking-widest mt-1">Lines</div>
      </div>
      <div class="glass rounded-xl p-4 text-center">
        <div class="text-xl font-extrabold text-sky-400 mono">{{ result.chars }}</div>
        <div class="text-[10px] text-slate-500 uppercase tracking-widest mt-1">Chars</div>
      </div>
      <div class="glass rounded-xl p-4 text-center">
        <div class="text-xl font-extrabold {% if result.score < 50 and result.score > 0 %}text-rose-400{% else %}text-lime-400{% endif %} mono">
          {{ result.confidence }}
        </div>
        <div class="text-[10px] text-slate-500 uppercase tracking-widest mt-1">Confidence</div>
      </div>
    </div>

  </div><!-- /LEFT -->

  <!-- RIGHT: Results -->
  <div class="flex flex-col gap-4" style="flex:1.8;min-width:0">

    <!-- Verdict banner -->
    <div class="glass rounded-2xl p-5 flex items-center gap-4
      {% if result.score < 50 and result.score > 0 %}critical{% elif result.score >= 85 and result.score > 0 %}good{% endif %}">
      <div class="text-2xl">
        {% if result.score == 0 %}⏳
        {% elif result.score >= 85 %}✅
        {% elif result.score >= 50 %}⚠️
        {% else %}🚨
        {% endif %}
      </div>
      <div>
        <div class="text-sm font-bold">{{ result.msg }}</div>
        <div class="text-[10px] text-slate-500 mono mt-1">
          Stability index · {{ lang | upper }} engine
        </div>
      </div>
    </div>

    <!-- Fault location -->
    <div class="glass rounded-2xl flex flex-col overflow-hidden {% if result.score < 50 and result.score > 0 %}critical{% endif %}">
      <div class="px-5 pt-4 pb-2 border-b border-white/5 flex items-center justify-between">
        <span class="text-[10px] mono text-rose-400 uppercase tracking-widest font-bold">❌ Fault Location &amp; Explanation</span>
      </div>
      <div class="scrollbox mono text-[11px] text-rose-200 p-5 leading-relaxed" style="min-height:180px">
        {{ result.old_line if result.old_line else '— No faults detected —' }}
      </div>
    </div>

    <!-- Corrected code with COPY button -->
    <div class="glass rounded-2xl flex flex-col overflow-hidden flex-1">
      <div class="px-5 pt-4 pb-2 border-b border-white/5 flex items-center justify-between">
        <span class="text-[10px] mono text-lime-400 uppercase tracking-widest font-bold">✅ Full Corrected Code — Ready to Use</span>
      </div>
      <div class="relative flex-1">
        <button class="copy-btn" id="copyBtn" onclick="copyCode()">⎘ Copy</button>
        <div id="correctedCode"
          class="scrollbox mono text-[12px] text-lime-100 p-5 leading-relaxed"
          style="min-height:220px">{{ result.full_code if result.full_code else '— Submit code to see corrected version —' }}</div>
      </div>
      {% if result.full_code %}
      <div class="px-5 pb-4">
        <button onclick="downloadCode()"
          class="w-full bg-lime-700 hover:bg-lime-600 text-white font-bold text-xs mono uppercase tracking-widest py-3 rounded-xl transition-all">
          ⬇ Download Fixed Code
        </button>
      </div>
      {% endif %}
    </div>

  </div><!-- /RIGHT -->

</div><!-- /layout -->

<script>
// ── Chart ────────────────────────────────────────────
const score = {{ result.score }};
const color = score >= 85 ? '#84cc16' : score >= 50 ? '#f59e0b' : score > 0 ? '#f43f5e' : '#1e293b';
new Chart(document.getElementById('scoreChart'), {
  type: 'doughnut',
  data: { datasets: [{ data: [score, 100 - score],
    backgroundColor: [color, '#0f172a'], borderWidth: 0, borderRadius: 10 }] },
  options: { cutout: '75%', plugins: { legend: { display: false } },
    animation: { duration: 800, easing: 'easeInOutQuart' } }
});

// ── Copy corrected code ──────────────────────────────
function copyCode() {
  const text = document.getElementById('correctedCode').innerText;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copyBtn');
    btn.textContent = '✓ Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '⎘ Copy'; btn.classList.remove('copied'); }, 2000);
  });
}

// ── Download fixed code ──────────────────────────────
function downloadCode() {
  const text = document.getElementById('correctedCode').innerText;
  const lang = '{{ lang }}';
  const ext  = { python: 'py', java: 'java', javascript: 'js' }[lang] || 'txt';
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `corrected_code.${ext}`;
  a.click();
}

// ── Clear input ──────────────────────────────────────
function clearCode() {
  document.getElementById('codeInput').value = '';
}

// ── Keyboard shortcut: Ctrl+Enter to submit ──────────
document.getElementById('codeInput').addEventListener('keydown', e => {
  if (e.ctrlKey && e.key === 'Enter') e.target.closest('form').submit();
});
</script>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    code = request.form.get("code", "")
    lang = request.form.get("lang", "python")
    result = {
        "score": 0, "confidence": "0%",
        "msg": "Paste code ab ove and click Analyse.",
        "old_line": "", "full_code": "", "lines": 0, "chars": 0
    }
    if request.method == "POST" and code.strip():
        result = analyze_logic(code, lang)
    return render_template_string(HTML, code=code, lang=lang, result=result)

if __name__ == "__main__":
    app.run(debug=True)
