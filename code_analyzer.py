import re, ast, pickle, os, time, subprocess, tempfile, logging, hashlib, threading, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("API_KEY")
client = Groq(api_key=GROQ_API_KEY)

# ── Structured logging instead of print() ──────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("anchor_elite.code_analyzer")

MODEL_DIR = Path(__file__).parent / 'model/models'
_bug_model = _adv_model = None

def _load_models():
    global _bug_model, _adv_model
    if _bug_model is not None:
        return
    for name, key in [('advanced_bug_model.pkl','_adv_model'),('bug_model.pkl','_bug_model')]:
        try:
            with open(MODEL_DIR / name, 'rb') as f:
                globals()[key] = pickle.load(f)
        except Exception:
            pass

PATTERNS = {
    "python": [
        (r'except\s*:',                       "Bare except — use: except Exception as e:",        2),
        (r'==\s*None',                        "Use 'is None' not '== None'",                      1),
        (r'!=\s*None',                        "Use 'is not None' not '!= None'",                  1),
        (r'\beval\s*\(',                      "eval() is dangerous — use ast.literal_eval()",     3),
        (r'\bexec\s*\(',                      "exec() executes arbitrary code — security risk",   3),
        (r'from .+? import \*|import \*',     "Wildcard import — import explicitly",              1),
        (r'\bglobal\b',                       "Avoid global — pass as argument instead",          1),
        (r'time\.sleep\s*\(',                 "Blocking sleep — use asyncio.sleep() in async",    2),
        (r'pickle\.loads?\s*\(',              "pickle on untrusted data allows RCE — use json",   3),
        (r'shell\s*=\s*True',                 "shell=True vulnerable to command injection",        3),
        (r'hashlib\.md5|hashlib\.sha1',       "MD5/SHA1 broken for passwords — use bcrypt",       3),
        (r"password\s*=\s*['\"].+['\"]",      "Hardcoded password — use os.environ.get()",        3),
        (r'random\.randint|random\.random\(', "random not secure — use secrets module",            2),
        (r'type\s*\([^)]+\)\s*==',           "Use isinstance() not type() ==",                    1),
        (r'\bassert\b',                       "assert disabled by -O — use if/raise instead",     1),
        (r'range\s*\(\s*len\s*\(',           "Use enumerate() not range(len(...))",                1),
        (r'\bprint\s*\(',                     "Use logging not print() in production",             1),
        (r'os\.system\s*\(',                  "os.system() unsafe — use subprocess.run(list)",    2),
        (r'open\s*\([^)]+\)(?!\s*as)',        "Use 'with open() as f:' to close file safely",    2),
    ],
    "java": [
        (r'==\s*"[^"]*"',                           "Use .equals() not == for String comparison",     2),
        (r'catch\s*\(\s*Exception\b',               "Catch specific exceptions not generic Exception", 2),
        (r'System\.out\.print',                     "Use Logger not System.out in production",         1),
        (r'\.length\s*\(\s*\)\s*==\s*0',           "Use .isEmpty() not .length() == 0",               1),
        (r'Thread\.sleep\s*\(',                     "Thread.sleep blocks thread — use async",          2),
        (r'==\s*null|null\s*==',                    "Use Optional or Objects.isNull() for null",       2),
        (r'Integer\.parseInt\s*\(',                 "parseInt throws NumberFormatException — wrap it",  2),
        (r'static\s+(?:List|Map|Set|ArrayList)\b', "Static mutable collection not thread-safe",        2),
        (r'result\s*\+=\s*\w+\s*;',               "String concat in loop — use StringBuilder",        2),
    ],
    "javascript": [
        (r'\beval\s*\(',                      "eval() enables XSS — remove entirely",             3),
        (r'\bvar\s+',                         "Replace var with let or const",                     1),
        (r'\.innerHTML\s*=',                  "innerHTML with user data enables XSS",              3),
        (r'document\.write\s*\(',            "document.write() overwrites page — use DOM API",    2),
        (r"setTimeout\s*\(\s*['\"]",         "Pass a function to setTimeout not a string",        2),
        (r'localStorage\.setItem',            "Never store sensitive data in localStorage",        3),
        (r'delete\s+\w+\[',                  "Use .splice() not delete on array index",            2),
        (r'JSON\.parse\s*\(',                "Wrap JSON.parse in try-catch for safety",            2),
        (r'console\.log\s*\(',               "Remove console.log before production",               1),
    ],
    "c": [
        (r'\bgets\s*\(',                      "gets() has no bounds check — use fgets() instead",  3),
        (r'\bscanf\s*\(\s*"%s"',             'scanf("%s") unbounded — use scanf("%Ns") with limit',3),
        (r'\bstrcpy\s*\(',                    "strcpy() unsafe — use strncpy() or strlcpy()",      3),
        (r'\bstrcat\s*\(',                    "strcat() unsafe — use strncat()",                    3),
        (r'\bsprintf\s*\(',                   "sprintf() unsafe — use snprintf()",                  3),
        (r'\bmalloc\s*\([^)]+\)\s*;(?!\s*if)',
                                              "malloc() return not checked — check for NULL",      2),
        (r'\bfree\s*\(\s*\w+\s*\)\s*;(?!.*\w+\s*=\s*NULL)',
                                              "After free(), set pointer to NULL to avoid use-after-free", 2),
        (r'==\s*NULL|NULL\s*==',             "Use explicit NULL check: if (ptr == NULL)",          1),
        (r'\bprintf\s*\(\s*\w+\s*\)',        "printf(var) allows format string attack — use printf(\"%s\", var)", 3),
        (r'int\s+main\s*\(\s*\)',            "Use int main(void) for no args or int main(int argc, char *argv[])", 1),
        (r'#include\s*<string\.h>.*\bstrcmp\b|strcmp\s*\(',
                                              "strcmp returns 0 for equal — don't use as boolean", 1),
        (r'\bsystem\s*\(',                   "system() is dangerous — use exec() family instead", 3),
        (r'char\s+\w+\s*\[\s*\d+\s*\].*=.*gets|gets.*char\s+\w+',
                                              "Buffer overflow risk — never use gets()",           3),
        (r'while\s*\(\s*1\s*\)|for\s*\(\s*;\s*;\s*\)',
                                              "Infinite loop — ensure there is a break condition", 2),
    ],
}

def _ast_issues(code: str) -> list:
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError line {e.lineno}: {e.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for d in node.args.defaults:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    issues.append(f"'{node.name}': mutable default arg — use None, assign inside")
            recursive = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == node.name for n in ast.walk(node)
            )
            if recursive and not any(isinstance(n, ast.If) for n in ast.walk(node)):
                issues.append(f"'{node.name}': recursive with no base case — add if guard")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            if isinstance(node.right, ast.Constant) and node.right.value == 0:
                issues.append("Division by literal zero detected")
    return issues

def _pylint_issues(code: str) -> list:
    issues = []
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                         delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp = f.name
        result = subprocess.run(
            ['pylint', tmp, '--output-format=text',
             '--disable=C0114,C0115,C0116,C0103,C0301,W0611',
             '--score=no'],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            if re.search(r':\d+:\d+:', line):
                clean = re.sub(r'.+\.py:(\d+):\d+: [A-Z]\d+: ', r'Line \1: ', line)
                issues.append(clean)
        os.unlink(tmp)
    except Exception:
        pass
    return issues[:10]

def _find_faults(code: str, lang: str) -> str:
    lines, flagged, seen = code.splitlines(), [], set()
    for pattern, desc, severity in PATTERNS.get(lang, []):
        for i, line in enumerate(lines, 1):
            if i not in seen and re.search(pattern, line):
                icon = '🔴' if severity == 3 else ('🟡' if severity == 2 else '🔵')
                flagged += [f"{icon} Line {i:>3}:  {line.strip()}",
                            f"           =>  {desc}"]
                seen.add(i)
    if lang == 'python':
        for issue in _ast_issues(code):
            flagged.append(f"🔴 AST:  {issue}")
        for issue in _pylint_issues(code):
            flagged.append(f"🟡 PYLINT:  {issue}")
    return '\n'.join(flagged) if flagged else '✅ No issues found.'

# ── Sandbox safety gate ────────────────────────────────────────────────────
# NOTE: this is a best-effort static gate, not a real sandbox. It blocks the
# obvious ways submitted code could touch the filesystem, network, or spawn
# processes on the host running this Flask app. For real isolation (untrusted
# multi-tenant use), run this inside a locked-down Docker container instead
# (see run_in_docker() below, disabled by default — enable with
# SANDBOX_BACKEND=docker in .env once Docker Desktop is installed).
_BLOCKED_IMPORTS = {
    'os', 'sys', 'subprocess', 'socket', 'shutil', 'ctypes', 'multiprocessing',
    'importlib', 'pty', 'pdb', 'signal', 'resource',
    'urllib', 'urllib2', 'urllib3', 'requests', 'http', 'ftplib', 'telnetlib',
    'smtplib', 'shelve', 'marshal', 'pickle',
}
# Deliberately NOT blocked despite being "system-adjacent": sqlite3 (local,
# file-scoped database — no network/shell access, and now runs in a
# throwaway scratch directory that gets deleted afterward — see
# _execute_and_check), inspect and threading (introspection/concurrency,
# neither can escape the sandboxed subprocess).
_BLOCKED_CALLS = {'eval', 'exec', '__import__', 'compile', 'open'}
# input() is deliberately NOT here — it isn't a security risk (no filesystem/
# network/process access), it's just interactivity that an unattended sandbox
# can't provide. That's handled separately by _uses_interactive_input() below,
# with an honest explanation instead of being mislabeled as "unsafe."

def _sandbox_violations(code: str):
    """Static AST scan for operations we refuse to execute locally.
    Returns (kind, list) where kind is 'syntax' or 'blocked'."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return ("syntax", [f"{e.msg} (line {e.lineno})"])

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split('.')[0]
                if root in _BLOCKED_IMPORTS:
                    violations.append(f"blocked import '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or '').split('.')[0]
            if root in _BLOCKED_IMPORTS:
                violations.append(f"blocked import 'from {node.module}'")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if name in _BLOCKED_CALLS:
                violations.append(f"blocked call '{name}()'")
    seen = set()
    out = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return ("blocked", out)


def run_in_docker(code: str, lang: str) -> str:
    """
    Optional real sandbox: runs code inside a throwaway, network-disabled,
    resource-capped Docker container. Requires Docker Desktop running on the
    host and SANDBOX_BACKEND=docker in .env. Falls back with a clear message
    if Docker isn't available — this function is NOT wired in by default.
    """
    image = 'python:3.12-slim' if lang != 'c' else 'gcc:13-bookworm'
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py' if lang != 'c' else '.c',
                                     delete=False, encoding='utf-8') as f:
        f.write(code)
        host_path = f.name
    container_path = f"/sandbox/{os.path.basename(host_path)}"
    try:
        cmd = [
            'docker', 'run', '--rm',
            '--network', 'none',                # no network access
            '--memory', '128m', '--cpus', '0.5',# resource caps
            '--pids-limit', '64',
            '--read-only',
            '-v', f'{host_path}:{container_path}:ro',
            image,
            'python', container_path
        ] if lang != 'c' else [
            'docker', 'run', '--rm', '--network', 'none',
            '--memory', '128m', '--cpus', '0.5', '--pids-limit', '64',
            '-v', f'{host_path}:{container_path}:ro',
            image, 'sh', '-c', f'gcc {container_path} -o /tmp/a.out && /tmp/a.out'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return result.stdout.strip() or result.stderr.strip() or "(no output)"
    except FileNotFoundError:
        return "⚠ Docker not found — install Docker Desktop or unset SANDBOX_BACKEND."
    except subprocess.TimeoutExpired:
        return "🔴 Execution timed out in sandbox."
    finally:
        try:
            os.unlink(host_path)
        except OSError:
            pass


def _uses_interactive_input(code: str) -> bool:
    """AST check for input() calls — code that reads from stdin can't be
    meaningfully executed in an unattended sandbox (nothing is typing
    answers), so this is used to skip a doomed execution attempt rather
    than let it hang or misreport a real bug."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == 'input':
                return True
    return False


def _execute_and_check(code: str, lang: str = 'python') -> str:
    if lang == 'c':
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.c',
                                             delete=False, encoding='utf-8') as f:
                f.write(code)
                tmp_c = f.name
            tmp_out = tmp_c.replace('.c', '.out')
            compile_result = subprocess.run(
                ['gcc', tmp_c, '-o', tmp_out, '-Wall', '-Wextra'],
                capture_output=True, text=True, timeout=15
            )
            os.unlink(tmp_c)
            if os.path.exists(tmp_out):
                os.unlink(tmp_out)
            if compile_result.returncode != 0:
                return f"🔴 COMPILE ERROR:\n{compile_result.stderr.strip()}"
            warnings = compile_result.stderr.strip()
            return f"✅ Compiles successfully.{' Warnings:\\n' + warnings if warnings else ''}"
        except FileNotFoundError:
            return "⚠ gcc not found — install GCC to enable C compilation checks."
        except Exception as e:
            return f"🔴 Compile check failed: {e}"

    # Python: static safety gate first — refuse to run anything that could
    # touch the filesystem, network, or spawn processes on this machine.
    # (Docker path gets real isolation, so the static gate isn't needed there.)
    if os.getenv('SANDBOX_BACKEND', '').lower() != 'docker':
        kind, violations = _sandbox_violations(code)
        if kind == "syntax":
            # Not a safety issue — the code just doesn't parse. Report it as
            # a normal error, same as a real runtime failure would look.
            return f"🔴 SYNTAX ERROR:\n{violations[0]}"
        if violations:
            return ("⚠ Execution skipped for safety — this code uses operations "
                     "the local sandbox doesn't allow: " + ", ".join(violations) +
                     ". Enable Docker-backed sandboxing (SANDBOX_BACKEND=docker) "
                     "for full execution of untrusted code.")

    if os.getenv('SANDBOX_BACKEND', '').lower() == 'docker':
        out = run_in_docker(code, lang)
        return f"✅ Ran in sandbox. Output:\n{out}" if not out.startswith(('🔴', '⚠')) else out

    # Code that calls input() can't be meaningfully run unattended — there's
    # no one at a keyboard to answer it. Running it anyway would either hang
    # until the timeout or raise a stdin EOFError, and both would look like
    # "the code is broken" when it isn't. Skip execution and say so plainly,
    # the same way we already do for code the safety gate refuses to run.
    if _uses_interactive_input(code):
        return ("⚠ Not executed — this script calls input() and waits for a person "
                "to type an answer, which an automated verification pass can't do. "
                "This isn't a bug in your code; test it yourself in a terminal or "
                "online compiler where you can actually type a response.")

    scratch_dir = tempfile.mkdtemp(prefix="anchor_sandbox_")
    try:
        tmp = os.path.join(scratch_dir, "submitted.py")
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(code)
        # -I: isolated mode (ignores env vars, user site-packages, cwd on sys.path)
        # Keep only what's needed to locate the interpreter/DLLs; strip everything
        # else (API keys, secrets, etc.) so the sandboxed code can't read them.
        minimal_env = {k: os.environ[k] for k in ('PATH', 'SystemRoot', 'SYSTEMROOT')
                        if k in os.environ}
        result = subprocess.run(
            ['python', '-I', tmp],
            capture_output=True, text=True, timeout=6,  # was 10s — typical demo code runs in
                              # milliseconds; this only matters as a worst-case cap for a hang
            env=minimal_env,
            cwd=scratch_dir,  # any files the code creates (e.g. a sqlite .db)
                              # land here, not in the app's real project folder
            stdin=subprocess.DEVNULL,  # defense-in-depth: if _uses_interactive_input()
                              # somehow misses an input() call, this turns a 6s hang
                              # into an instant, clean EOFError instead
        )
        if result.returncode != 0:
            return f"🔴 RUNTIME ERROR:\n{result.stderr.strip()}"
        return f"✅ Runs successfully. Output:\n{result.stdout.strip()}"
    except subprocess.TimeoutExpired:
        return "🔴 Execution timed out (6s limit)."
    except Exception as e:
        return f"🔴 Execution failed: {e}"
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


# ── Updated _groq_call — returns dict with result + real token usage ──────────
def _groq_call(system: str, user: str) -> str:
    """
    Calls Groq API and returns just the text result (str).
    Use _groq_call_with_usage() when you need token counts.
    """
    data = _groq_call_with_usage(system, user)
    return data["result"]


# ── Live model list ─────────────────────────────────────────────────────────
# Hardcoded fallback used only if the /v1/models fetch itself fails (e.g. no
# network) — deliberately NOT the source of truth anymore, so a future Groq
# model deprecation doesn't silently break this app again.
_FALLBACK_MODEL_LIMITS = {
    "openai/gpt-oss-120b": 131072,
    "openai/gpt-oss-20b":  131072,
}
_model_cache = {"limits": None, "fetched_at": 0}
_MODEL_CACHE_TTL = 3600  # re-check available models hourly


def _get_model_limits(force_refresh: bool = False) -> dict:
    """Fetch current Groq-hosted chat models + context windows from the live
    /v1/models endpoint, cached for _MODEL_CACHE_TTL seconds. Falls back to
    _FALLBACK_MODEL_LIMITS if the API call fails.

    force_refresh=True bypasses the cache — used when every model in the
    cached list just failed, so a stale list (e.g. Groq deprecated a model
    we still have cached) gets auto-corrected on the spot instead of the
    request just failing until the next hourly refresh."""
    now = time.time()
    if not force_refresh and _model_cache["limits"] and (now - _model_cache["fetched_at"] < _MODEL_CACHE_TTL):
        return _model_cache["limits"]

    try:
        resp = client.models.list()
        limits = {}
        for m in resp.data:
            mid = getattr(m, "id", "")
            ctx = getattr(m, "context_window", None)
            if not mid or ctx is None:
                continue
            if any(bad in mid for bad in ("whisper", "tts", "guard", "playai")):
                continue  # not valid for chat.completions
            limits[mid] = ctx
        if limits:
            ordered = dict(sorted(limits.items(), key=lambda kv: (-kv[1], kv[0])))
            _model_cache["limits"] = ordered
            _model_cache["fetched_at"] = now
            log.info(f"Refreshed live model list: {list(ordered.keys())}")
            return ordered
    except Exception as e:
        log.warning(f"Live model fetch failed, using fallback list: {e}")

    _model_cache["limits"] = _FALLBACK_MODEL_LIMITS
    _model_cache["fetched_at"] = now
    return _FALLBACK_MODEL_LIMITS


# ── Response cache ──────────────────────────────────────────────────────────
# In-memory TTL cache keyed by a hash of (system, user) prompt. Avoids paying
# for/waiting on a fresh Groq call for a repeat request (e.g. re-clicking
# Analyze on the same snippet, or Convert immediately followed by re-Analyze).
_response_cache = {}
_CACHE_TTL = 600  # 10 minutes
_cache_lock = threading.Lock()


def _cache_key(system: str, user: str) -> str:
    return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()


def _cache_get(key: str):
    with _cache_lock:
        entry = _response_cache.get(key)
        if entry and (time.time() - entry["ts"] < _CACHE_TTL):
            return entry["data"]
        if entry:
            del _response_cache[key]
    return None


def _cache_set(key: str, data: dict):
    with _cache_lock:
        _response_cache[key] = {"data": data, "ts": time.time()}
        if len(_response_cache) > 500:  # cheap eviction, keep it bounded
            for k, _ in sorted(_response_cache.items(), key=lambda kv: kv[1]["ts"])[:100]:
                del _response_cache[k]


def _estimate_max_tokens(user_prompt: str) -> int:
    """Sizes the output token ceiling to the actual input instead of always
    allowing room for the maximum — generation time scales with the number
    of tokens produced, so a short snippet shouldn't pay for headroom a
    20,000-char submission would need. Rough rule of thumb: ~4 chars/token,
    and a fixed/explained response rarely exceeds ~1.3x the input length in
    tokens. Floored so tiny inputs still get enough room for a full
    explanation, ceilinged at the old flat 2000 for large inputs."""
    return max(500, min(2000, int(len(user_prompt) / 4 * 1.3)))


def _try_models_once(system: str, user: str, model_limits: dict):
    """Attempts every model in model_limits, in order, once each. Returns a
    result dict on the first success, or None if every model failed.
    Shared by the two-pass retry logic in _groq_call_with_usage."""
    for model in model_limits:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user}
                ],
                max_tokens=_estimate_max_tokens(user),
                temperature=0.1,
                timeout=10,  # was 20s — a dead/decommissioned model should fail fast, not stall the whole request
            )
            result = response.choices[0].message.content.strip()
            if result and len(result) > 20:
                usage = response.usage
                prompt_tokens = usage.prompt_tokens  if usage else 0
                output_tokens = usage.completion_tokens if usage else 0
                total_tokens  = usage.total_tokens   if usage else 0
                limit         = model_limits.get(model, 8192)
                limit_pct     = round((total_tokens / limit) * 100, 1) if limit else 0

                log.info(f"SUCCESS: {model} | prompt={prompt_tokens} out={output_tokens} "
                         f"total={total_tokens} ({limit_pct}% of {limit})")
                return {
                    "result":        result,
                    "model":         model,
                    "prompt_tokens": prompt_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens":  total_tokens,
                    "limit":         limit,
                    "limit_pct":     limit_pct,
                }
        except Exception as e:
            log.warning(f"FAILED {model}: {str(e)[:100]}")
            continue
    return None


def _groq_call_with_usage(system: str, user: str, use_cache: bool = True) -> dict:
    """
    Calls Groq API and returns a dict:
      {
        "result":        str,   # model response text
        "model":         str,   # which model actually responded
        "prompt_tokens": int,   # tokens used by system + user message
        "output_tokens": int,   # tokens in the response
        "total_tokens":  int,   # prompt + output combined
        "limit":         int,   # context window size for that model
        "limit_pct":     float, # percentage of context window used
        "cached":        bool,  # True if served from the response cache
      }
    Returns {"result": "", ...zeros...} only if every model fails on BOTH
    the cached model list and a forced-fresh refetch of it — see below.
    """
    key = _cache_key(system, user)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            log.info("Cache hit for Groq call")
            return {**cached, "cached": True}

    # Pass 1: try every model in the (possibly cached-up-to-an-hour-old) list.
    data = _try_models_once(system, user, _get_model_limits())

    # Pass 2: if that was a total wipeout, don't just give up — the cached
    # list itself might be stale (e.g. Groq deprecated one of these models
    # since we last checked, the exact failure mode that broke this app
    # once before). Force a live refetch and try once more before failing.
    if data is None:
        log.warning("All cached models failed — forcing a live model-list refresh and retrying once")
        data = _try_models_once(system, user, _get_model_limits(force_refresh=True))

    if data is not None:
        if use_cache:
            _cache_set(key, data)
        return {**data, "cached": False}

    return {
        "result":        "",
        "model":         "",
        "prompt_tokens": 0,
        "output_tokens": 0,
        "total_tokens":  0,
        "limit":         0,
        "limit_pct":     0.0,
        "cached":        False,
    }


def _groq_stream(system: str, user: str, use_cache: bool = True):
    """
    Generator version of _groq_call_with_usage for real token-by-token
    streaming, instead of the old approach of waiting for the full response
    and then fake-typing it out client-side.

    Yields dicts as they happen:
      {"type": "chunk", "text": "..."}                          — one per token/delta
      {"type": "done", "model", "prompt_tokens", "output_tokens",
                "total_tokens", "limit", "limit_pct", "cached"}  — exactly once, last
      {"type": "error", "message": "..."}                       — only if every model fails

    If the exact (system, user) pair is already cached from a prior
    non-streaming or streaming call, the cached result is replayed as a
    single immediate chunk rather than re-calling Groq at all.
    """
    key = _cache_key(system, user)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            log.info("Cache hit for Groq stream (replayed, not re-streamed)")
            yield {"type": "chunk", "text": cached["result"]}
            yield {"type": "done", **{k: v for k, v in cached.items() if k != "result"}, "cached": True}
            return

def _stream_models_once(system: str, user: str, model_limits: dict):
    """Attempts every model in model_limits, in order, yielding chunk/done
    events live as they arrive from Groq (true streaming, not buffered).

    Falls through to the next model only if a model fails before producing
    any visible output — once a model has started streaming real content to
    the user, we commit to it rather than silently switching mid-response
    (which would look like garbled, mixed output). A failure after content
    has already been shown yields an 'error' event instead of retrying."""
    for model in model_limits:
        got_any = False
        full_text = []
        prompt_tokens = output_tokens = total_tokens = 0
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user}
                ],
                max_tokens=_estimate_max_tokens(user),
                temperature=0.1,
                timeout=10,  # was 20s — fail fast on a dead model instead of stalling
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    got_any = True
                    full_text.append(delta)
                    yield {"type": "chunk", "text": delta}
                usage = getattr(chunk, "x_groq", None)
                usage = getattr(usage, "usage", None) if usage else getattr(chunk, "usage", None)
                if usage:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or prompt_tokens
                    output_tokens = getattr(usage, "completion_tokens", 0) or output_tokens
                    total_tokens  = getattr(usage, "total_tokens", 0) or total_tokens
        except Exception as e:
            log.warning(f"STREAM FAILED {model}: {str(e)[:100]}")
            if got_any:
                # Already showed real content to the user — don't silently
                # switch models mid-response, that produces confusing
                # mixed/garbled output. Surface the failure instead.
                yield {"type": "error", "message": f"Connection to {model} was interrupted."}
                return
            continue  # nothing shown yet — safe to try the next model

        if not got_any:
            continue

        result = "".join(full_text).strip()
        if len(result) <= 20:
            continue

        limit     = model_limits.get(model, 8192)
        limit_pct = round((total_tokens / limit) * 100, 1) if limit and total_tokens else 0.0
        log.info(f"STREAM SUCCESS: {model} | total={total_tokens} ({limit_pct}% of {limit})")
        yield {
            "type": "done", "model": model, "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens, "total_tokens": total_tokens,
            "limit": limit, "limit_pct": limit_pct, "_result_text": result,
        }
        return


def _groq_stream(system: str, user: str, use_cache: bool = True):
    """
    Generator version of _groq_call_with_usage for real token-by-token
    streaming, instead of the old approach of waiting for the full response
    and then fake-typing it out client-side.

    Yields dicts as they happen:
      {"type": "chunk", "text": "..."}                          — one per token/delta
      {"type": "done", "model", "prompt_tokens", "output_tokens",
                "total_tokens", "limit", "limit_pct", "cached"}  — exactly once, last
      {"type": "error", "message": "..."}                       — only if every model fails

    If the exact (system, user) pair is already cached from a prior
    non-streaming or streaming call, the cached result is replayed as a
    single immediate chunk rather than re-calling Groq at all.

    If every model in the cached model list fails, this automatically
    forces a live refresh of the model list and tries once more before
    giving up — same self-healing behavior as _groq_call_with_usage, so a
    stale cached model (e.g. one Groq just deprecated) doesn't just fail
    silently until the next hourly refresh.
    """
    key = _cache_key(system, user)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            log.info("Cache hit for Groq stream (replayed, not re-streamed)")
            yield {"type": "chunk", "text": cached["result"]}
            yield {"type": "done", **{k: v for k, v in cached.items() if k != "result"}, "cached": True}
            return

    for attempt, model_limits in enumerate([_get_model_limits(), None]):
        if model_limits is None:
            log.warning("All cached models failed to stream — forcing a live model-list refresh and retrying once")
            model_limits = _get_model_limits(force_refresh=True)

        done_event = None
        any_content_shown = False
        stop_entirely = False
        for event in _stream_models_once(system, user, model_limits):
            if event["type"] == "chunk":
                any_content_shown = True
                yield event
            elif event["type"] == "done":
                done_event = event
                result_text = done_event.pop("_result_text")
                if use_cache:
                    _cache_set(key, {"result": result_text, **done_event})
                yield {**done_event, "cached": False}
            elif event["type"] == "error":
                # Partial content was already shown to the user before this
                # model failed — don't retry with a fresh model list, that
                # would silently glue a second model's output onto the first
                # model's partial output and look broken. Stop here instead.
                yield event
                stop_entirely = True

        if done_event is not None or stop_entirely:
            return  # success, or a clean stop after partial content — either way, done

        if any_content_shown:
            return  # shouldn't normally happen without stop_entirely, but be safe

    yield {"type": "error", "message": "AI model unavailable — check your Groq API key or network."}


def _groq_explain(code: str, lang: str) -> str:
    try:
        system = f"You are an expert {lang} code reviewer. Be precise and specific."
        user   = f"""Analyze this {lang} code and list every bug, error, and bad practice.

Format each issue exactly like:
🔴 Line X:  <code line>
           =>  <what is wrong and exact fix>

Use 🔴 critical, 🟡 moderate, 🔵 minor.
Cover ALL: TypeError, missing self, ZeroDivisionError, SQL injection,
hardcoded secrets, mutable defaults, recursion without base case,
resource leaks, bare except, class variable bugs, index errors,
empty list crashes, wrong formulas, None returns, silent failures,
wrong operators like =+ instead of +=,
missing parentheses causing wrong order of operations.

CODE:
{code}

ISSUES:"""
        runtime = _execute_and_check(code, lang) if lang in ('python', 'c') else ""
        result  = _groq_call(system, user)
        combined = (result if result else _find_faults(code, lang))
        if runtime:
            combined += f"\n\n── Runtime Check ──\n{runtime}"
        return combined
    except Exception:
        return _find_faults(code, lang)

def _groq_fix(code: str, lang: str, max_retries: int = 1, time_budget: float = 9.0) -> dict:
    """
    Fixes bugs in `code`, then — for languages we can actually run locally
    (python: real execution, c: compile check) — VERIFIES the fix by running
    it and feeding any remaining error back to the model for another pass,
    instead of trusting the model's output on faith. This is the difference
    between "looks plausible" and "was actually checked."

    time_budget caps how long this whole function is allowed to keep
    retrying, in seconds — once exceeded, it stops and returns the best
    attempt so far rather than trying another round-trip to Groq. This is
    what keeps Analyze fast: a bounded worst case instead of an unbounded
    number of sequential network calls.

    For languages with no local execution backend (java, javascript), the
    model still gets an explicit instruction to reason about whole-program
    behavior rather than line-by-line syntax, but the result is unverified —
    reflected in the returned "verified" flag.

    Returns:
      {
        "code":       str,   # best fixed code we produced
        "verified":   bool,  # True only if we actually ran it and it passed
        "attempts":   int,   # how many fix attempts were made
        "last_error": str,   # remaining error text, if any, after all retries
      }
    """
    system = f"""You are an expert {lang} programmer doing a real code review, not a
syntax linter. Fix bugs so the program is CORRECT end-to-end — meaning: if
someone runs it with realistic inputs, it produces the result a reader would
actually expect, not just "no crash." That includes:
- Off-by-one errors (e.g. range(len(x)+1), out-of-bounds access)
- Wrong/missing dictionary keys that would KeyError or silently return None
- Type errors (e.g. concatenating str + int without conversion)
- Dead code, unreachable branches, or logic that can never trigger
- Variables/data structures that LOOK connected to a feature (e.g. same name
  or similar purpose) but are actually unrelated and would confuse a reader
  of the output — if you find this and it's not safe to remove without
  changing intended behavior, add a single short '# NOTE:' comment directly
  above it explaining the disconnect. Do not invent new features or rewrite
  the program's intent — only fix actual bugs and flag genuine confusion.
Never add markdown, never add explanations outside the code, never add code
fences. Never add imports from other languages. If language is javascript do
NOT add java imports like java.sql or java.util. Return raw {lang} code only."""

    user_base = f"""Fix every bug in this {lang} code completely and make sure the
program's actual runtime behavior is correct, not just syntactically valid.

Fix ALL of these if present:
- Missing 'self' in class methods
- Wrong method calls like withdraw(self=acc1)
- ZeroDivisionError — add zero check
- Empty list crash — add length check
- Empty string index crash — add length check
- Off-by-one errors (range(len(x)+1), index len(x), etc.)
- Missing or wrong dictionary keys that would KeyError
- Mutable default args — use None and assign inside
- SQL injection — use parameterised queries
- Hardcoded passwords or api keys — use environment variables
- Bare except — use specific exception
- File not closed — use with open()
- Recursion without base case — add base case
- == None — use is None
- Class variables shared across instances — move to constructor
- Wrong formula logic — fix the math
- Wrong operators like =+ — fix to +=
- Missing parentheses wrong order of operations
- Functions returning undefined or None — return proper value
- Type mismatches (e.g. string + int) — convert explicitly
- Missing imports — add at top
- Incomplete logic — fix fully
- Methods modifying original data — use copy
- var keyword in javascript — use let or const
- delete on array index — use splice instead
- innerHTML — use textContent instead
- JSON.parse without try catch — wrap in try catch
- setTimeout with string — pass function instead
- console.log — remove in production

Return ONLY the fixed runnable {lang} code. No explanation outside the code. No markdown.

BUGGY CODE:
{code}

FIXED CODE:"""

    def _clean(raw: str) -> str:
        raw = re.sub(r'^```[\w]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        return raw.strip()

    attempt = 0
    current_error = None
    fixed = None
    _t0 = time.time()

    while attempt < max_retries + 1:  # max_retries=1 means "1 retry" = up to 2 attempts total
        if attempt > 0 and (time.time() - _t0) > time_budget:
            log.info(f"_groq_fix stopping early — time budget ({time_budget}s) exceeded after {attempt} attempt(s)")
            break
        attempt += 1
        prompt = user_base if current_error is None else (
            user_base + f"\n\nYour previous fix still fails when actually run, with this "
            f"error:\n{current_error}\n\nFix that too. Return ONLY the corrected code."
        )
        try:
            result = _groq_call(system, prompt)
        except Exception:
            result = ""

        if not result:
            fixed = fixed or _pattern_fix(code, lang)
            break

        fixed = _clean(result)
        if len(fixed) <= 20:
            fixed = _pattern_fix(code, lang)
            break

        # Verify: only python (real execution) and c (compile check) have a
        # local backend. Java/JS get one shot, unverified.
        if lang == 'python':
            check = _execute_and_check(fixed, 'python')
            if check.startswith('✅'):
                return {"code": fixed, "verified": True, "attempts": attempt, "last_error": ""}
            if check.startswith('⚠'):
                # sandbox refused to run it (e.g. legitimately uses os/subprocess) —
                # can't verify, but don't treat that as "still broken"
                return {"code": fixed, "verified": False, "attempts": attempt, "last_error": check}
            current_error = (check.replace('🔴 RUNTIME ERROR:\n', '')
                                   .replace('🔴 SYNTAX ERROR:\n', '').strip())
            continue
        elif lang == 'c':
            check = _execute_and_check(fixed, 'c')
            if check.startswith('✅'):
                return {"code": fixed, "verified": True, "attempts": attempt, "last_error": ""}
            if check.startswith('⚠'):
                return {"code": fixed, "verified": False, "attempts": attempt, "last_error": check}
            current_error = check.replace('🔴 COMPILE ERROR:\n', '').strip()
            continue
        else:
            return {"code": fixed, "verified": False, "attempts": attempt, "last_error": ""}

    return {
        "code": fixed or _pattern_fix(code, lang),
        "verified": False,
        "attempts": attempt,
        "last_error": current_error or "",
    }



def _pattern_fix(code: str, lang: str) -> str:
    lines = code.splitlines()
    out = []
    imports_to_add = []

    for line in lines:
        fixed = line
        if lang == 'python':
            fixed = re.sub(r'==\s*None', 'is None', fixed)
            fixed = re.sub(r'!=\s*None', 'is not None', fixed)
            fixed = re.sub(r'except\s*:', 'except Exception as e:', fixed)
            fixed = re.sub(r'hashlib\.md5\s*\(', 'hashlib.sha256(', fixed)
            fixed = re.sub(r'hashlib\.sha1\s*\(', 'hashlib.sha256(', fixed)
            fixed = re.sub(r'os\.system\s*\(', 'subprocess.run(', fixed)
            fixed = re.sub(
                r"(password\s*=\s*)['\"].+['\"]",
                r"\1os.environ.get('PASSWORD', '')",
                fixed, flags=re.IGNORECASE
            )
            fixed = re.sub(
                r"(api_key\s*=\s*)['\"].+['\"]",
                r"\1os.environ.get('API_KEY', '')",
                fixed, flags=re.IGNORECASE
            )
            m_self = re.match(r'^(\s{4,}def\s+)(\w+)\s*\((?!self\b)([^)]*)\)\s*:', fixed)
            if m_self and not m_self.group(2).startswith('__'):
                indent = m_self.group(1)
                fname  = m_self.group(2)
                args   = m_self.group(3).strip()
                fixed  = f'{indent}{fname}(self, {args}):' if args else f'{indent}{fname}(self):'

            m = re.match(r'^(\s*def\s+\w+\s*\()(.*)(\)\s*:)', fixed)
            if m:
                args = m.group(2)
                mutable_vars = []
                for var in re.findall(r'(\w+)\s*=\s*\[\]', args):
                    mutable_vars.append((var, '[]'))
                for var in re.findall(r'(\w+)\s*=\s*\{\}', args):
                    mutable_vars.append((var, '{}'))
                args = re.sub(r'(\w+)\s*=\s*\[\]', r'\1=None', args)
                args = re.sub(r'(\w+)\s*=\s*\{\}', r'\1=None', args)
                fixed = m.group(1) + args + m.group(3)
                out.append(fixed)
                indent = re.match(r'^(\s*)', line).group(1) + '    '
                for var, typ in mutable_vars:
                    default = '[]' if typ == '[]' else '{}'
                    out.append(f'{indent}if {var} is None: {var} = {default}')
                continue

        elif lang == 'javascript':
            fixed = re.sub(r'\bvar\s+', 'let ', fixed)
            fixed = re.sub(r'\.innerHTML\s*=', '.textContent =', fixed)
        elif lang == 'java':
            fixed = re.sub(r'\.length\s*\(\s*\)\s*==\s*0', '.isEmpty()', fixed)

        out.append(fixed)

    result = '\n'.join(out)

    if lang == 'python':
        if 'os.environ' in result and 'import os' not in result:
            imports_to_add.append('import os')
        if 'subprocess.run' in result and 'import subprocess' not in result:
            imports_to_add.append('import subprocess')
        if 'logging' in result and 'import logging' not in result:
            imports_to_add.append('import logging')
        if 'hashlib' in result and 'import hashlib' not in result:
            imports_to_add.append('import hashlib')

    if imports_to_add:
        result = '\n'.join(imports_to_add) + '\n\n' + result

    return result

_PENALTY = {1: 5, 2: 12, 3: 22}

def _has_critical_patterns(code: str, lang: str) -> bool:
    """Cheap, instant check (no LLM, no execution) for whether any
    SEVERITY-3 rule pattern matches — used to decide whether genuinely
    verified-correct code deserves a high-confidence score floor."""
    return any(re.search(p, code) for p, _, s in PATTERNS.get(lang, []) if s == 3)


def _score(code: str, lang: str) -> int:
    penalty = sum(_PENALTY[s] for p,_,s in PATTERNS.get(lang,[]) if re.search(p, code))
    if lang == 'python':
        penalty += len(_ast_issues(code)) * 10
        penalty += len(_pylint_issues(code)) * 3
    return max(0, min(100, 100 - penalty))

def _ml_blend(code: str, lang: str, base: int) -> int:
    _load_models()
    try:
        m = _adv_model or _bug_model
        if m:
            p = m.predict_proba([code + ' ' + lang])[0]
            return int(base * 0.5 + (1.0 - p[1]) * 100 * 0.5)
    except Exception:
        pass
    return base

def _message(score: int) -> str:
    if score == 0:   return "Paste code above and click Analyse."
    if score >= 95:  return "Excellent — no issues found."
    if score >= 85:  return "Good quality. Minor improvements available."
    if score >= 70:  return "Decent code. A few issues to address."
    if score >= 50:  return "Moderate issues. Review recommended."
    if score >= 30:  return "Multiple problems found. Refactoring needed."
    return "Critical issues. Major revision required."

# Hard cap on submitted code size — protects against giant pastes blowing up
# Groq token usage / cost and locking up the (single-process) Flask server.
MAX_CODE_CHARS = 20000


def _compute_diff(original: str, corrected: str) -> list:
    """
    Line-based diff between original and corrected code, returned as a list
    of {type, old_line, new_line, old_no, new_no} rows the frontend can
    render as a two-column (or unified) diff view. type is one of:
    'equal', 'replace', 'insert', 'delete'.
    """
    import difflib
    old_lines = original.splitlines()
    new_lines = corrected.splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k, (oi, ni) in enumerate(zip(range(i1, i2), range(j1, j2))):
                rows.append({"type": "equal", "old_line": old_lines[oi], "new_line": new_lines[ni],
                             "old_no": oi + 1, "new_no": ni + 1})
        elif tag == 'replace':
            span = max(i2 - i1, j2 - j1)
            for k in range(span):
                oi = i1 + k if i1 + k < i2 else None
                ni = j1 + k if j1 + k < j2 else None
                rows.append({
                    "type": "replace",
                    "old_line": old_lines[oi] if oi is not None else None,
                    "new_line": new_lines[ni] if ni is not None else None,
                    "old_no": (oi + 1) if oi is not None else None,
                    "new_no": (ni + 1) if ni is not None else None,
                })
        elif tag == 'delete':
            for oi in range(i1, i2):
                rows.append({"type": "delete", "old_line": old_lines[oi], "new_line": None,
                             "old_no": oi + 1, "new_no": None})
        elif tag == 'insert':
            for ni in range(j1, j2):
                rows.append({"type": "insert", "old_line": None, "new_line": new_lines[ni],
                             "old_no": None, "new_no": ni + 1})
    return rows


def analyze_logic(code: str, lang: str = 'python') -> dict:
    if not code.strip():
        return {"score":0,"confidence":"0%","msg":"Paste code above and click Analyse.",
                "old_line":"","full_code":"","lines":0,"chars":0, "diff": []}

    if len(code) > MAX_CODE_CHARS:
        return {
            "score": 0, "confidence": "0%",
            "msg": f"Input too large ({len(code):,} chars). Limit is {MAX_CODE_CHARS:,} chars — "
                   f"split it up or trim before re-analyzing.",
            "old_line": "", "full_code": "", "lines": len(code.splitlines()), "chars": len(code), "diff": [],
        }

    # _score/_ml_blend (regex+AST+pylint+ML, all local CPU work) don't
    # depend on Groq at all, and _groq_explain/_groq_fix don't depend on the
    # score — so all three run in the SAME parallel batch now instead of
    # scoring finishing first and only then starting the network calls.
    with ThreadPoolExecutor(max_workers=3) as pool:
        score_future   = pool.submit(lambda: _ml_blend(code, lang, _score(code, lang)))
        explain_future = pool.submit(_groq_explain, code, lang)
        fix_future     = pool.submit(_groq_fix, code, lang)
        final      = max(0, min(100, score_future.result()))
        faults     = explain_future.result()
        fix_result = fix_future.result()

    corrected     = fix_result["code"]
    verified      = fix_result["verified"]
    fix_attempts  = fix_result["attempts"]
    last_error    = fix_result["last_error"]

    # Verified-correctness floor: the rule+AST+pylint+ML score formula is
    # tuned for CATCHING bugs, which makes it a noisy, overly harsh judge of
    # code we already have real evidence is fine — style nitpicks (pylint)
    # and a small-dataset ML model can drag down code that actually runs
    # correctly with zero critical findings. So: if we've PROVEN the code
    # executes successfully (not just "the model says so") AND our own
    # rule-based scan finds no severity-3 (critical) pattern, don't let a
    # noisy secondary signal keep the score below what verified-correct
    # code deserves.
    _VERIFIED_FLOOR = 92
    original_ran_ok = ('── Runtime Check ──\n✅' in faults)
    if original_ran_ok and not _has_critical_patterns(code, lang):
        final = max(final, _VERIFIED_FLOOR)

    # Auto re-score: run the same scoring pipeline on the corrected code so
    # the user immediately sees whether the fix actually helped, instead of
    # having to paste it back in and click Analyze a second time.
    corrected_final = final
    corrected_msg = ""
    improved = None
    if corrected and corrected.strip() and corrected.strip() != code.strip():
        try:
            c_base  = _score(corrected, lang)
            corrected_final = max(0, min(100, _ml_blend(corrected, lang, c_base)))
            if verified and not _has_critical_patterns(corrected, lang):
                corrected_final = max(corrected_final, _VERIFIED_FLOOR)
            corrected_msg = _message(corrected_final)
            improved = corrected_final >= final
        except Exception as e:
            log.warning(f"Auto re-score of corrected code failed: {e}")
            corrected_final = final
            corrected_msg = ""

    # Verification status shown to the user — this is the "did we actually
    # check it or just trust the model" signal.
    if lang not in ('python', 'c'):
        verify_note = f"⚠ Not execution-verified ({lang} has no local run/compile check available here)."
    elif verified:
        verify_note = f"✅ Verified: the corrected code was actually run and passed (attempt {fix_attempts})."
    elif last_error and last_error.strip().startswith('⚠'):
        # This ⚠ path means execution was deliberately SKIPPED (interactive
        # input(), or a genuinely unsafe operation) — not that the fix was
        # tried and found broken. Saying "still fails" here would be actively
        # wrong and misleading, so it gets its own honest phrasing.
        verify_note = f"⚠ Not verified — {last_error[1:].strip()}"
    elif last_error:
        verify_note = (f"⚠ Still fails after {fix_attempts} fix attempt(s): {last_error[:300]}"
                        f"{'…' if len(last_error) > 300 else ''}")
    else:
        verify_note = "⚠ Not execution-verified."

    # Diff between original and corrected code, for the diff-view toggle.
    diff_rows = _compute_diff(code, corrected) if corrected and corrected.strip() else []

    return {
        "score":      final,
        "confidence": f"{final}%",
        "msg":        _message(final),
        "old_line":   faults,
        "full_code":  corrected,
        "lines":      len(code.splitlines()),
        "chars":      len(code),
        "diff":       diff_rows,
        # New fields — safe to ignore in older frontend code, used by the
        # updated UI to show a before/after score.
        "corrected_score":      corrected_final,
        "corrected_confidence": f"{corrected_final}%",
        "corrected_msg":        corrected_msg,
        "improved":             improved,
        # New — actual verification status of the fix, not just the model's word for it.
        "verified":             verified,
        "verify_note":          verify_note,
        "fix_attempts":         fix_attempts,
    }