from flask import Flask, render_template_string, request, jsonify
from code_analyzer import analyze_logic
import re, os

app = Flask(__name__)

HTML = r"""
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="google-site-verification" content="36sRSLEbYk3ZaYUam-VCQzh9aazXBdnGXtfa9RdxAME" />
<link rel="icon" href="/static/favicon.ico" type="image/x-icon">
<link rel="shortcut icon" href="/static/favicon.ico">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Anchor Elite AI | Neural Code Review</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
/* ══════════════════════════════════════════════════════
   THEME VARIABLES
══════════════════════════════════════════════════════ */
[data-theme="dark"] {
  --bg:        #0d0d12;
  --surface:   #13131a;
  --surface2:  #1a1a24;
  --surface3:  #22222f;
  --border:    rgba(255,255,255,0.07);
  --border2:   rgba(255,255,255,0.12);
  --text:      #e2e8f0;
  --text2:     #94a3b8;
  --muted:     #64748b;
  --muted2:    #475569;
  --code-color:#38bdf8;
  --overlay:   rgba(0,0,0,0.85);
}
[data-theme="light"] {
  --bg:        #f1f5f9;
  --surface:   #ffffff;
  --surface2:  #f8fafc;
  --surface3:  #e2e8f0;
  --border:    rgba(0,0,0,0.08);
  --border2:   rgba(0,0,0,0.15);
  --text:      #0f172a;
  --text2:     #475569;
  --muted:     #94a3b8;
  --muted2:    #cbd5e1;
  --code-color:#0369a1;
  --overlay:   rgba(255,255,255,0.9);
}
:root {
  --purple:       #a855f7;
  --purple-dim:   rgba(168,85,247,0.15);
  --purple-bright:#c084fc;
  --rose:         #f43f5e;
  --lime:         #84cc16;
  --amber:        #f59e0b;
  --sky:          #38bdf8;
}

/* ══════════════════════════════════════════════════════
   RESET & BASE
══════════════════════════════════════════════════════ */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', sans-serif;
  height: 100vh;
  display: flex;
  overflow: hidden;
  transition: background .3s, color .3s;
}
.mono { font-family: 'JetBrains Mono', monospace; }

/* ══════════════════════════════════════════════════════
   SIDEBAR
══════════════════════════════════════════════════════ */
.sidebar {
  width: 56px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; align-items: center;
  padding: 14px 0; gap: 6px; flex-shrink: 0; z-index: 10;
  transition: background .3s, border-color .3s;
}
.sidebar-logo {
  width: 36px; height: 36px;
  background: var(--purple-dim);
  border: 1px solid rgba(168,85,247,.35);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 10px; color: var(--purple); font-size: 16px;
  cursor: pointer;
}
.sidebar-icon {
  width: 36px; height: 36px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); cursor: pointer;
  transition: all .2s; font-size: 15px;
  border: 1px solid transparent;
  position: relative;
}
.sidebar-icon:hover { background: var(--surface2); color: var(--text); }
.sidebar-icon.active { background: var(--purple-dim); color: var(--purple); border-color: rgba(168,85,247,.3); }
/* Tooltip */
.sidebar-icon[title]:hover::after {
  content: attr(title);
  position: absolute; left: 46px; top: 50%; transform: translateY(-50%);
  background: var(--surface3); border: 1px solid var(--border2);
  color: var(--text); font-size: 11px; font-weight: 500;
  padding: 4px 9px; border-radius: 6px; white-space: nowrap;
  z-index: 999; pointer-events: none;
}
.sidebar-divider { width: 24px; height: 1px; background: var(--border); margin: 6px 0; }
.sidebar-bottom { margin-top: auto; display: flex; flex-direction: column; gap: 6px; align-items: center; }

/* Theme toggle */
.theme-toggle {
  width: 36px; height: 20px;
  background: var(--surface3);
  border: 1px solid var(--border2);
  border-radius: 20px; position: relative;
  cursor: pointer; transition: all .3s;
}
.theme-toggle::after {
  content: ''; position: absolute;
  top: 2px; left: 2px;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: var(--muted);
  transition: all .3s;
}
[data-theme="light"] .theme-toggle { background: var(--purple-dim); border-color: var(--purple); }
[data-theme="light"] .theme-toggle::after { left: 18px; background: var(--purple); }
.theme-icon { font-size: 14px; cursor: pointer; color: var(--muted); transition: color .2s; }
.theme-icon:hover { color: var(--text); }

/* ══════════════════════════════════════════════════════
   TOPBAR
══════════════════════════════════════════════════════ */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.topbar {
  height: 52px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 18px; gap: 10px; flex-shrink: 0;
  transition: background .3s, border-color .3s;
}
.topbar-logo { font-size: 15px; font-weight: 800; color: var(--text); margin-right: 6px; letter-spacing: -.02em; }
.topbar-logo span { color: var(--purple); }
.sep { width: 1px; height: 20px; background: var(--border2); flex-shrink: 0; }

/* Language pills */
.lang-group { display: flex; gap: 2px; }
.lang-btn {
  padding: 5px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  cursor: pointer; transition: all .2s; border: none; background: none;
  color: var(--muted); font-family: 'Inter', sans-serif;
}
.lang-btn.active { background: var(--purple-dim); color: var(--purple-bright); border: 1px solid rgba(168,85,247,.25); }
.lang-btn:not(.active):hover { color: var(--text); background: var(--surface2); }

/* Code convert button */
.convert-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 8px;
  background: rgba(56,189,248,.1); border: 1px solid rgba(56,189,248,.25);
  color: var(--sky); font-size: 12px; font-weight: 600;
  cursor: pointer; transition: all .2s; font-family: 'Inter', sans-serif;
}
.convert-btn:hover { background: rgba(56,189,248,.22); border-color: rgba(56,189,248,.45); }

.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.icon-btn {
  width: 32px; height: 32px; border-radius: 8px;
  background: var(--surface2); border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); cursor: pointer; transition: all .2s; font-size: 14px;
}
.icon-btn:hover { color: var(--text); background: var(--surface3); }
.avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: linear-gradient(135deg, var(--purple) 0%, #6366f1 100%);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: white; cursor: pointer;
}

/* ══════════════════════════════════════════════════════
   CONTENT / SCROLLBAR
══════════════════════════════════════════════════════ */
.content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.content::-webkit-scrollbar { width: 4px; }
.content::-webkit-scrollbar-thumb { background: rgba(128,128,128,.2); border-radius: 4px; }

/* ══════════════════════════════════════════════════════
   ANALYSE PAGE — fills all remaining vertical space
══════════════════════════════════════════════════════ */
.analyse-page {
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 12px;
  flex: 1; overflow: hidden; min-height: 0;
}

/* ── Stats row ── */
.stats-row { display: flex; gap: 10px; flex-shrink: 0; }
.health-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 12px 16px; display: flex; align-items: center; gap: 12px;
  width: 240px; flex-shrink: 0; transition: background .3s, border-color .3s;
}
.health-gauge-wrap { position: relative; width: 64px; height: 64px; flex-shrink: 0; }
.score-num { font-size: 26px; font-weight: 700; font-family: 'JetBrains Mono', monospace; line-height: 1; color: var(--text); }
.score-label { font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin-top: 3px; }
.score-status { font-size: 11px; margin-top: 5px; font-weight: 600; }
.status-good { color: var(--lime); }
.status-warn { color: var(--amber); }
.status-crit { color: var(--rose); }

.stat-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  padding: 12px 16px; flex: 1; display: flex; flex-direction: column; justify-content: space-between;
  transition: background .3s, border-color .3s;
}
.stat-label { font-size: 9px; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); display: flex; align-items: center; gap: 5px; }
.stat-num { font-size: 26px; font-weight: 700; color: var(--text); font-family: 'JetBrains Mono', monospace; margin-top: 6px; }

/* ── Panels row — takes all remaining space ── */
.panels-row {
  display: flex; gap: 12px;
  flex: 1; min-height: 0; /* CRITICAL: allows children to shrink */
}
.panel {
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  display: flex; flex-direction: column; overflow: hidden; flex: 1;
  transition: background .3s, border-color .3s;
  min-height: 0;
}
.panel-header {
  padding: 9px 14px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
}
.panel-title { font-size: 11px; color: var(--muted); font-weight: 500; display: flex; align-items: center; gap: 7px; }
.panel-tag {
  font-size: 10px; font-family: 'JetBrains Mono', monospace;
  background: var(--surface2); border: 1px solid var(--border);
  padding: 1px 7px; border-radius: 5px; color: var(--muted);
}

/* ── Code area fills panel ── */
.code-area {
  flex: 1; display: flex; overflow: hidden; min-height: 0;
}
.line-nums {
  padding: 10px 0 10px 10px; color: var(--muted2);
  font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 20px;
  text-align: right; user-select: none; min-width: 38px; flex-shrink: 0; overflow: hidden;
}
.code-scroll-inner { flex: 1; overflow: auto; display: flex; }
.code-scroll-inner::-webkit-scrollbar { width: 3px; height: 3px; }
.code-scroll-inner::-webkit-scrollbar-thumb { background: rgba(128,128,128,.15); border-radius: 4px; }
textarea.code-input {
  flex: 1; background: transparent; border: none; outline: none; resize: none;
  color: var(--code-color); font-family: 'JetBrains Mono', monospace;
  font-size: 12px; line-height: 20px; padding: 10px 14px 10px 8px;
  caret-color: var(--purple); width: 100%; height: 100%;
  transition: color .3s;
}
textarea.code-input::placeholder { color: var(--muted2); }

/* Input panel form fills space */
#mainForm {
  display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden;
}

/* Corrected code output */
.corrected-body {
  flex: 1; overflow-y: auto; padding: 10px 14px;
  font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 20px;
  color: var(--lime); white-space: pre-wrap; word-break: break-word;
  transition: color .3s;
}
.corrected-body::-webkit-scrollbar { width: 3px; }
.corrected-body::-webkit-scrollbar-thumb { background: rgba(132,204,22,.15); border-radius: 4px; }
.optim-badge {
  margin: 6px 14px; background: rgba(132,204,22,.07);
  border: 1px solid rgba(132,204,22,.2); border-radius: 8px;
  padding: 7px 11px; font-size: 10px; color: var(--lime); font-weight: 700;
  letter-spacing: .04em; flex-shrink: 0;
}
.optim-desc { font-size: 11px; color: var(--muted); font-weight: 400; margin-top: 3px; line-height: 1.5; font-family: 'Inter', sans-serif; }

/* Buttons */
.panel-actions { padding: 9px 12px; border-top: 1px solid var(--border); display: flex; gap: 7px; flex-shrink: 0; }
.btn { padding: 8px 16px; border-radius: 9px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all .2s; border: none; font-family: 'Inter', sans-serif; }
.btn-primary { background: var(--purple); color: white; flex: 1; }
.btn-primary:hover { background: var(--purple-bright); }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost { background: var(--surface2); border: 1px solid var(--border2); color: var(--muted); }
.btn-ghost:hover { color: var(--text); }
.btn-lime { background: rgba(132,204,22,.12); border: 1px solid rgba(132,204,22,.25); color: var(--lime); }
.btn-lime:hover { background: rgba(132,204,22,.22); }

/* Fault panel */
.fault-panel {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 14px; padding: 10px 14px; flex-shrink: 0;
  transition: background .3s, border-color .3s;
}
.fault-header { font-size: 9px; text-transform: uppercase; letter-spacing: .1em; color: var(--rose); font-weight: 700; margin-bottom: 7px; }
.fault-body {
  font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #fca5a5;
  line-height: 1.7; max-height: 90px; overflow-y: auto;
  white-space: pre-wrap; word-break: break-word;
}
[data-theme="light"] .fault-body { color: #be123c; }
.fault-body::-webkit-scrollbar { width: 3px; }
.fault-body::-webkit-scrollbar-thumb { background: rgba(244,63,94,.2); }

/* Recommended refactors */
.refactors-section { flex-shrink: 0; }
.section-label { font-size: 9px; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); font-weight: 700; margin-bottom: 8px; }
.refactors-row { display: flex; gap: 9px; }
.refactor-card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 10px 12px; flex: 1; display: flex; align-items: center; gap: 10px;
  cursor: pointer; transition: all .2s; text-decoration: none;
}
.refactor-card:hover { border-color: rgba(168,85,247,.35); background: var(--purple-dim); transform: translateY(-1px); }
.refactor-icon { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; }
.ri-purple { background: var(--purple-dim); }
.ri-amber  { background: rgba(245,158,11,.12); }
.ri-rose   { background: rgba(244,63,94,.1); }
.ri-sky    { background: rgba(56,189,248,.1); }
.refactor-info .ri-title { font-size: 12px; font-weight: 600; color: var(--text); }
.refactor-info .ri-sub   { font-size: 10px; color: var(--muted); margin-top: 1px; }
.refactor-arrow { margin-left: auto; color: var(--muted); font-size: 12px; transition: transform .2s; }
.refactor-card:hover .refactor-arrow { transform: translateX(2px); color: var(--purple); }

/* copy btn small */
.copy-btn-sm {
  padding: 3px 9px; border-radius: 6px;
  background: var(--surface2); border: 1px solid var(--border2);
  color: var(--muted); font-size: 10px; cursor: pointer;
  transition: all .2s; font-family: 'JetBrains Mono', monospace;
}
.copy-btn-sm:hover { color: var(--text); }
.copy-btn-sm.copied { background: rgba(132,204,22,.1); border-color: rgba(132,204,22,.3); color: var(--lime); }

/* empty state */
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--muted); }
.empty-state .es-icon { font-size: 28px; opacity: .4; }
.empty-state .es-txt { font-size: 12px; }

/* ══════════════════════════════════════════════════════
   ANALYZING OVERLAY
══════════════════════════════════════════════════════ */
#analyzeOverlay {
  position: fixed; inset: 0; z-index: 999;
  background: var(--overlay);
  backdrop-filter: blur(8px);
  display: none; flex-direction: column;
  align-items: center; justify-content: center; gap: 24px;
}
#analyzeOverlay.show { display: flex; }
.overlay-card {
  background: var(--surface);
  border: 1px solid var(--border2);
  border-radius: 20px; padding: 40px 48px;
  display: flex; flex-direction: column; align-items: center; gap: 20px;
  min-width: 340px; max-width: 440px;
  box-shadow: 0 24px 60px rgba(0,0,0,.4);
}
.spinner-ring { width: 64px; height: 64px; position: relative; }
.spinner-ring svg { animation: spin 1.4s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.spinner-ring circle {
  fill: none; stroke-width: 4; stroke-linecap: round;
  stroke-dasharray: 150 100;
  animation: dash 1.4s ease-in-out infinite;
}
@keyframes dash {
  0%   { stroke-dasharray: 1 200; stroke-dashoffset: 0; }
  50%  { stroke-dasharray: 100 200; stroke-dashoffset: -30px; }
  100% { stroke-dasharray: 100 200; stroke-dashoffset: -125px; }
}
.overlay-title { font-size: 17px; font-weight: 700; color: var(--text); text-align: center; }
.overlay-step  { font-size: 12px; color: var(--muted); font-family: 'JetBrains Mono', monospace; text-align: center; min-height: 16px; }
.overlay-bar-bg { width: 100%; height: 4px; background: var(--surface3); border-radius: 4px; overflow: hidden; }
.overlay-bar    { height: 100%; background: linear-gradient(90deg, var(--purple), var(--purple-bright)); border-radius: 4px; width: 0%; transition: width .4s ease; }

/* ══════════════════════════════════════════════════════
   MODAL PANELS (History, Reports, Settings, etc.)
══════════════════════════════════════════════════════ */
.side-modal {
  position: fixed; top: 0; right: -360px; width: 360px; height: 100vh;
  background: var(--surface); border-left: 1px solid var(--border2);
  z-index: 800; transition: right .3s ease;
  display: flex; flex-direction: column;
  box-shadow: -16px 0 40px rgba(0,0,0,.3);
}
.side-modal.open { right: 0; }
.side-modal-header {
  padding: 16px 18px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
}
.side-modal-title { font-size: 14px; font-weight: 700; color: var(--text); }
.side-modal-close {
  background: none; border: none; color: var(--muted); font-size: 18px;
  cursor: pointer; transition: color .2s; line-height: 1;
}
.side-modal-close:hover { color: var(--text); }
.side-modal-body { padding: 18px; flex: 1; overflow-y: auto; }
.modal-empty { text-align: center; padding: 40px 20px; color: var(--muted); font-size: 13px; }
.modal-empty .me-icon { font-size: 36px; margin-bottom: 12px; opacity: .4; }

/* History items */
.history-item {
  background: var(--surface2); border: 1px solid var(--border);
  border-radius: 10px; padding: 11px 13px; margin-bottom: 8px;
  cursor: pointer; transition: all .2s;
}
.history-item:hover { border-color: rgba(168,85,247,.3); }
.history-item .hi-lang { font-size: 10px; color: var(--purple-bright); font-weight: 700; text-transform: uppercase; }
.history-item .hi-code { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text2); margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-item .hi-meta { font-size: 10px; color: var(--muted); margin-top: 6px; display: flex; justify-content: space-between; }

/* Settings panel */
.settings-row { margin-bottom: 18px; }
.settings-label { font-size: 11px; font-weight: 700; color: var(--text2); margin-bottom: 8px; text-transform: uppercase; letter-spacing: .06em; }
.settings-option {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 12px; background: var(--surface2); border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: 5px; font-size: 13px; color: var(--text);
}
.settings-toggle {
  width: 32px; height: 18px; background: var(--surface3); border: 1px solid var(--border2);
  border-radius: 18px; position: relative; cursor: pointer; transition: all .3s;
}
.settings-toggle.on { background: var(--purple-dim); border-color: var(--purple); }
.settings-toggle::after {
  content: ''; position: absolute; top: 2px; left: 2px;
  width: 12px; height: 12px; border-radius: 50%;
  background: var(--muted); transition: all .3s;
}
.settings-toggle.on::after { left: 16px; background: var(--purple); }

/* ══════════════════════════════════════════════════════
   CONVERT MODAL
══════════════════════════════════════════════════════ */
.modal-backdrop {
  position: fixed; inset: 0; z-index: 900;
  background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
  display: none; align-items: center; justify-content: center;
}
.modal-backdrop.open { display: flex; }
.modal-card {
  background: var(--surface); border: 1px solid var(--border2);
  border-radius: 18px; padding: 28px 32px; min-width: 400px;
  box-shadow: 0 24px 60px rgba(0,0,0,.5); position: relative;
}
.modal-title { font-size: 16px; font-weight: 800; color: var(--text); margin-bottom: 6px; }
.modal-sub   { font-size: 12px; color: var(--muted); margin-bottom: 20px; }
.modal-row   { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.modal-select {
  flex: 1; background: var(--surface2); border: 1px solid var(--border2);
  color: var(--text); font-size: 13px; padding: 9px 12px;
  border-radius: 10px; outline: none; font-family: 'Inter', sans-serif;
  cursor: pointer; transition: border-color .2s;
}
.modal-select:focus { border-color: var(--purple); }
.modal-arrow { font-size: 20px; color: var(--purple); flex-shrink: 0; }
.modal-actions { display: flex; gap: 8px; margin-top: 4px; }
.modal-close { position: absolute; top: 14px; right: 16px; background: none; border: none; color: var(--muted); font-size: 20px; cursor: pointer; transition: color .2s; }
.modal-close:hover { color: var(--text); }
.convert-result {
  margin-top: 12px; padding: 10px 12px;
  background: rgba(56,189,248,.07); border: 1px solid rgba(56,189,248,.2);
  border-radius: 8px; font-size: 12px; color: var(--sky); font-family: 'JetBrains Mono', monospace;
  display: none;
}
.convert-result.show { display: block; }

/* ══════════════════════════════════════════════════════
   BACKDROP (for side modals)
══════════════════════════════════════════════════════ */
.modal-backdrop-side {
  position: fixed; inset: 0; z-index: 799;
  background: rgba(0,0,0,.4); backdrop-filter: blur(2px);
  display: none;
}
.modal-backdrop-side.open { display: block; }

/* ══════════════════════════════════════════════════════
   NOTIFICATIONS BADGE
══════════════════════════════════════════════════════ */
.notif-badge {
  position: relative;
}
.notif-badge::after {
  content: ''; position: absolute; top: 5px; right: 5px;
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--rose); border: 1px solid var(--surface);
}
</style>
</head>
<body>

<!-- ══════════════════════════════════════════════════════
     ANALYZING OVERLAY
══════════════════════════════════════════════════════ -->
<div id="analyzeOverlay">
  <div class="overlay-card">
    <div class="spinner-ring">
      <svg viewBox="25 25 50 50" width="64" height="64">
        <circle cx="50" cy="50" r="20" stroke="url(#grad)" />
        <defs>
          <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#a855f7"/>
            <stop offset="100%" stop-color="#c084fc"/>
          </linearGradient>
        </defs>
      </svg>
    </div>
    <div>
      <div class="overlay-title">Analyzing your code...</div>
      <div class="overlay-step" id="overlayStep">Initializing neural engine</div>
    </div>
    <div style="width:100%">
      <div class="overlay-bar-bg"><div class="overlay-bar" id="overlayBar"></div></div>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     CONVERT MODAL
══════════════════════════════════════════════════════ -->
<div class="modal-backdrop" id="convertModal">
  <div class="modal-card">
    <button class="modal-close" onclick="closeConvert()">✕</button>
    <div class="modal-title">⇄ Code Conversion</div>
    <div class="modal-sub">Convert your code from one language to another using AI.</div>
    <div class="modal-row">
      <select class="modal-select" id="convertFrom">
        <option value="python">🐍 Python</option>
        <option value="java">☕ Java</option>
        <option value="javascript">🟨 JavaScript</option>
        <option value="typescript">🔷 TypeScript</option>
        <option value="cpp">⚙ C++</option>
        <option value="go">🐹 Go</option>
      </select>
      <span class="modal-arrow">→</span>
      <select class="modal-select" id="convertTo">
        <option value="javascript">🟨 JavaScript</option>
        <option value="python">🐍 Python</option>
        <option value="java">☕ Java</option>
        <option value="typescript">🔷 TypeScript</option>
        <option value="cpp">⚙ C++</option>
        <option value="go">🐹 Go</option>
      </select>
    </div>
    <div id="convertStatus" class="convert-result"></div>
    <div class="modal-actions" style="margin-top:14px">
      <button class="btn btn-primary" onclick="doConvert()" id="convertBtn" style="flex:1">⚡ Convert Code</button>
      <button class="btn btn-ghost" onclick="closeConvert()">Cancel</button>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     SIDE MODAL BACKDROP
══════════════════════════════════════════════════════ -->
<div class="modal-backdrop-side" id="sideBackdrop" onclick="closeAllSideModals()"></div>

<!-- ══════════════════════════════════════════════════════
     HISTORY SIDE MODAL
══════════════════════════════════════════════════════ -->
<div class="side-modal" id="sideHistory">
  <div class="side-modal-header">
    <span class="side-modal-title">⏱ Analysis History</span>
    <button class="side-modal-close" onclick="closeSideModal('sideHistory')">✕</button>
  </div>
  <div class="side-modal-body" id="historyBody">
    <div class="modal-empty">
      <div class="me-icon">⏱</div>
      No analyses yet. Submit some code to get started.
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     REPORTS SIDE MODAL
══════════════════════════════════════════════════════ -->
<div class="side-modal" id="sideReports">
  <div class="side-modal-header">
    <span class="side-modal-title">📊 Reports</span>
    <button class="side-modal-close" onclick="closeSideModal('sideReports')">✕</button>
  </div>
  <div class="side-modal-body">
    <div class="modal-empty">
      <div class="me-icon">📊</div>
      Reports are generated after code analysis. Run an analysis to see results here.
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     DOCS SIDE MODAL
══════════════════════════════════════════════════════ -->
<div class="side-modal" id="sideDocs">
  <div class="side-modal-header">
    <span class="side-modal-title">📖 Documentation</span>
    <button class="side-modal-close" onclick="closeSideModal('sideDocs')">✕</button>
  </div>
  <div class="side-modal-body">
    <div class="settings-row">
      <div class="settings-label">Quick Reference</div>
      <div class="settings-option"><span>Paste code, select language</span><span style="color:var(--purple);font-size:11px">Step 1</span></div>
      <div class="settings-option"><span>Click ⚡ Analyze &amp; Refactor</span><span style="color:var(--purple);font-size:11px">Step 2</span></div>
      <div class="settings-option"><span>Review fixed code on the right</span><span style="color:var(--purple);font-size:11px">Step 3</span></div>
      <div class="settings-option"><span>Download or copy corrected code</span><span style="color:var(--purple);font-size:11px">Step 4</span></div>
    </div>
    <div class="settings-row">
      <div class="settings-label">Keyboard Shortcuts</div>
      <div class="settings-option"><span>Analyze code</span><span style="font-family:monospace;font-size:11px;color:var(--muted)">Ctrl+Enter</span></div>
      <div class="settings-option"><span>Clear editor</span><span style="font-family:monospace;font-size:11px;color:var(--muted)">Ctrl+K</span></div>
    </div>
    <div class="settings-row">
      <div class="settings-label">Supported Languages</div>
      <div class="settings-option"><span>🐍 Python</span><span style="color:var(--lime);font-size:11px">Full support</span></div>
      <div class="settings-option"><span>☕ Java</span><span style="color:var(--lime);font-size:11px">Full support</span></div>
      <div class="settings-option"><span>🟨 JavaScript</span><span style="color:var(--lime);font-size:11px">Full support</span></div>
      <div class="settings-option"><span>🔷 TypeScript</span><span style="color:var(--amber);font-size:11px">Partial</span></div>
      <div class="settings-option"><span>⚙ C++ / 🐹 Go</span><span style="color:var(--amber);font-size:11px">Conversion only</span></div>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     SETTINGS SIDE MODAL
══════════════════════════════════════════════════════ -->
<div class="side-modal" id="sideSettings">
  <div class="side-modal-header">
    <span class="side-modal-title">⚙ Settings</span>
    <button class="side-modal-close" onclick="closeSideModal('sideSettings')">✕</button>
  </div>
  <div class="side-modal-body">
    <div class="settings-row">
      <div class="settings-label">Appearance</div>
      <div class="settings-option">
        <span>Dark Mode</span>
        <div class="settings-toggle on" id="darkToggle" onclick="toggleTheme()"></div>
      </div>
    </div>
    <div class="settings-row">
      <div class="settings-label">Analysis</div>
      <div class="settings-option">
        <span>Auto-analyze on paste</span>
        <div class="settings-toggle" id="autoAnalyze" onclick="this.classList.toggle('on')"></div>
      </div>
      <div class="settings-option">
        <span>Security scan</span>
        <div class="settings-toggle on" onclick="this.classList.toggle('on')"></div>
      </div>
      <div class="settings-option">
        <span>Deep AST analysis</span>
        <div class="settings-toggle on" onclick="this.classList.toggle('on')"></div>
      </div>
    </div>
    <div class="settings-row">
      <div class="settings-label">Editor</div>
      <div class="settings-option">
        <span>Show line numbers</span>
        <div class="settings-toggle on" onclick="this.classList.toggle('on')"></div>
      </div>
      <div class="settings-option">
        <span>Word wrap</span>
        <div class="settings-toggle" onclick="this.classList.toggle('on')"></div>
      </div>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     NOTIFICATIONS SIDE MODAL
══════════════════════════════════════════════════════ -->
<div class="side-modal" id="sideNotifs">
  <div class="side-modal-header">
    <span class="side-modal-title">🔔 Notifications</span>
    <button class="side-modal-close" onclick="closeSideModal('sideNotifs')">✕</button>
  </div>
  <div class="side-modal-body">
    <div class="history-item">
      <div class="hi-lang" style="color:var(--rose)">🔴 CRITICAL</div>
      <div class="hi-code">Security vulnerability found in last scan</div>
      <div class="hi-meta"><span>SQL injection risk detected</span><span>just now</span></div>
    </div>
    <div class="history-item">
      <div class="hi-lang" style="color:var(--lime)">✅ SUCCESS</div>
      <div class="hi-code">Code analysis completed</div>
      <div class="hi-meta"><span>Health score: {{ result.score }}/100</span><span>recently</span></div>
    </div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     SIDEBAR
══════════════════════════════════════════════════════ -->
<div class="sidebar">
  <div class="sidebar-logo" onclick="showPage('analyse')" title="Home">⚓</div>
  <div class="sidebar-icon active" id="sb-analyse" onclick="showPage('analyse')" title="Analyse Code">⊞</div>
  <div class="sidebar-icon" id="sb-history" onclick="openSideModal('sideHistory')" title="History">⏱</div>
  <div class="sidebar-divider"></div>
  <div class="sidebar-icon" onclick="openSideModal('sideReports')" title="Reports">📊</div>
  <div class="sidebar-icon" onclick="openSideModal('sideDocs')" title="Documentation">📖</div>
  <div class="sidebar-bottom">
    <div class="theme-icon" onclick="toggleTheme()" title="Toggle theme" id="themeIcon">🌙</div>
    <div class="theme-toggle" onclick="toggleTheme()" title="Toggle theme"></div>
    <div class="sidebar-divider"></div>
    <div class="sidebar-icon" onclick="openSideModal('sideSettings')" title="Settings">⚙</div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════
     MAIN
══════════════════════════════════════════════════════ -->
<div class="main">

  <!-- TOPBAR -->
  <div class="topbar">
    <span class="topbar-logo">Anchor <span>Elite AI</span></span>

    <div class="sep"></div>

    <!-- Language selector -->
    <div class="lang-group">
      <button class="lang-btn {% if lang=='python' %}active{% endif %}" id="lang-python" onclick="setLang('python')">🐍 Python</button>
      <button class="lang-btn {% if lang=='java' %}active{% endif %}" id="lang-java" onclick="setLang('java')">☕ Java</button>
      <button class="lang-btn {% if lang=='javascript' %}active{% endif %}" id="lang-js" onclick="setLang('javascript')">🟨 JS</button>
    </div>

    <div class="sep"></div>

    <!-- Code Convert -->
    <button class="convert-btn" onclick="openConvert()">⇄ Convert</button>

    <div class="topbar-right">
      <div class="icon-btn notif-badge" title="Notifications" onclick="openSideModal('sideNotifs')">🔔</div>
      <div class="icon-btn" title="Settings" onclick="openSideModal('sideSettings')">⚙</div>
      <div class="avatar" onclick="openSideModal('sideSettings')" title="Profile">AE</div>
    </div>
  </div>

  <!-- CONTENT -->
  <div class="content">

    <!-- ═══════════ ANALYSE PAGE ═══════════ -->
    <div id="page-analyse" class="analyse-page">

      <!-- Stats -->
      <div class="stats-row">
        <div class="health-card">
          <div class="health-gauge-wrap"><canvas id="gaugeChart" width="64" height="64"></canvas></div>
          <div>
            <div class="score-num">{{ result.score }}</div>
            <div class="score-label">Health Score</div>
            <div class="score-status {% if result.score >= 85 %}status-good{% elif result.score >= 50 %}status-warn{% elif result.score > 0 %}status-crit{% endif %}">
              {% if result.score == 0 %}—
              {% elif result.score >= 85 %}Good Stand
              {% elif result.score >= 50 %}Needs Work
              {% else %}Critical{% endif %}
            </div>
          </div>
        </div>
        <div class="stat-card"><div class="stat-label">🐛 Critical</div><div class="stat-num">{{ result.critical_count }}</div></div>
        <div class="stat-card"><div class="stat-label">✦ Optims</div><div class="stat-num">{{ result.optims_count }}</div></div>
        <div class="stat-card"><div class="stat-label">🛡 Security</div><div class="stat-num">{{ result.security_count }}</div></div>
        <div class="stat-card"><div class="stat-label">⚡ Latency</div><div class="stat-num" style="font-size:18px">{{ result.latency }}</div></div>
      </div>

      <!-- Code panels -->
      <div class="panels-row">

        <!-- LEFT: Input panel -->
        <div class="panel">
          <div class="panel-header">
            <div class="panel-title">
              📄 Input Source
              <span class="panel-tag" id="fileTagLabel">main.{{ lang_ext }}</span>
            </div>
            <span style="font-size:10px;color:var(--muted)" id="codeStats">{{ result.lines }} ln · {{ result.chars }} ch</span>
          </div>

          <form method="POST" id="mainForm" onsubmit="showAnalyzeOverlay(event)">
            <input type="hidden" name="lang" id="langHidden" value="{{ lang }}">
            <!-- code area fills all available form height -->
            <div class="code-area">
              <div class="line-nums" id="lineNums">{% for i in range(1, [result.lines+2,3]|max) %}{{ i }}
{% endfor %}</div>
              <div class="code-scroll-inner">
                <textarea name="code" id="codeInput" class="code-input"
                  placeholder="// Paste your code here...&#10;// Ctrl+Enter to analyse"
                  oninput="syncLines(this);updateStats(this)">{{ code }}</textarea>
              </div>
            </div>
            <div class="panel-actions">
              <button type="submit" class="btn btn-primary" id="analyzeBtn">⚡ Analyze &amp; Refactor</button>
              <button type="button" class="btn btn-ghost" onclick="clearCode()">Clear</button>
            </div>
          </form>
        </div>

        <!-- RIGHT: Output panel -->
        <div class="panel" style="flex:1.1">
          <div class="panel-header">
            <div class="panel-title">✦ Corrected Code</div>
            <div style="display:flex;gap:6px">
              <button class="copy-btn-sm" id="copyBtn" onclick="copyCode()">⎘ Copy</button>
              {% if result.full_code %}<button class="copy-btn-sm" onclick="downloadCode()">⬇ Download</button>{% endif %}
            </div>
          </div>

          {% if result.full_code %}
            <div class="corrected-body" id="correctedCode">{{ result.full_code }}</div>
            <div class="optim-badge">
              ✦ OPTIMIZATION APPLIED
              <div class="optim-desc">{{ result.msg }}</div>
            </div>
          {% else %}
            <div class="empty-state">
              <div class="es-icon">✦</div>
              <div class="es-txt">Corrected code appears here after analysis</div>
            </div>
          {% endif %}

          <div class="panel-actions">
            {% if result.full_code %}
              <button class="btn btn-lime" onclick="downloadCode()" style="flex:1">⬇ Download Fixed Code</button>
            {% else %}
              <div style="font-size:11px;color:var(--muted);padding:4px 0">— Submit code to see corrected version —</div>
            {% endif %}
          </div>
        </div>
      </div>

      <!-- Fault panel -->
      {% if result.old_line %}
      <div class="fault-panel">
        <div class="fault-header">❌ Fault Location &amp; Explanation</div>
        <div class="fault-body">{{ result.old_line }}</div>
      </div>
      {% endif %}

      <!-- Recommended Refactors -->
      <div class="refactors-section">
        <div class="section-label">Recommended Refactors</div>
        <div class="refactors-row">
          <div class="refactor-card" onclick="applyRefactor('decouple')">
            <div class="refactor-icon ri-purple">🔗</div>
            <div class="refactor-info">
              <div class="ri-title">Decouple API Logic</div>
              <div class="ri-sub">Extract endpoints into config provider.</div>
            </div>
            <span class="refactor-arrow">›</span>
          </div>
          <div class="refactor-card" onclick="applyRefactor('lazy')">
            <div class="refactor-icon ri-amber">✦</div>
            <div class="refactor-info">
              <div class="ri-title">Lazy Load Modules</div>
              <div class="ri-sub">Reduce ML startup latency.</div>
            </div>
            <span class="refactor-arrow">›</span>
          </div>
          <div class="refactor-card" onclick="applyRefactor('sanitize')">
            <div class="refactor-icon ri-rose">🛡</div>
            <div class="refactor-info">
              <div class="ri-title">Sanitize Inputs</div>
              <div class="ri-sub">Fix SQL Injection risks.</div>
            </div>
            <span class="refactor-arrow">›</span>
          </div>
          <div class="refactor-card" onclick="applyRefactor('convert')">
            <div class="refactor-icon ri-sky">⇄</div>
            <div class="refactor-info">
              <div class="ri-title">Convert Language</div>
              <div class="ri-sub">Translate to another language.</div>
            </div>
            <span class="refactor-arrow">›</span>
          </div>
        </div>
      </div>

    </div><!-- /analyse-page -->

  </div><!-- /content -->
</div><!-- /main -->

<!-- ══════════════════════════════════════════════════════
     SCRIPTS
══════════════════════════════════════════════════════ -->
<script>
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
  document.getElementById('page-' + name).style.display = 'flex';
  document.querySelectorAll('.sidebar-icon[id^="sb-"]').forEach(el => el.classList.remove('active'));
  const sb = document.getElementById('sb-' + name);
  if (sb) sb.classList.add('active');
}

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
const langExt = { python:'py', java:'java', javascript:'js' };
function setLang(lang) {
  document.getElementById('langHidden').value = lang;
  ['python','java','js'].forEach(l => {
    const id = 'lang-' + l;
    const el = document.getElementById(id);
    if (el) el.classList.toggle('active', (l === 'js' ? 'javascript' : l) === lang);
  });
  const ext = langExt[lang] || 'txt';
  document.getElementById('fileTagLabel').textContent = 'main.' + ext;
}

// ── Gauge chart ──────────────────────────────────────
const score = {{ result.score }};
const gColor = score >= 85 ? '#84cc16' : score >= 50 ? '#f59e0b' : score > 0 ? '#f43f5e' : '#1e293b';
const gaugeCtx = document.getElementById('gaugeChart');
if (gaugeCtx) {
  new Chart(gaugeCtx, {
    type: 'doughnut',
    data: { datasets:[{ data:[score, 100-score], backgroundColor:[gColor,'#0f172a'], borderWidth:0, borderRadius:6 }] },
    options: { cutout:'78%', plugins:{ legend:{ display:false } }, animation:{ duration:900, easing:'easeInOutQuart' } }
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
  // Save to history
  addToHistory(code, document.getElementById('langHidden').value);
}

// ── History ──────────────────────────────────────────
let analysisHistory = JSON.parse(localStorage.getItem('ae-history') || '[]');
function addToHistory(code, lang) {
  const entry = {
    code: code.slice(0, 120),
    lang: lang,
    time: new Date().toLocaleTimeString(),
    date: new Date().toLocaleDateString(),
  };
  analysisHistory.unshift(entry);
  if (analysisHistory.length > 20) analysisHistory.pop();
  localStorage.setItem('ae-history', JSON.stringify(analysisHistory));
  renderHistory();
}
function renderHistory() {
  const body = document.getElementById('historyBody');
  if (!analysisHistory.length) {
    body.innerHTML = '<div class="modal-empty"><div class="me-icon">⏱</div>No analyses yet.</div>';
    return;
  }
  body.innerHTML = analysisHistory.map((h, i) => `
    <div class="history-item" onclick="loadHistory(${i})">
      <div class="hi-lang">${h.lang.toUpperCase()}</div>
      <div class="hi-code">${h.code.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
      <div class="hi-meta"><span>${h.date}</span><span>${h.time}</span></div>
    </div>
  `).join('');
}
function loadHistory(i) {
  const h = analysisHistory[i];
  if (!h) return;
  document.getElementById('codeInput').value = h.code;
  syncLines(document.getElementById('codeInput'));
  updateStats(document.getElementById('codeInput'));
  setLang(h.lang);
  closeAllSideModals();
}
renderHistory();

// ── Copy & Download ───────────────────────────────────
function copyCode() {
  const el = document.getElementById('correctedCode');
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
function applyRefactor(type) {
  if (type === 'convert') {
    openConvert();
    return;
  }
  const ta = document.getElementById('codeInput');
  const code = ta.value.trim();
  if (!code) {
    // Show tooltip-style feedback
    alert('Paste some code first, then click a refactor card.');
    return;
  }
  // Trigger analyze with current code
  document.getElementById('mainForm').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
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
</script>
</body>
</html>
"""

def _count_by_severity(faults_text: str):
    if not faults_text:
        return 0, 0, 0
    return faults_text.count('🔴'), faults_text.count('🟡'), faults_text.count('🔵')

@app.route("/", methods=["GET", "POST"])
def index():
    code = request.form.get("code", "")
    lang = request.form.get("lang", "python")
    result = {
        "score": 0, "confidence": "0%",
        "msg": "Paste code above and click Analyse.",
        "old_line": "", "full_code": "", "lines": 0, "chars": 0,
        "critical_count": "00", "optims_count": "00",
        "security_count": "00", "latency": "—",
    }
    if request.method == "POST" and code.strip():
        result = analyze_logic(code, lang)
        faults = result.get("old_line", "")
        crit, mod, minor = _count_by_severity(faults)
        sec_kw = ["sql","inject","xss","password","hardcoded","shell","pickle","rce","innerhtml","localstorage"]
        sec_count = sum(1 for l in faults.splitlines()
                        if '🔴' in l and any(k in l.lower() for k in sec_kw))
        result["critical_count"] = f"{crit:02d}"
        result["optims_count"]   = f"{(mod + minor):02d}"
        result["security_count"] = f"{sec_count:02d}"
        result["latency"]        = f"{max(1, result['chars'] // 80)}ms"

    lang_ext = {"python": "py", "java": "java", "javascript": "js"}.get(lang, "txt")
    return render_template_string(HTML, code=code, lang=lang, result=result, lang_ext=lang_ext)


@app.route("/convert", methods=["POST"])
def convert_code():
    """Convert code from one language to another using Groq."""
    try:
        data      = request.get_json()
        code      = data.get("code", "")
        from_lang = data.get("from_lang", "python")
        to_lang   = data.get("to_lang", "javascript")

        if not code.strip():
            return jsonify({"error": "No code provided"}), 400

        from code_analyzer import _groq_call

        system = f"""You are a code conversion expert. Convert code from {from_lang} to {to_lang}.
Rules:
- Return ONLY the converted {to_lang} code, no explanations, no markdown, no code fences.
- Preserve the logic exactly.
- Use idiomatic {to_lang} patterns.
- Add appropriate imports/packages for {to_lang}.
- Do NOT include any language tags or markdown."""

        user = f"""Convert this {from_lang} code to {to_lang}:

{code}

Return ONLY the {to_lang} code:"""

        result = _groq_call(system, user)
        if result:
            result = result.strip()
            for fence in ["```" + to_lang, "```python", "```java", "```javascript", "```typescript", "```cpp", "```go", "```"]:
                result = result.replace(fence, "")
            result = result.strip()
            return jsonify({"converted": result})
        else:
            return jsonify({"error": "Conversion failed — Groq unavailable"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)