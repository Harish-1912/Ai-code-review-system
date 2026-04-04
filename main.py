"""
main.py — Project entry point.
Runs the full pipeline:
  1. Generate / expand dataset
  2. Train models
  3. Start Flask app
"""
import subprocess, sys, os

def run(cmd):
    print(f"\n▶ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=os.path.dirname(__file__))
    if result.returncode != 0:
        print(f"  ⚠ Command exited with code {result.returncode}")

def main():
    print("╔══════════════════════════════════════╗")
    print("║   ANCHOR ELITE  —  Code Review AI    ║")
    print("╚══════════════════════════════════════╝")

    # Step 1: expand dataset
    run([sys.executable, 'generate_data.py'])

    # Step 2: train models
    run([sys.executable, 'train_model.py'])

    # Step 3: launch app
    print("\n▶ Starting Flask server on http://127.0.0.1:5000\n")
    os.execv(sys.executable, [sys.executable, 'app.py'])

if __name__ == '__main__':
    main()
