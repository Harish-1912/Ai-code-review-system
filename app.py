from flask import Flask, render_template, request, jsonify, Response
from code_analyzer import analyze_logic, _groq_call_with_usage, _groq_stream, MAX_CODE_CHARS
import re, os, logging, json
from flask import Flask, send_file
import history_db

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _HAS_LIMITER = True
except ImportError:
    _HAS_LIMITER = False

# ── Structured logging instead of print() ──────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("anchor_elite.app")

app = Flask(__name__)
history_db.init_db()

# Reject request bodies over 1MB outright (defense in depth on top of the
# per-field MAX_CODE_CHARS check in code_analyzer.analyze_logic).
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

if _HAS_LIMITER:
    limiter = Limiter(get_remote_address, app=app, default_limits=["120 per hour"])
else:
    log.warning("flask-limiter not installed — run `pip install flask-limiter` "
                "to enable rate limiting. Endpoints are unprotected until then.")
    class _NoopLimiter:
        def limit(self, *a, **k):
            def deco(fn):
                return fn
            return deco
    limiter = _NoopLimiter()

@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "Request body too large (max 1MB)."}), 413


@app.route('/robots.txt')
def robots():
    content = "User-agent: *\nAllow: /\n\nSitemap: https://ai-code-review-system.onrender.com/sitemap.xml\n"
    return app.response_class(content, mimetype='text/plain')



def _count_by_severity(faults_text: str):
    if not faults_text:
        return 0, 0, 0
    return faults_text.count('🔴'), faults_text.count('🟡'), faults_text.count('🔵')

@app.route("/", methods=["GET", "POST"])
@limiter.limit("30 per minute")
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

        # Server-side history — saved AFTER the result exists (so it actually
        # records a score), with the full code, not a truncated preview.
        try:
            history_db.save_analyze(
                code=code, lang=lang, score=result.get("score", 0),
                corrected_code=result.get("full_code", ""),
                verified=result.get("verified", False),
            )
        except Exception:
            log.exception("Failed to save analyze history (non-fatal)")

    lang_ext = {"python": "py", "java": "java", "javascript": "js", "c": "c"}.get(lang, "txt")
    return render_template("index.html", code=code, lang=lang, result=result, lang_ext=lang_ext)


@app.route("/convert", methods=["POST"])
@limiter.limit("20 per minute")
def convert_code():
    """Convert code from one language to another using Groq."""
    try:
        data      = request.get_json(silent=True) or {}
        code      = data.get("code", "")
        from_lang = data.get("from_lang", "python")
        to_lang   = data.get("to_lang", "javascript")

        if not code.strip():
            return jsonify({"error": "No code provided"}), 400
        if len(code) > MAX_CODE_CHARS:
            return jsonify({"error": f"Input too large ({len(code):,} chars). "
                                      f"Limit is {MAX_CODE_CHARS:,} chars."}), 413

        from code_analyzer import _groq_call

        system = f"""You are a code conversion expert. Convert code from {from_lang} to {to_lang}.
Rules:
- Return ONLY the converted {to_lang} code, no explanations, no markdown, no code fences.
- Preserve the logic exactly.
- Use idiomatic {to_lang} patterns.
- STRONGLY PREFER the {to_lang} standard library / built-in classes only. Do NOT use third-party
  packages (e.g. Jackson, Gson, requests, lodash, Newtonsoft.Json) unless the original {from_lang}
  code itself already depends on an external library with no reasonable standard-library equivalent.
- If a third-party dependency is truly unavoidable, add a single-line comment directly above the
  import stating the exact package/artifact needed (e.g. "// requires: com.fasterxml.jackson.core:jackson-databind:2.17.0").
- Add only the imports/packages actually needed for the code to compile and run as-is.
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
        log.exception("convert_code failed")
        return jsonify({"error": str(e)}), 500


def _build_assistant_prompt(prompt: str, code: str):
    """Shared by /assistant and /assistant/stream so both endpoints ask
    Groq the exact same thing — one prompt to maintain, not two."""
    if code:
        system = """You are an expert AI coding assistant. The user will give you existing code and instructions on how to modify it.
Rules:
- Return ONLY the modified code, no explanations, no markdown fences, no preamble.
- Preserve the original language and structure unless explicitly asked to change.
- Apply the requested modifications precisely.
- Add comments only where necessary to explain changes.
- Do NOT wrap the output in triple backticks."""
        user = f"""Instructions: {prompt}

Existing code to modify:
{code}

Return ONLY the modified code:"""
    else:
        system = """You are an expert AI coding assistant. Generate clean, production-quality code based on the user's request.
Rules:
- Return ONLY the code, no explanations, no markdown fences, no preamble.
- Use best practices and idiomatic patterns for the language.
- Add brief inline comments for complex logic.
- Do NOT wrap the output in triple backticks."""
        user = f"""Generate code for the following request:
{prompt}

Return ONLY the code:"""
    return system, user


@app.route("/assistant", methods=["POST"])
@limiter.limit("20 per minute")
def assistant():
    """AI Assistant — generate or modify code based on prompt."""
    try:
        data   = request.get_json(silent=True) or {}
        prompt = data.get("prompt", "").strip()
        code   = data.get("code", "").strip()

        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400
        if len(prompt) + len(code) > MAX_CODE_CHARS:
            return jsonify({"error": f"Input too large. Limit is {MAX_CODE_CHARS:,} chars total."}), 413

        system, user = _build_assistant_prompt(prompt, code)

        # Uses the shared client in code_analyzer.py (live model discovery +
        # response caching + structured logging) instead of duplicating a
        # second hardcoded Groq client here — previously this endpoint had
        # its own copy of the model list, which is exactly how one of the
        # earlier "everything is broken" bugs slipped in undetected.
        usage_data = _groq_call_with_usage(system, user)
        result        = usage_data["result"]
        model_used    = usage_data["model"]
        prompt_tokens = usage_data["prompt_tokens"]
        output_tokens = usage_data["output_tokens"]
        total_tokens  = usage_data["total_tokens"]
        limit         = usage_data["limit"]
        limit_pct     = usage_data["limit_pct"]

        if result:
            for fence in ["```python","```java","```javascript","```typescript","```cpp","```go","```"]:
                result = result.replace(fence, "")
            result = result.strip()
            try:
                history_db.save_assistant(prompt=prompt, code=code, result=result, model=model_used)
            except Exception:
                log.exception("Failed to save assistant history (non-fatal)")
            return jsonify({
                "result":        result,
                "model":         model_used,
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_tokens":  total_tokens,
                "limit":         limit,
                "limit_pct":     limit_pct,
                "cached":        usage_data.get("cached", False),
            })
        else:
            return jsonify({"error": "AI model unavailable — check your Groq API key"}), 500

    except Exception as e:
        log.exception("assistant endpoint failed")
        return jsonify({"error": str(e)}), 500


@app.route("/assistant/stream", methods=["POST"])
@limiter.limit("20 per minute")
def assistant_stream():
    """
    Real token-by-token streaming version of /assistant, using Server-Sent
    Events. Replaces the old approach of waiting for the full Groq response
    and then fake-typing it out character-by-character client-side — this
    actually streams as Groq generates it.

    Each event line is: data: <json>\\n\\n
    Event payloads: {"type": "chunk", "text": "..."} as text arrives,
    then exactly one {"type": "done", ...usage stats} or {"type": "error", ...}.
    """
    data   = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "").strip()
    code   = data.get("code", "").strip()

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400
    if len(prompt) + len(code) > MAX_CODE_CHARS:
        return jsonify({"error": f"Input too large. Limit is {MAX_CODE_CHARS:,} chars total."}), 413

    system, user = _build_assistant_prompt(prompt, code)

    def generate():
        chunks = []
        model_used = ""
        try:
            for event in _groq_stream(system, user):
                if event.get("type") == "chunk":
                    chunks.append(event["text"])
                elif event.get("type") == "done":
                    model_used = event.get("model", "")
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            log.exception("assistant_stream generator failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        full_result = "".join(chunks).strip()
        if full_result:
            for fence in ["```python","```java","```javascript","```typescript","```cpp","```go","```"]:
                full_result = full_result.replace(fence, "")
            full_result = full_result.strip()
            try:
                history_db.save_assistant(prompt=prompt, code=code, result=full_result, model=model_used)
            except Exception:
                log.exception("Failed to save assistant stream history (non-fatal)")

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering so chunks arrive live
        },
    )


@app.route("/api/history/<kind>", methods=["GET"])
@limiter.limit("60 per minute")
def get_history(kind):
    """kind is 'analyze' or 'assistant'. Returns most-recent-first JSON list."""
    if kind not in ("analyze", "assistant"):
        return jsonify({"error": "kind must be 'analyze' or 'assistant'"}), 400
    limit = min(int(request.args.get("limit", 20)), 100)
    try:
        rows = (history_db.get_analyze_history(limit) if kind == "analyze"
                else history_db.get_assistant_history(limit))
        return jsonify({"entries": rows})
    except Exception as e:
        log.exception("get_history failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<kind>/<int:entry_id>", methods=["DELETE"])
@limiter.limit("60 per minute")
def delete_history_entry(kind, entry_id):
    if kind not in ("analyze", "assistant"):
        return jsonify({"error": "kind must be 'analyze' or 'assistant'"}), 400
    try:
        history_db.delete_entry(kind, entry_id)
        return jsonify({"ok": True})
    except Exception as e:
        log.exception("delete_history_entry failed")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history/<kind>", methods=["DELETE"])
@limiter.limit("20 per minute")
def clear_history_route(kind):
    if kind not in ("analyze", "assistant"):
        return jsonify({"error": "kind must be 'analyze' or 'assistant'"}), 400
    try:
        history_db.clear_history(kind)
        return jsonify({"ok": True})
    except Exception as e:
        log.exception("clear_history_route failed")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)