"""
generate_data.py — expands dataset/code_dataset.csv with synthetic samples.
Run: python generate_data.py
"""
import csv, os

EXTRA_SAMPLES = [
    {"code": "def safe_divide(a, b):\n    return a // b", "language": "python", "bug_type": "zero_division", "has_bug": 1,
     "corrected_code": "def safe_divide(a, b):\n    if b == 0:\n        return None\n    return a // b", "description": "Integer floor division without zero guard"},
    {"code": "result = [x**2 for x in range(10)]", "language": "python", "bug_type": "none", "has_bug": 0,
     "corrected_code": "result = [x**2 for x in range(10)]", "description": "Clean list comprehension"},
    {"code": "import pickle\nobj = pickle.loads(user_data)", "language": "python", "bug_type": "insecure_deserialize", "has_bug": 1,
     "corrected_code": "import json\nobj = json.loads(user_data)", "description": "pickle.loads on untrusted data enables RCE"},
    {"code": "def append_all(items, target=[]):\n    target.extend(items)\n    return target", "language": "python", "bug_type": "mutable_default", "has_bug": 1,
     "corrected_code": "def append_all(items, target=None):\n    if target is None:\n        target = []\n    target.extend(items)\n    return target", "description": "Mutable default list accumulates across calls"},
    {"code": "import subprocess\ncmd = 'ls ' + user_input\nsubprocess.run(cmd, shell=True)", "language": "python", "bug_type": "command_injection", "has_bug": 1,
     "corrected_code": "import subprocess\nsubprocess.run(['ls', user_input], shell=False)", "description": "shell=True with user input allows command injection"},
    {"code": "assert user_input != '', 'Input required'", "language": "python", "bug_type": "assert_removed", "has_bug": 1,
     "corrected_code": "if not user_input:\n    raise ValueError('Input required')", "description": "assert can be disabled with -O flag"},
    {"code": "for key in dict.keys():\n    print(key)", "language": "python", "bug_type": "antipattern", "has_bug": 1,
     "corrected_code": "for key in dict:\n    print(key)", "description": "Unnecessary .keys() call"},
    {"code": "if type(x) == int:\n    pass", "language": "python", "bug_type": "antipattern", "has_bug": 1,
     "corrected_code": "if isinstance(x, int):\n    pass", "description": "Use isinstance() not type() =="},
    {"code": "def read_lines(path):\n    return open(path).readlines()", "language": "python", "bug_type": "unclosed_file", "has_bug": 1,
     "corrected_code": "def read_lines(path):\n    with open(path) as f:\n        return f.readlines()", "description": "File handle never closed"},
    {"code": "n = len(s)\nfor i in range(n):\n    for j in range(n):\n        check(s[i], s[j])", "language": "python", "bug_type": "inefficient", "has_bug": 1,
     "corrected_code": "from itertools import product\nfor a, b in product(s, s):\n    check(a, b)", "description": "O(n²) nested loop"},
    {"code": "import hashlib\ndef hash_password(p):\n    return hashlib.md5(p.encode()).hexdigest()", "language": "python", "bug_type": "weak_hash", "has_bug": 1,
     "corrected_code": "import bcrypt\ndef hash_password(p):\n    return bcrypt.hashpw(p.encode(), bcrypt.gensalt())", "description": "MD5 is broken for passwords"},
    {"code": "def generate_token():\n    import random\n    return str(random.randint(100000, 999999))", "language": "python", "bug_type": "weak_random", "has_bug": 1,
     "corrected_code": "import secrets\ndef generate_token():\n    return secrets.token_hex(16)", "description": "random module is not cryptographically secure"},
    {"code": "data = []\nfor item in source:\n    data.append(transform(item))", "language": "python", "bug_type": "antipattern", "has_bug": 1,
     "corrected_code": "data = [transform(item) for item in source]", "description": "Manual append loop; use list comprehension"},
    {"code": "nums = list(range(1000000))\nevens = [x for x in nums if x % 2 == 0]", "language": "python", "bug_type": "memory_list", "has_bug": 1,
     "corrected_code": "evens = (x for x in range(1000000) if x % 2 == 0)", "description": "Builds entire list in memory; use generator"},
    # Java
    {"code": "int result = Integer.parseInt(userInput);", "language": "java", "bug_type": "uncaught_exception", "has_bug": 1,
     "corrected_code": "int result;\ntry {\n    result = Integer.parseInt(userInput);\n} catch (NumberFormatException e) {\n    result = 0;\n}", "description": "parseInt throws uncaught NumberFormatException"},
    {"code": "public void processAll(List<String> items) {\n    for (int i = 0; i <= items.size(); i++) {\n        process(items.get(i));\n    }\n}", "language": "java", "bug_type": "off_by_one", "has_bug": 1,
     "corrected_code": "public void processAll(List<String> items) {\n    for (int i = 0; i < items.size(); i++) {\n        process(items.get(i));\n    }\n}", "description": "Off-by-one IndexOutOfBoundsException"},
    {"code": "Optional<User> user = repo.findById(id);\nSystem.out.println(user.get().getName());", "language": "java", "bug_type": "optional_misuse", "has_bug": 1,
     "corrected_code": "Optional<User> user = repo.findById(id);\nuser.ifPresent(u -> System.out.println(u.getName()));", "description": "Optional.get() without isPresent check"},
    {"code": "Map<String,String> m = new HashMap<>();\nString val = m.get(\"missing\").toUpperCase();", "language": "java", "bug_type": "null_pointer", "has_bug": 1,
     "corrected_code": "Map<String,String> m = new HashMap<>();\nString val = m.getOrDefault(\"missing\", \"\").toUpperCase();", "description": "map.get returns null for missing key"},
    # JavaScript
    {"code": "const users = await db.query('SELECT * FROM users WHERE name = \"' + name + '\"');", "language": "javascript", "bug_type": "sql_injection", "has_bug": 1,
     "corrected_code": "const users = await db.query('SELECT * FROM users WHERE name = $1', [name]);", "description": "SQL injection via string concatenation"},
    {"code": "const sum = arr.reduce((a, b) => a + b);", "language": "javascript", "bug_type": "no_initial_value", "has_bug": 1,
     "corrected_code": "const sum = arr.reduce((a, b) => a + b, 0);", "description": "reduce without initial value throws on empty array"},
    {"code": "const regex = new RegExp(userInput);", "language": "javascript", "bug_type": "redos", "has_bug": 1,
     "corrected_code": "const escaped = userInput.replace(/[.*+?^${}()|[\\\\]\\\\\\\\]/g, '\\\\\\\\$&');\nconst regex = new RegExp(escaped);", "description": "Unescaped user input in RegExp allows ReDoS"},
    {"code": "element.addEventListener('click', () => {\n  element.addEventListener('click', handler);\n});", "language": "javascript", "bug_type": "event_leak", "has_bug": 1,
     "corrected_code": "element.addEventListener('click', handler);", "description": "Nested addEventListener adds duplicate listeners"},
    {"code": "const clone = JSON.parse(JSON.stringify(obj));", "language": "javascript", "bug_type": "none", "has_bug": 0,
     "corrected_code": "const clone = structuredClone(obj);", "description": "JSON clone loses non-serialisable values"},
    {"code": "const API_KEY = 'sk-abc123';", "language": "javascript", "bug_type": "hardcoded_secret", "has_bug": 1,
     "corrected_code": "const API_KEY = process.env.API_KEY;", "description": "Hardcoded API key in source"},
    {"code": "var xhr = new XMLHttpRequest();\nxhr.open('GET', url, false);\nxhr.send();", "language": "javascript", "bug_type": "sync_xhr", "has_bug": 1,
     "corrected_code": "const res = await fetch(url);\nconst data = await res.json();", "description": "Synchronous XHR blocks the UI thread"},
]

def main():
    base = os.path.join(os.path.dirname(__file__), 'dataset', 'code_dataset.csv')
    fieldnames = ["code","language","bug_type","has_bug","corrected_code","description"]
    existing, existing_codes = [], set()
    if os.path.exists(base):
        with open(base, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                existing.append(row)
                existing_codes.add(row['code'])
    added = 0
    for s in EXTRA_SAMPLES:
        if s['code'] not in existing_codes:
            existing.append({k: str(v) for k,v in s.items()})
            existing_codes.add(s['code'])
            added += 1
    with open(base, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existing)
    print(f"Done — {len(existing)} total rows ({added} new added)")

if __name__ == '__main__':
    main()
