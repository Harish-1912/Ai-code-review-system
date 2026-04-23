import re, ast, pickle, os, time, subprocess, tempfile
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("API_KEY")
client = Groq(api_key=GROQ_API_KEY)

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
    # Python execution
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                         delete=False, encoding='utf-8') as f:
            f.write(code)
            tmp = f.name
        result = subprocess.run(
            ['python', tmp],
            capture_output=True, text=True, timeout=10
        )
        os.unlink(tmp)
        if result.returncode != 0:
            return f"🔴 RUNTIME ERROR:\n{result.stderr.strip()}"
        return f"✅ Runs successfully. Output:\n{result.stdout.strip()}"
    except Exception as e:
        return f"🔴 Execution failed: {e}"


# ── Updated _groq_call — returns dict with result + real token usage ──────────
def _groq_call(system: str, user: str) -> str:
    """
    Calls Groq API and returns just the text result (str).
    Use _groq_call_with_usage() when you need token counts.
    """
    data = _groq_call_with_usage(system, user)
    return data["result"]


def _groq_call_with_usage(system: str, user: str) -> dict:
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
      }
    Returns {"result": "", ...zeros...} if all models fail.
    """
    # Context window sizes per model
    MODEL_LIMITS = {
        "llama-3.3-70b-versatile": 128000,
        "llama3-70b-8192":          8192,
        "mixtral-8x7b-32768":      32768,
        "gemma2-9b-it":             8192,
    }
    models = list(MODEL_LIMITS.keys())

    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user}
                ],
                max_tokens=2000,
                temperature=0.1,
                timeout=20
            )
            result = response.choices[0].message.content.strip()
            if result and len(result) > 20:
                # Extract real token usage from Groq response
                usage = response.usage
                prompt_tokens = usage.prompt_tokens  if usage else 0
                output_tokens = usage.completion_tokens if usage else 0
                total_tokens  = usage.total_tokens   if usage else 0
                limit         = MODEL_LIMITS.get(model, 8192)
                limit_pct     = round((total_tokens / limit) * 100, 1) if limit else 0

                print(f"SUCCESS: {model} | prompt={prompt_tokens} out={output_tokens} total={total_tokens} ({limit_pct}% of {limit})")
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
            print(f"FAILED {model}: {str(e)[:100]}")
            continue

    return {
        "result":        "",
        "model":         "",
        "prompt_tokens": 0,
        "output_tokens": 0,
        "total_tokens":  0,
        "limit":         0,
        "limit_pct":     0.0,
    }


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

def _groq_fix(code: str, lang: str) -> str:
    try:
        system = f"""You are an expert {lang} programmer.
Fix ALL bugs and return only clean runnable {lang} code.
Never add markdown, never add explanations, never add code blocks.
Never add imports from other languages.
If language is javascript do NOT add any java imports like java.sql or java.util.
Return raw {lang} code only."""

        user = f"""Fix every bug in this {lang} code completely.

Fix ALL of these if present:
- Missing 'self' in class methods
- Wrong method calls like withdraw(self=acc1)
- ZeroDivisionError — add zero check
- Empty list crash — add length check
- Empty string index crash — add length check
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
- Missing imports — add at top
- Incomplete logic — fix fully
- Methods modifying original data — use copy
- var keyword in javascript — use let or const
- delete on array index — use splice instead
- innerHTML — use textContent instead
- JSON.parse without try catch — wrap in try catch
- setTimeout with string — pass function instead
- console.log — remove in production

Return ONLY the fixed runnable {lang} code. No explanation. No markdown.

BUGGY CODE:
{code}

FIXED CODE:"""

        result = _groq_call(system, user)
        if result:
            result = re.sub(r'^```[\w]*\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
            result = result.strip()
            if len(result) > 20:
                return result
        return _pattern_fix(code, lang)
    except Exception:
        return _pattern_fix(code, lang)

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

def analyze_logic(code: str, lang: str = 'python') -> dict:
    if not code.strip():
        return {"score":0,"confidence":"0%","msg":"Paste code above and click Analyse.",
                "old_line":"","full_code":"","lines":0,"chars":0}

    base      = _score(code, lang)
    final     = max(0, min(100, _ml_blend(code, lang, base)))
    faults    = _groq_explain(code, lang)
    corrected = _groq_fix(code, lang)

    return {
        "score":      final,
        "confidence": f"{final}%",
        "msg":        _message(final),
        "old_line":   faults,
        "full_code":  corrected,
        "lines":      len(code.splitlines()),
        "chars":      len(code),
    }