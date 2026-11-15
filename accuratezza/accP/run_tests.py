import json
import time
import subprocess
import tempfile
import os
import csv
from pathlib import Path

RESULTS_CSV = "results.csv"
TASKS_FILE = "tasks.json"

def run_generated_code(code, tests):
    with tempfile.TemporaryDirectory() as tmpdir:
        code_path = os.path.join(tmpdir, "solution.py")
        test_path = os.path.join(tmpdir, "test_solution.py")

        with open(code_path, "w") as f:
            f.write(code)

        test_code = "from solution import *\n\n"
        for i, t in enumerate(tests):
            test_code += f"def test_{i}():\n"
            test_code += f"    assert {t['input']} == {t['expected']}\n\n"

        with open(test_path, "w") as f:
            f.write(test_code)

        result = subprocess.run(
            ["python", "-m", "pytest", test_path, "-q"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=30
        )

        passed = result.returncode == 0
        return passed, result.stdout, result.stderr

def run_task(task, model_response):
    code = extract_code(model_response)
    passed, stdout, stderr = run_generated_code(code, task["tests"])
    return {
        "task_id": task["id"],
        "passed": passed,
        "stdout": stdout,
        "stderr": stderr,
        "latency_ms": 0
    }

def extract_code(text):
    if "```python" in text:
        return text.split("```python").split("```")[0][1]
    if "```" in text:
        return text.split("```")[1].split("```")[0]
    return text

def save_results(results):
    keys = results[0].keys()
    with open(RESULTS_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)

def main():
    with open(TASKS_FILE) as f:
        tasks = json.load(f)["tasks"]

    results = []
    for task in tasks:
        model_response = get_model_response(task["prompt"])
        result = run_task(task, model_response)
        results.append(result)

    save_results(results)

if __name__ == "__main__":
    main()