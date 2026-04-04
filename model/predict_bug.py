"""
predict_bug.py — CLI tool to analyse a code file.
Usage:
    python predict_bug.py myfile.py
    python predict_bug.py myfile.js --lang javascript
    python predict_bug.py myfile.java --lang java
"""
import sys, os, argparse
from code_analyzer import analyze_logic

EXT_TO_LANG = {'.py': 'python', '.java': 'java', '.js': 'javascript', '.ts': 'javascript'}

def main():
    parser = argparse.ArgumentParser(description='ANCHOR ELITE — CLI Code Analyser')
    parser.add_argument('file', help='Path to source file')
    parser.add_argument('--lang', default=None, help='Language override (python|java|javascript)')
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: file not found: {args.file}")
        sys.exit(1)

    with open(args.file, encoding='utf-8') as f:
        code = f.read()

    ext  = os.path.splitext(args.file)[1].lower()
    lang = args.lang or EXT_TO_LANG.get(ext, 'python')

    print(f"\n{'─'*60}")
    print(f"  ANCHOR ELITE — Analysing {args.file} ({lang})")
    print(f"{'─'*60}")

    result = analyze_logic(code, lang)

    icon = '✅' if result['score'] >= 85 else '⚠️' if result['score'] >= 50 else '🚨'
    print(f"\n{icon} Stability Score : {result['score']}/100 ({result['confidence']})")
    print(f"   Verdict        : {result['msg']}")
    print(f"   Lines / Chars  : {result['lines']} / {result['chars']}")

    if result['old_line']:
        print(f"\n{'─'*60}")
        print("  FAULTS DETECTED")
        print(f"{'─'*60}")
        print(result['old_line'])

    if result['full_code']:
        out_ext  = {'python': '.py', 'java': '.java', 'javascript': '.js'}.get(lang, '.txt')
        out_path = args.file.replace(ext, f'_fixed{out_ext}')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(result['full_code'])
        print(f"\n✅ Corrected code saved to: {out_path}")

    print(f"{'─'*60}\n")

if __name__ == '__main__':
    main()
