"""
train_model.py
Trains bug-detection and correction models from dataset/code_dataset.csv.
Produces:
    models/vectorizer.pkl
    models/bug_model.pkl
    models/advanced_bug_model.pkl
Run: python train_model.py
"""

import os, csv, pickle, json
from collections import Counter

# ── Try scikit-learn (optional but gives better accuracy) ──────────────────
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import classification_report
    import numpy as np
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    print("scikit-learn not found — using built-in rule model only.")

DATASET_PATH = os.path.join(os.path.dirname(__file__), '..', 'dataset', 'code_dataset.csv')
MODEL_DIR    = os.path.join(os.path.dirname(__file__), 'models')


# ──────────────────────────────────────────────────────────────────────────
# 1.  Load dataset
# ──────────────────────────────────────────────────────────────────────────
def load_dataset():
    rows = []
    with open(DATASET_PATH, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


# ──────────────────────────────────────────────────────────────────────────
# 2.  Feature engineering
# ──────────────────────────────────────────────────────────────────────────
def extract_features(code: str, lang: str) -> dict:
    """Hand-crafted feature vector used by the rule model."""
    import re
    return {
        "len":              len(code),
        "lines":            code.count('\n'),
        "has_try":          int(bool(re.search(r'\btry\b', code))),
        "has_except":       int(bool(re.search(r'\bexcept\b', code))),
        "bare_except":      int(bool(re.search(r'except\s*:', code))),
        "has_eval":         int(bool(re.search(r'\beval\s*\(', code))),
        "has_exec":         int(bool(re.search(r'\bexec\s*\(', code))),
        "has_global":       int(bool(re.search(r'\bglobal\b', code))),
        "has_sleep":        int(bool(re.search(r'sleep\s*\(', code))),
        "has_none_eq":      int(bool(re.search(r'==\s*None|!=\s*None', code))),
        "has_float_eq":     int(bool(re.search(r'==\s*0\.\d+|0\.\d+\s*==', code))),
        "has_loose_eq":     int(bool(re.search(r'(?<!=)={1}(?!=)', code) and lang == 'javascript')),
        "has_var":          int(bool(re.search(r'\bvar\b', code) and lang == 'javascript')),
        "has_innerhtml":    int(bool(re.search(r'innerHTML', code))),
        "has_sql_concat":   int(bool(re.search(r'SELECT.*\+|INSERT.*\+|UPDATE.*\+', code))),
        "has_shell_true":   int(bool(re.search(r'shell\s*=\s*True', code))),
        "has_pickle":       int(bool(re.search(r'pickle\.loads', code))),
        "has_md5":          int(bool(re.search(r'md5\(', code))),
        "has_hardcoded_pw": int(bool(re.search(r'password\s*=\s*["\']', code, re.IGNORECASE))),
        "has_open_no_with": int(bool(re.search(r'(?<!with )open\(', code))),
        "has_no_return":    int(bool(re.search(r'def \w+\([^)]*\):\s*\n(?:\s+(?!return)\S.*\n)*\s*$', code))),
        "has_range_len":    int(bool(re.search(r'range\(len\(', code))),
        "has_assert":       int(bool(re.search(r'\bassert\b', code))),
        "has_star_import":  int(bool(re.search(r'from .* import \*|import \*', code))),
        "lang_py":          int(lang == 'python'),
        "lang_java":        int(lang == 'java'),
        "lang_js":          int(lang == 'javascript'),
    }


# ──────────────────────────────────────────────────────────────────────────
# 3a.  Rule-based model (pure Python, no sklearn required)
# ──────────────────────────────────────────────────────────────────────────
class RuleModel:
    """
    Weighted rule classifier.
    Each feature has a weight; the sum decides has_bug probability.
    """
    WEIGHTS = {
        "bare_except": 0.7, "has_eval": 0.9, "has_exec": 0.85,
        "has_global": 0.3, "has_sleep": 0.2, "has_none_eq": 0.5,
        "has_float_eq": 0.5, "has_loose_eq": 0.6, "has_var": 0.3,
        "has_innerhtml": 0.6, "has_sql_concat": 0.9, "has_shell_true": 0.8,
        "has_pickle": 0.8, "has_md5": 0.7, "has_hardcoded_pw": 0.9,
        "has_open_no_with": 0.6, "has_range_len": 0.3, "has_assert": 0.25,
        "has_star_import": 0.35, "has_no_return": 0.4,
    }

    def predict_proba(self, features: dict) -> float:
        score = sum(self.WEIGHTS.get(k, 0) * v for k, v in features.items())
        # sigmoid-like normalisation
        return min(1.0, score / 3.0)

    def predict(self, features: dict) -> int:
        return 1 if self.predict_proba(features) >= 0.4 else 0

    def accuracy(self, rows) -> float:
        correct = 0
        for row in rows:
            feat = extract_features(row['code'], row['language'])
            pred = self.predict(feat)
            correct += int(pred == int(row['has_bug']))
        return correct / len(rows) if rows else 0.0


# ──────────────────────────────────────────────────────────────────────────
# 3b.  Sklearn ML models (optional)
# ──────────────────────────────────────────────────────────────────────────
def train_sklearn_models(rows):
    codes  = [r['code'] + ' ' + r['language'] for r in rows]
    labels = [int(r['has_bug']) for r in rows]

    X_train, X_test, y_train, y_test = train_test_split(
        codes, labels, test_size=0.2, random_state=42, stratify=labels
    )

    # Basic model — Logistic Regression on TF-IDF
    basic = Pipeline([
        ('tfidf', TfidfVectorizer(analyzer='char_wb', ngram_range=(2,4),
                                  max_features=8000, sublinear_tf=True)),
        ('clf',   LogisticRegression(max_iter=1000, C=1.0, class_weight='balanced'))
    ])
    basic.fit(X_train, y_train)

    # Advanced model — Gradient Boosting
    advanced = Pipeline([
        ('tfidf', TfidfVectorizer(analyzer='char_wb', ngram_range=(2,5),
                                  max_features=12000, sublinear_tf=True)),
        ('clf',   GradientBoostingClassifier(n_estimators=120, max_depth=4,
                                              learning_rate=0.1, random_state=42))
    ])
    advanced.fit(X_train, y_train)

    y_pred_basic    = basic.predict(X_test)
    y_pred_advanced = advanced.predict(X_test)

    print("\n── Basic Model (Logistic Regression) ──")
    print(classification_report(y_test, y_pred_basic, target_names=['clean','bug']))

    print("\n── Advanced Model (Gradient Boosting) ──")
    print(classification_report(y_test, y_pred_advanced, target_names=['clean','bug']))

    return basic, advanced


# ──────────────────────────────────────────────────────────────────────────
# 4.  Correction lookup (exact + similarity)
# ──────────────────────────────────────────────────────────────────────────
class CorrectionDB:
    """In-memory lookup from bug_type → (code_snippet → corrected_code)."""
    def __init__(self, rows):
        self.exact = {}      # code → corrected_code
        self.by_type = {}    # bug_type → list of (code, corrected_code)
        for r in rows:
            if int(r['has_bug']) and r['corrected_code'].strip():
                self.exact[r['code'].strip()] = r['corrected_code']
                self.by_type.setdefault(r['bug_type'], []).append(
                    (r['code'], r['corrected_code'], r['description'])
                )

    def lookup(self, code: str, bug_type: str = '') -> str | None:
        code = code.strip()
        if code in self.exact:
            return self.exact[code]
        if bug_type and bug_type in self.by_type:
            # Return best match (longest common substring heuristic)
            candidates = self.by_type[bug_type]
            best = max(candidates, key=lambda c: _lcs_len(code, c[0]))
            return best[1]
        return None

    def serialize(self) -> dict:
        return {"exact": self.exact, "by_type": self.by_type}


def _lcs_len(a: str, b: str) -> int:
    """Length of longest common substring (fast approximation)."""
    min_len = min(len(a), len(b), 50)
    count = 0
    for i in range(min_len):
        if a[i] == b[i]:
            count += 1
    return count


# ──────────────────────────────────────────────────────────────────────────
# 5.  Main training pipeline
# ──────────────────────────────────────────────────────────────────────────
def main():
    os.makedirs(MODEL_DIR, exist_ok=True)
    print(f"Loading dataset from {DATASET_PATH}…")
    rows = load_dataset()
    print(f"  {len(rows)} samples | "
          f"{sum(1 for r in rows if int(r['has_bug']))} bugs | "
          f"{sum(1 for r in rows if not int(r['has_bug']))} clean")

    # ── Rule model ──
    rule_model = RuleModel()
    rule_acc = rule_model.accuracy(rows)
    print(f"\nRule model accuracy: {rule_acc*100:.1f}%")

    # ── Correction DB ──
    db = CorrectionDB(rows)
    print(f"Correction DB: {len(db.exact)} exact entries, "
          f"{len(db.by_type)} bug categories")

    # ── Save rule model + DB ──
    with open(os.path.join(MODEL_DIR, 'rule_model.pkl'), 'wb') as f:
        pickle.dump(rule_model, f)
    with open(os.path.join(MODEL_DIR, 'correction_db.pkl'), 'wb') as f:
        pickle.dump(db, f)
    print("Saved: models/rule_model.pkl, models/correction_db.pkl")

    # ── Sklearn models ──
    if HAS_SKLEARN:
        print("\nTraining sklearn ML models…")
        basic_model, advanced_model = train_sklearn_models(rows)

        # Also train a TF-IDF vectorizer standalone for code_analyzer.py
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2,4),
                              max_features=8000, sublinear_tf=True)
        vec.fit([r['code'] for r in rows])

        with open(os.path.join(MODEL_DIR, 'vectorizer.pkl'), 'wb') as f:
            pickle.dump(vec, f)
        with open(os.path.join(MODEL_DIR, 'bug_model.pkl'), 'wb') as f:
            pickle.dump(basic_model, f)
        with open(os.path.join(MODEL_DIR, 'advanced_bug_model.pkl'), 'wb') as f:
            pickle.dump(advanced_model, f)
        print("Saved: models/vectorizer.pkl, models/bug_model.pkl, models/advanced_bug_model.pkl")
    else:
        print("\nsklearn not installed — only rule model saved.")
        print("Install with: pip install scikit-learn")

    print("\n✅ Training complete!")


if __name__ == '__main__':
    main()
